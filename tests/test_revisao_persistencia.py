"""Casos da revisão de 04/11/2026 (persistência): cada teste reproduz um defeito encontrado e já corrigido."""

from datetime import datetime

import pandas as pd

from pipeline import cadastro, carteira, prediagnostico, resultados
from pipeline.armazenamento import contratos, historico, lago
from pipeline.armazenamento.contratos import Coluna, Contrato

from conftest import CPF_VALIDO

T1, T2 = datetime(2026, 10, 1, 3), datetime(2026, 11, 1, 3)


def _contrato(historico_, colunas, acompanhar=()):
    return Contrato("ref.teste", "", "teste", ("id",), historico_, "lite", tuple(colunas), tuple(acompanhar))


def _gravar(c, pasta, df, momento):
    return historico.GRAVAR[c.historico](pasta, contratos.validar(df, c), c, f"teste:{momento:%Y%m%dT%H%M%S}",
                                          momento)


def test_coluna_nova_no_contrato_nao_quebra_a_tabela_validade(tmp_path):
    antigo = _contrato("validade", [Coluna("id", "texto", False), Coluna("situacao", "texto")], ("situacao",))
    _gravar(antigo, tmp_path, pd.DataFrame({"id": ["a"], "situacao": ["ativo"]}), T1)
    novo = _contrato("validade", [*antigo.colunas, Coluna("cnae", "texto")], ("situacao",))
    _gravar(novo, tmp_path, pd.DataFrame({"id": ["a", "b"], "situacao": ["ativo", "ativo"], "cnae": ["x", "y"]}), T2)
    vigente = historico.ler(tmp_path, novo).set_index("id")
    assert vigente.at["b", "cnae"] == "y" and vigente.at["a", "cnae"] == "x"


def test_inteiro_em_float_nao_abre_versao_nova(tmp_path):
    c = _contrato("validade", [Coluna("id", "texto", False), Coluna("n", "inteiro")], ("n",))
    _gravar(c, tmp_path, pd.DataFrame({"id": ["a"], "n": pd.array([5], dtype="Int64")}), T1)
    resumo = _gravar(c, tmp_path, pd.DataFrame({"id": ["a"], "n": [5.0]}), T2)
    assert resumo["inalterados"] == 1 and resumo["versoes"] == 1


def test_duas_gravacoes_no_mesmo_segundo_nao_repetem_a_chave(tmp_path):
    v = _contrato("validade", [Coluna("id", "texto", False), Coluna("s", "texto")], ("s",))
    _gravar(v, tmp_path, pd.DataFrame({"id": ["a"], "s": ["1"]}), T1)
    _gravar(v, tmp_path, pd.DataFrame({"id": ["a"], "s": ["2"]}), T2)
    _gravar(v, tmp_path, pd.DataFrame({"id": ["a"], "s": ["3"]}), T2)
    tudo = historico.ler(tmp_path, v, vigente=False)
    assert not tudo.duplicated(["id", "valido_de"]).any()
    assert historico.ler(tmp_path, v)["s"].tolist() == ["3"]

    p = _contrato("por_consulta", [Coluna("id", "texto", False), Coluna("f", "decimal")])
    pasta = tmp_path / "pc"
    _gravar(p, pasta, pd.DataFrame({"id": ["a"], "f": [0.1]}), T2)
    _gravar(p, pasta, pd.DataFrame({"id": ["a"], "f": [0.2]}), T2)
    tudo = historico.ler(pasta, p, vigente=False)
    assert len(tudo) == 1 and tudo["f"].iloc[0] == 0.2


def test_carteira_com_coordenada_invalida_e_cpf_em_coluna_livre(tmp_path):
    planilha = pd.DataFrame({"id_produtor": ["P1", "P2"], "cod_car": [None, None], "lat": ["18°54'S", "-18,9"],
                             "lon": ["46°W", "-46,9"], "cpf": [CPF_VALIDO, None],
                             "obs": ["titular 11144477735", "ok"]})
    arquivo = tmp_path / "coop.csv"
    planilha.to_csv(arquivo, index=False)
    org = cadastro.organizacao("Coop")
    _, ids = cadastro.importar_carteira(planilha, org, arquivo)  # a linha inválida não derruba a carteira
    assert ids[0]["imovel_id"] and lago.ler("cad.imovel")["lat"].dropna().tolist() == [-18.9]
    texto = lago.ler("cad.carteira_item").to_csv()
    assert "11144477735" not in texto and "111.444.777-35" not in texto and '"obs"' in texto
    saida = carteira.processar(planilha, tmp_path / "saida", consultar=lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("sem rede")))
    assert "cpf" not in saida.columns and "11144477735" not in saida.to_csv()


def test_demonstracao_tem_organizacao_propria_e_avulsa_fica_sem():
    assert resultados.Execucao("demonstracao").organizacao_id == resultados.DEMONSTRACAO
    assert resultados.Execucao("avulsa").organizacao_id is None


def test_evidencia_da_lista_suja_usa_a_chave_estavel_e_leva_a_carga():
    lista = pd.DataFrame({"chave_registro": ["k1"], "id_registro": [7], "documento_hash": ["h"], "uf": ["MG"],
                          "cnae": ["0134"], "data_inclusao": [pd.Timestamp("2025-01-01")],
                          "data_decisao": [pd.NaT], "carga_id": ["mte_lista_suja:20261103T100000"]})
    _, achados = prediagnostico._criterio_lista_suja(lista, "h")
    colunas = ["chave_registro", "id_registro", "uf", "cnae", "data_inclusao", "data_decisao", "carga_id"]
    assert achados.reindex(columns=colunas)["carga_id"].iloc[0] == "mte_lista_suja:20261103T100000"
    assert resultados.EVIDENCIAS["lista_suja"][2] == "chave_registro"
