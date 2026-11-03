import pandas as pd
import pytest

from conftest import CHAVE, CNPJ_VALIDO, CPF_VALIDO, CPF_VALIDO_2, HOJE, ocorrencias
from pipeline.fontes import mte_lista_suja
from pipeline.validacao import ErroDeValidacao, ResultadoFonte

CABECALHO = ["ID", "Ano da\nação fiscal", "UF", "Empregador", "CNPJ/CPF", "Estabelecimento", "Trabalhadores\nenvolvidos",
             "CNAE", "Decisão administrativa\nde procedência", "Inclusão no\nCadastro de\nEmpregadores"]
TEXTO = "Cadastro de Empregadores\nAtualização periódica. Cadastro atualizado em 04/09/2026."


def registro(id_, doc=CPF_VALIDO, uf="MG", ano="2023", trab="5", cnae="0151-2/01", decisao="10/01/2024",
             inclusao="05/04/2024"):
    return [id_, ano, uf, "Nome Fictício", doc, "Fazenda Fictícia, zona rural", trab, cnae, decisao, inclusao]


def titulo(texto):
    return [texto] + [None] * 9


def processar(tabelas, textos=None):
    textos = textos if textos is not None else [TEXTO] * len(tabelas)
    resultado = ResultadoFonte("mte_lista_suja", "documento")
    saida, descartados = mte_lista_suja.transformar(textos, tabelas, CHAVE, HOJE, resultado)
    return saida.set_index("id_registro", drop=False), descartados, resultado


def test_segmentacao_remove_cabecalhos_e_titulos():
    pagina = [titulo("Atualização periódica"), titulo("I- PUBLICAÇÃO"), CABECALHO, registro("1"), registro("2", CNPJ_VALIDO)]
    saida, descartados, res = processar([pagina, [titulo("I- PUBLICAÇÃO"), CABECALHO, registro("3", CPF_VALIDO_2)]])
    assert saida["id_registro"].tolist() == [1, 2, 3] and len(descartados) == 0
    assert saida["data_atualizacao_cadastro"].iloc[0] == pd.Timestamp("2026-09-04")
    assert "empregador" not in saida.columns and saida.loc[2, "tipo_documento"] == "CNPJ"
    assert bool(saida.loc[1, "cnae_agropecuaria"])


def test_documento_vazio_interrompe():
    with pytest.raises(ErroDeValidacao, match="LS_DOCUMENTO_VAZIO"):
        processar([[CABECALHO, registro("1")]], textos=[""])


def test_cabecalho_inesperado_interrompe():
    with pytest.raises(ErroDeValidacao, match="LS_CABECALHO_INESPERADO"):
        processar([[["ID", "Outra coluna"] + [""] * 8, registro("1")]])


def test_linha_nao_reconhecida_e_descartada():
    saida, descartados, res = processar([[CABECALHO, registro("1"), ["", "2023", "MG"] + [""] * 7]])
    assert len(saida) == 1 and ocorrencias(res, "LS_LINHA_NAO_RECONHECIDA") == 1 and len(descartados) == 1


def test_id_duplicado_interrompe():
    with pytest.raises(ErroDeValidacao, match="LS_ID_DUPLICADO"):
        processar([[CABECALHO, registro("1"), registro("1", CPF_VALIDO_2)]])


def test_documentos_invalidos_e_repetidos():
    saida, _, _ = processar([[CABECALHO, registro("1", "111.444.777-36"), registro("2", "123"),
                              registro("3", CPF_VALIDO_2), registro("4", CPF_VALIDO_2)]])
    assert saida.loc[1, "alertas"] == "DOC_DV_INVALIDO" and pd.isna(saida.loc[1, "documento_hash"])
    assert saida.loc[2, "alertas"] == "DOC_FORMATO_INVALIDO"
    assert saida.loc[3, "alertas"] == saida.loc[4, "alertas"] == "DOC_REPETIDO"


def test_registro_incompleto_gera_alertas_e_anula_campos():
    saida, _, _ = processar([[CABECALHO, registro("1", uf="", ano="", trab="", cnae="", decisao="")]])
    r = saida.loc[1]
    assert r["alertas"] == ("UF_INVALIDA;ANO_ACAO_INVALIDO;TRABALHADORES_INVALIDO;"
                            "CNAE_FORMATO_INVALIDO;DATA_DECISAO_INVALIDA")
    assert pd.isna(r["uf"]) and pd.isna(r["ano_acao_fiscal"]) and pd.isna(r["data_decisao"])


def test_multiplos_periodos_de_inclusao():
    saida, _, res = processar([[CABECALHO, registro("1", inclusao="01/02/2020 a 03/04/2021, 05/06/2022")]])
    assert saida.loc[1, "data_inclusao"] == pd.Timestamp("2020-02-01")
    assert saida.loc[1, "data_inclusao_ultima"] == pd.Timestamp("2022-06-05")
    assert ocorrencias(res, "LS_INCLUSAO_MULTIPLOS_PERIODOS") == 1


def test_inclusao_antes_da_decisao_e_data_futura():
    saida, _, _ = processar([[CABECALHO, registro("1", decisao="10/01/2024", inclusao="01/01/2024"),
                              registro("2", CPF_VALIDO_2, inclusao="01/01/2030")]])
    assert saida.loc[1, "alertas"] == "INCLUSAO_ANTES_DA_DECISAO"
    assert saida.loc[2, "alertas"] == "DATA_INCLUSAO_INVALIDA" and pd.isna(saida.loc[2, "data_inclusao"])


def test_data_de_atualizacao_ausente_gera_alerta():
    _, _, res = processar([[CABECALHO, registro("1")]], textos=["Cadastro de Empregadores"])
    assert ocorrencias(res, "LS_DATA_ATUALIZACAO_AUSENTE") == 1


def test_pagina_sem_texto_gera_alerta():
    _, _, res = processar([[CABECALHO, registro("1")], []], textos=[TEXTO, ""])
    assert ocorrencias(res, "LS_PAGINA_SEM_TEXTO") == 1


def test_documento_sem_registros_interrompe():
    with pytest.raises(ErroDeValidacao, match="LS_SEM_REGISTROS"):
        processar([[titulo("I- PUBLICAÇÃO"), CABECALHO]])


# --- Chave do registro e gravação no lago --------------------------------------------------------------------------

def test_chave_do_registro_e_estavel_unica_e_sem_documento_em_claro():
    pagina = [CABECALHO, registro("1"), registro("2", CPF_VALIDO_2, ano="", uf=""),
              registro("3", CNPJ_VALIDO, trab="7"), registro("4", CNPJ_VALIDO, trab="8")]
    saida, _, _ = processar([pagina])
    assert saida["chave_registro"].is_unique and saida["chave_registro"].str.fullmatch(r"[0-9a-f]{32}").all()
    assert pd.isna(saida.loc[2, "ano_acao_fiscal"])  # nulo na tripla, mas a chave existe
    # A numeração do PDF muda entre versões; a chave não.
    nova, _, _ = processar([[CABECALHO, registro("40", CNPJ_VALIDO, trab="7"), registro("41", CNPJ_VALIDO, trab="8"),
                             registro("42", CPF_VALIDO_2, ano="", uf=""), registro("43")]])
    assert (nova.set_index("chave_registro")["trabalhadores_envolvidos"].to_dict()
            == saida.set_index("chave_registro")["trabalhadores_envolvidos"].to_dict())
    assert CPF_VALIDO not in saida.to_string()


@pytest.fixture
def lago_tmp(tmp_path, monkeypatch):
    from pipeline import config
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(config, "LAGO", tmp_path / "data" / "lago")
    monkeypatch.setattr(config, "DADOS_BRUTOS", tmp_path / "data" / "raw")
    monkeypatch.setattr(config, "DADOS_PROCESSADOS", tmp_path / "data" / "processed")
    return tmp_path


def executar(monkeypatch, tabelas, n):
    monkeypatch.setattr(mte_lista_suja, "baixar", lambda *a, **k: {})
    monkeypatch.setattr(mte_lista_suja, "extrair", lambda caminho: ([TEXTO] * len(tabelas), tabelas))
    monkeypatch.setattr(mte_lista_suja, "ResultadoFonte",
                        lambda fonte, tipo: ResultadoFonte(fonte, tipo, carga_id=f"{fonte}:2026091{n}T120000"))
    return mte_lista_suja.executar(CHAVE, HOJE)


def test_executar_grava_no_lago_e_so_abre_versao_quando_algo_muda(lago_tmp, monkeypatch):
    from pipeline.armazenamento import lago
    r1 = executar(monkeypatch, [[CABECALHO, registro("1"), registro("2", CNPJ_VALIDO)]], 1)
    assert r1.saida["arquivo"] == "data/lago/ref/lista_suja" and r1.saida["registros_produzidos"] == 2
    assert r1.saida["tabelas"]["ref.lista_suja"]["inseridos"] == 2
    assert not (lago_tmp / "data" / "processed").exists()  # nada em data/processed

    r2 = executar(monkeypatch, [[CABECALHO, registro("2", CNPJ_VALIDO), registro("1")]], 2)  # outra ordem, mesmo dado
    resumo = r2.saida["tabelas"]["ref.lista_suja"]
    assert (resumo["inseridos"], resumo["alterados"], resumo["encerrados"], resumo["versoes"]) == (0, 0, 0, 2)

    # Mudança em coluna acompanhada (trabalhadores) fecha a versão e abre outra; id_registro novo não conta.
    r3 = executar(monkeypatch, [[CABECALHO, registro("7", trab="9"), registro("8", CNPJ_VALIDO)]], 3)
    resumo = r3.saida["tabelas"]["ref.lista_suja"]
    assert (resumo["alterados"], resumo["inalterados"], resumo["versoes"]) == (1, 1, 3)
    vigente = lago.ler("ref.lista_suja")
    assert len(vigente) == 2 and sorted(vigente["trabalhadores_envolvidos"]) == [5, 9]
    assert {"id_registro", "documento_hash", "data_inclusao", "data_decisao", "uf", "cnae"} <= set(vigente.columns)
