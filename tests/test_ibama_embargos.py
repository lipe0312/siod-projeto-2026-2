import pandas as pd
import pytest

from conftest import CHAVE, CPF_VALIDO, HOJE, ocorrencias
from pipeline.fontes import ibama_embargos
from pipeline.validacao import ErroDeValidacao, ResultadoFonte

POLIGONO = "POLYGON((-50.6 -3.8, -50.5 -3.8, -50.5 -3.7, -50.6 -3.8))"


def linha(**campos):
    base = dict(SEQ_TAD="1", NUM_TAD="100", SER_TAD="A", DAT_EMBARGO="10/05/2022 10:00:00",
                DAT_ULT_ALTERACAO="11/05/2022 10:00:00", COD_UF_TAD="15", SIG_UF_TAD="PA", COD_MUNICIPIO_TAD="1505486",
                NOM_MUNICIPIO_TAD="Pacaja", NUM_LATITUDE_TAD="-3.8", NUM_LONGITUDE_TAD="-50.6",
                CPF_CNPJ_EMBARGADO=CPF_VALIDO, QTD_AREA_EMBARGADA="10,5000", DES_TIPO_BIOMA="Amazonia",
                WKT_GEOM_AREA_EMBARGADA=POLIGONO, DES_INFRACAO="Desmatar sem autorização")
    base.update(campos)
    return base


def processar(linhas, ref):
    bruto = pd.DataFrame(linhas).astype(str).replace("None", "")
    resultado = ResultadoFonte("ibama_embargos", "tabular")
    saida, descartados = ibama_embargos.transformar(bruto, CHAVE, ref, HOJE, resultado)
    return saida.set_index("seq_tad", drop=False), descartados, resultado


def test_registro_valido_sai_tipado_e_sem_documento_original(ref_municipios):
    saida, descartados, _ = processar([linha()], ref_municipios)
    r = saida.iloc[0]
    assert r["id_embargo"] == "100-A-1" and r["alertas"] == ""
    assert r["tipo_documento"] == "CPF" and len(r["documento_hash"]) == 64
    assert r["area_ha"] == 10.5 and r["biomas"] == "Amazônia" and r["municipio"] == "Pacajá"
    assert bool(r["pos_corte_eudr"]) and "CPF_CNPJ_EMBARGADO" not in saida.columns
    assert len(descartados) == 0


def test_colunas_obrigatorias_ausentes_interrompem(ref_municipios):
    bruto = pd.DataFrame([linha()]).drop(columns=["DAT_EMBARGO"])
    with pytest.raises(ErroDeValidacao, match="IBAMA_COLUNAS_OBRIGATORIAS"):
        ibama_embargos.transformar(bruto, CHAVE, ref_municipios, HOJE, ResultadoFonte("x", "x"))


def test_identificador_duplicado_interrompe(ref_municipios):
    with pytest.raises(ErroDeValidacao, match="IBAMA_ID_DUPLICADO"):
        processar([linha(), linha()], ref_municipios)


def test_numero_do_termo_ausente_e_descartado(ref_municipios):
    saida, descartados, res = processar([linha(), linha(SEQ_TAD="2", NUM_TAD="")], ref_municipios)
    assert len(saida) == 1 and descartados["motivo"].tolist() == ["IBAMA_NUMERO_TERMO_AUSENTE"]


def test_documentos_invalidos_sao_anulados(ref_municipios):
    saida, _, res = processar([linha(SEQ_TAD="1", CPF_CNPJ_EMBARGADO="111.444.777-36"),
                               linha(SEQ_TAD="2", CPF_CNPJ_EMBARGADO="12345"),
                               linha(SEQ_TAD="3", CPF_CNPJ_EMBARGADO="")], ref_municipios)
    assert saida["documento_hash"].isna().all()
    assert saida.loc["1", "alertas"] == "DOC_DV_INVALIDO"
    assert saida.loc["2", "alertas"] == "DOC_TAMANHO_INVALIDO"
    assert saida.loc["3", "alertas"] == "DOC_AUSENTE"


def test_datas_futura_e_invalida_sao_anuladas(ref_municipios):
    saida, _, res = processar([linha(SEQ_TAD="1", DAT_EMBARGO="25/09/2925 15:10:00"),
                               linha(SEQ_TAD="2", DAT_EMBARGO="31/02/2020 10:00:00")], ref_municipios)
    assert saida["data_embargo"].isna().all() and saida["pos_corte_eudr"].isna().all()
    assert ocorrencias(res, "IBAMA_DATA_EMBARGO_FUTURA") == 1
    assert ocorrencias(res, "IBAMA_DATA_EMBARGO_INVALIDA") == 1


def test_coordenadas_impossiveis_sao_anuladas(ref_municipios):
    saida, _, _ = processar([linha(SEQ_TAD="1", NUM_LATITUDE_TAD="0", NUM_LONGITUDE_TAD="0"),
                             linha(SEQ_TAD="2", NUM_LATITUDE_TAD="40.4", NUM_LONGITUDE_TAD="-3.7"),
                             linha(SEQ_TAD="3", NUM_LONGITUDE_TAD="")], ref_municipios)
    assert saida["latitude"].isna().all() and saida["longitude"].isna().all()
    assert [saida.loc[s, "alertas"] for s in "123"] == ["COORD_ZERO", "COORD_FORA_BRASIL", "COORD_INCOMPLETA"]


def test_area_nao_positiva_e_texto_invalido(ref_municipios):
    saida, _, res = processar([linha(SEQ_TAD="1", QTD_AREA_EMBARGADA="0,0000"),
                               linha(SEQ_TAD="2", QTD_AREA_EMBARGADA="dez")], ref_municipios)
    assert saida["area_ha"].isna().all()
    assert ocorrencias(res, "IBAMA_AREA_NAO_POSITIVA") == 1 and ocorrencias(res, "IBAMA_AREA_INVALIDA") == 1


def test_bioma_normalizado_e_desconhecido(ref_municipios):
    saida, _, res = processar([linha(SEQ_TAD="1", DES_TIPO_BIOMA="Cerrado, Amazonia, Amazonia"),
                               linha(SEQ_TAD="2", DES_TIPO_BIOMA="Amazonia, Tundra")], ref_municipios)
    assert saida.loc["1", "biomas"] == "Amazônia, Cerrado"
    assert saida.loc["2", "biomas"] == "Amazônia" and saida.loc["2", "alertas"] == "BIOMA_DESCONHECIDO"


def test_municipio_desconhecido_e_uf_divergente(ref_municipios):
    saida, _, _ = processar([linha(SEQ_TAD="1", COD_MUNICIPIO_TAD="9999999"),
                             linha(SEQ_TAD="2", COD_MUNICIPIO_TAD="2927408")], ref_municipios)
    assert saida.loc["1", "alertas"] == "MUNICIPIO_DESCONHECIDO"
    assert saida.loc["2", "alertas"] == "MUNICIPIO_UF_DIVERGENTE" and saida.loc["2", "uf"] == "BA"


def test_geometrias_problematicas(ref_municipios):
    saida, _, _ = processar([
        linha(SEQ_TAD="1", WKT_GEOM_AREA_EMBARGADA="POLYGON((-50.6 -3.8, -50.5"),
        linha(SEQ_TAD="2", WKT_GEOM_AREA_EMBARGADA="POINT(-50.6 -3.8)"),
        linha(SEQ_TAD="3", WKT_GEOM_AREA_EMBARGADA="POLYGON((10 10, 11 10, 11 11, 10 10))"),
        linha(SEQ_TAD="4", WKT_GEOM_AREA_EMBARGADA="POLYGON((-50.6 -3.8, -50.5 -3.7, -50.5 -3.8, -50.6 -3.7, -50.6 -3.8))"),
    ], ref_municipios)
    assert saida.loc[["1", "2", "3"], "geometria_wkt"].isna().all()
    assert [saida.loc[s, "alertas"] for s in "123"] == ["GEOM_ILEGIVEL", "GEOM_TIPO_INVALIDO", "GEOM_FORA_BRASIL"]
    assert saida.loc["4", "alertas"] == "GEOM_INVALIDA" and saida.loc["4", "geometria_wkt"] is not None


def test_sem_vinculo_nem_localizacao_e_descartado(ref_municipios):
    inutil = linha(SEQ_TAD="2", CPF_CNPJ_EMBARGADO="", WKT_GEOM_AREA_EMBARGADA="",
                   NUM_LATITUDE_TAD="0", NUM_LONGITUDE_TAD="0")
    saida, descartados, res = processar([linha(), inutil], ref_municipios)
    assert len(saida) == 1
    assert descartados["motivo"].tolist() == ["IBAMA_SEM_VINCULO_NEM_LOCALIZACAO"]
    assert "documento_hash" in descartados.columns and "CPF_CNPJ_EMBARGADO" not in descartados.columns


def test_arquivo_sem_registros_interrompe(ref_municipios):
    bruto = pd.DataFrame(columns=ibama_embargos.COLUNAS_OBRIGATORIAS)
    with pytest.raises(ErroDeValidacao, match="IBAMA_SEM_REGISTROS"):
        ibama_embargos.transformar(bruto, CHAVE, ref_municipios, HOJE, ResultadoFonte("x", "x"))


# --- Termo de embargo do Portal de Dados Abertos (fonte desde 02/11/2026) -----------------------------------------

def linha_portal(**campos):
    base = dict(SEQ_TAD="1", DES_STATUS_FORMULARIO="Lavrado", SIT_CANCELADO="N", NUM_TAD="100", SER_TAD="A",
                DAT_EMBARGO="2022-05-10 10:00:00", DAT_ULT_ALTERACAO="2022-05-11 10:00:00", CPF_CNPJ_EMBARGADO=CPF_VALIDO,
                NOME_EMBARGADO="NOME QUALQUER", DES_TAD="Desmatar sem autorização", COD_MUNICIPIO="1505486",
                MUNICIPIO="Pacaja", UF="PA", NUM_LONGITUDE_TAD="-50.6", NUM_LATITUDE_TAD="-3.8",
                QTD_AREA_EMBARGADA="10,5000", GEOM_AREA_EMBARGADA=POLIGONO, SIT_DESEMBARGO="", DAT_DESEMBARGO="")
    base.update(campos)
    return base


def test_portal_cancelado_sai_e_desembargado_fica_marcado(ref_municipios):
    saida, descartados, r = processar([
        linha_portal(), linha_portal(SEQ_TAD="2", SIT_CANCELADO="S"),
        linha_portal(SEQ_TAD="3", DES_STATUS_FORMULARIO="Substituído por outro"),
        linha_portal(SEQ_TAD="4", SIT_DESEMBARGO="S", DAT_DESEMBARGO="2024-02-01 09:00:00")], ref_municipios)
    assert sorted(saida.index) == ["1", "4"]
    assert saida.loc["1", "situacao"] == "ativo" and saida.loc["4", "situacao"] == "desembargado"
    assert str(saida.loc["4", "data_desembargo"].date()) == "2024-02-01"
    assert str(saida.loc["1", "data_embargo"].date()) == "2022-05-10"  # data no formato do portal
    assert saida.loc["1", "uf"] == "PA" and saida.loc["1", "descricao_infracao"] == "Desmatar sem autorização"
    assert ocorrencias(r, "IBAMA_TERMO_CANCELADO") == 2 and ocorrencias(r, "IBAMA_DESEMBARGADO") == 1
    assert set(descartados["motivo"]) == {"IBAMA_TERMO_CANCELADO"}
    assert "NOME_EMBARGADO" not in saida and CPF_VALIDO not in saida.to_string()


def test_portal_data_com_ano_impossivel_e_anulada(ref_municipios):
    saida, _, r = processar([linha_portal(DAT_EMBARGO="2925-09-25 15:10:00")], ref_municipios)
    assert pd.isna(saida.iloc[0]["data_embargo"]) and ocorrencias(r, "IBAMA_DATA_EMBARGO_FUTURA") == 1


def test_csv_antigo_continua_lido_e_todo_embargo_e_ativo(ref_municipios):
    saida, _, _ = processar([linha()], ref_municipios)
    assert saida.iloc[0]["situacao"] == "ativo"


def test_embargo_desembargado_no_imovel_nao_e_pendencia():
    from pipeline import prediagnostico
    from test_prediagnostico import DENTRO, alertas, car, embargos, lista_suja, prodes
    emb = embargos(("e1", DENTRO, None, None)).assign(situacao="desembargado",
                                                      data_desembargo=pd.Timestamp("2024-02-01"))
    ficha = prediagnostico.diagnosticar(car(), emb, alertas(), lista_suja(), prodes(), ultimo_ano_prodes=2025)
    c = next(c for c in ficha["criterios"] if c["chave"] == "embargo")
    assert c["situacao"] == "sem ocorrência" and "desembargado em 01/02/2024" in c["evidencia"]
    ativo = embargos(("e1", DENTRO, None, None))  # sem a coluna situacao (CSV antigo): conta como ativo
    ficha = prediagnostico.diagnosticar(car(), ativo, alertas(), lista_suja(), prodes(), ultimo_ano_prodes=2025)
    assert next(c for c in ficha["criterios"] if c["chave"] == "embargo")["situacao"] == "pendência"
