from datetime import datetime

import pandas as pd
import pytest

from pipeline import config
from pipeline.armazenamento import cargas, contratos, historico, lago
from pipeline.armazenamento.contratos import Coluna, Contrato, ErroDeContrato
from pipeline.validacao import ResultadoFonte

T1, T2, T3 = datetime(2026, 10, 1, 3), datetime(2026, 11, 1, 3), datetime(2026, 12, 1, 3)


def contrato(historico_, chave=("id",), acompanhar=(), particao=None, substituir=False):
    colunas = (Coluna("id", "texto", False), Coluna("uf", "texto", False), Coluna("valor", "decimal"),
               Coluna("situacao", "texto"))
    return Contrato("ref.teste", "", "teste", tuple(chave), historico_, "lite", colunas, tuple(acompanhar), particao,
                    substituir)


def dados(*linhas):
    return pd.DataFrame(linhas, columns=["id", "uf", "valor", "situacao"])


def gravar(c, pasta, df, momento):
    return historico.GRAVAR[c.historico](pasta, contratos.validar(df, c), c, f"teste:{momento:%Y%m%dT%H%M%S}",
                                          momento)


def test_todos_os_contratos_carregam_e_fontes_do_catalogo_existem():
    todos = contratos.todos()
    assert {"meta", "geo", "ref", "cad", "diag"} == {c.esquema for c in todos.values()}
    tabelas_catalogo = {t for f in contratos.catalogo_fontes() for t in f["tabelas"]}
    assert tabelas_catalogo <= set(todos)
    for c in todos.values():
        if c.esquema in ("cad", "diag") and c.tabela not in ("diag.execucao_carga",):
            assert "organizacao_id" in c.nomes, c.tabela  # segurança por linha


def test_validar_recusa_coluna_tipo_nulo_e_chave_repetida():
    c = contrato("fotografia")
    with pytest.raises(ErroDeContrato, match="faltam"):
        contratos.validar(dados(("a", "BA", 1.0, "x")).drop(columns="valor"), c)
    with pytest.raises(ErroDeContrato, match="fora do contrato"):
        contratos.validar(dados(("a", "BA", 1.0, "x")).assign(extra=1), c)
    with pytest.raises(ErroDeContrato, match="não é decimal"):
        contratos.validar(dados(("a", "BA", "um", "x")), c)
    with pytest.raises(ErroDeContrato, match="nulo"):
        contratos.validar(dados((None, "BA", 1.0, "x")), c)
    with pytest.raises(ErroDeContrato, match="repetida"):
        contratos.validar(dados(("a", "BA", 1.0, "x"), ("a", "MG", 2.0, "y")), c)
    # Coluna de controle que veio da leitura do lago é descartada, não recusada.
    assert list(contratos.validar(dados(("a", "BA", 1.0, "x")).assign(carga_id="c"), c).columns) == c.nomes


def test_fotografia_so_grava_quando_o_conteudo_muda(tmp_path):
    c = contrato("fotografia")
    df = dados(("a", "BA", 1.0, "x"), ("b", "MG", 2.0, "y"))
    assert gravar(c, tmp_path, df, T1)["novo"]
    assert not gravar(c, tmp_path, df.iloc[::-1], T2)["novo"]  # mesma informação, outra ordem
    assert gravar(c, tmp_path, dados(("a", "BA", 1.5, "x")), T3)["novo"]
    vigente = historico.ler(tmp_path, c)
    assert vigente["valor"].tolist() == [1.5] and vigente["carga_id"].iloc[0] == "teste:20261201T030000"
    assert len(historico.ler(tmp_path, c, vigente=False)) == 3  # duas cargas guardadas


def test_validade_abre_fecha_e_corrige_versoes(tmp_path):
    c = contrato("validade", acompanhar=("situacao",))
    gravar(c, tmp_path, dados(("a", "BA", 1.0, "ativo"), ("b", "MG", 2.0, "ativo"), ("c", "PA", 3.0, "ativo")), T1)
    resumo = gravar(c, tmp_path, dados(("a", "BA", 1.0, "desembargado"), ("b", "MG", 9.0, "ativo"),
                                       ("d", "SP", 4.0, "ativo")), T2)
    assert (resumo["inseridos"], resumo["alterados"], resumo["encerrados"], resumo["inalterados"]) == (1, 1, 1, 1)
    vigente = historico.ler(tmp_path, c).set_index("id")
    assert sorted(vigente.index) == ["a", "b", "d"]
    assert vigente.at["a", "situacao"] == "desembargado"
    assert vigente.at["b", "valor"] == 9.0  # coluna não acompanhada: corrigida sem versão nova
    assert vigente.at["b", "carga_id"] == "teste:20261001T030000"
    tudo = historico.ler(tmp_path, c, vigente=False)
    a = tudo[tudo["id"] == "a"].sort_values("valido_de")
    assert a["situacao"].tolist() == ["ativo", "desembargado"]
    assert a["valido_ate"].iloc[0] == pd.Timestamp(T2) and pd.isna(a["valido_ate"].iloc[1])
    assert tudo.loc[tudo["id"] == "c", "valido_ate"].iloc[0] == pd.Timestamp(T2)  # sumiu da fonte


def test_acrescimo_nao_duplica_e_mantem_a_carga_de_entrada(tmp_path):
    c = contrato("acrescimo", particao="uf")
    gravar(c, tmp_path, dados(("a", "BA", 1.0, "x"), ("b", "MG", 2.0, "y")), T1)
    resumo = gravar(c, tmp_path, dados(("a", "BA", 1.0, "x"), ("c", "BA", 3.0, "z")), T2)
    assert (resumo["inseridos"], resumo["alterados"], resumo["particoes_gravadas"]) == (1, 0, ["BA"])
    df = historico.ler(tmp_path, c).set_index("id")
    assert sorted(df.index) == ["a", "b", "c"]  # "b" (MG) não veio na carga 2 e continua
    assert df.at["a", "carga_id"] == "teste:20261001T030000"
    assert df.at["c", "carga_id"] == "teste:20261101T030000"
    assert list(historico.ler(tmp_path, c, particao="MG")["id"]) == ["b"]
    assert gravar(c, tmp_path, dados(("a", "BA", 1.0, "x")), T3)["particoes_gravadas"] == []


def test_acrescimo_com_substituir_particao_remove_o_que_sumiu(tmp_path):
    c = contrato("acrescimo", chave=("id", "uf"), particao="uf", substituir=True)
    gravar(c, tmp_path, dados(("a", "BA", 1.0, "x"), ("b", "BA", 2.0, "y")), T1)
    resumo = gravar(c, tmp_path, dados(("a", "BA", 1.0, "x")), T2)
    assert resumo["removidos"] == 1
    assert historico.ler(tmp_path, c)["id"].tolist() == ["a"]


def test_por_consulta_so_acrescenta_versao_diferente(tmp_path):
    c = contrato("por_consulta")
    gravar(c, tmp_path, dados(("a", "BA", 1.0, "x")), T1)
    assert gravar(c, tmp_path, dados(("a", "BA", 1.0, "x")), T2)["repetidos"] == 1
    gravar(c, tmp_path, dados(("a", "BA", 2.0, "x")), T3)
    assert historico.ler(tmp_path, c)["valor"].tolist() == [2.0]
    assert len(historico.ler(tmp_path, c, vigente=False)) == 2


def test_lago_grava_anota_no_resultado_e_le_o_legado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LAGO", tmp_path / "lago")
    monkeypatch.setattr(config, "DADOS_PROCESSADOS", tmp_path / "processed")
    (tmp_path / "processed").mkdir()
    municipios = pd.DataFrame({"cod_municipio": ["2927408"], "municipio": ["Salvador"], "uf": ["BA"],
                               "chave": ["salvador|BA"]})
    municipios.to_parquet(tmp_path / "processed" / "ibge_municipios.parquet", index=False)
    assert lago.ler("geo.municipio")["municipio"].tolist() == ["Salvador"]  # legado

    r = ResultadoFonte("ibge_municipios", "API (JSON)", carga_id="ibge_municipios:20261103T100000")
    lago.gravar("geo.municipio", municipios.assign(municipio="Salvador (BA)"), r)
    assert r.saida["tabelas"]["geo.municipio"]["novo"]
    lido = lago.ler("geo.municipio")
    assert lido["municipio"].tolist() == ["Salvador (BA)"] and lido["carga_id"].iloc[0] == r.carga_id
    with pytest.raises(lago.TabelaAusente):
        lago.ler("ref.terra_indigena")


def test_cargas_e_descartes_vao_para_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LAGO", tmp_path / "lago")
    r = ResultadoFonte("ibama_embargos", "tabular (CSV)", carga_id="ibama_embargos:20261103T100000", status="ok",
                       entrada={"url": "https://exemplo", "sha256": "abc", "registros_recebidos": 3},
                       saida={"registros_produzidos": 2, "registros_descartados": 1})
    r.validar("IBAMA_TESTE", "teste", "descarte", "descarta", 1, 3)
    descartes = pd.DataFrame({"id_embargo": ["X-1", None], "motivo": ["sem data", "sem data"],
                              "area_ha": [1.0, 2.0]})
    assert lago.gravar_descartes(descartes, r, "id_embargo")["inseridos"] == 2
    cargas.registrar([r])
    assert cargas.ultima("ibama_embargos")["sha256_entrada"] == "abc"
    assert lago.ler("meta.validacao")["codigo"].tolist() == ["IBAMA_TESTE"]
    assert sorted(lago.ler("meta.descarte")["registro_id"]) == ["X-1", "linha:1"]
    assert cargas.registrar_catalogo()["novo"] and not cargas.registrar_catalogo()["novo"]
