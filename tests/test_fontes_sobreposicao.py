"""Terras indígenas, unidades de conservação e territórios quilombolas: validações das fontes e critérios de
sobreposição no pré-diagnóstico (sem rede)."""

import numpy as np
import pandas as pd
import pytest
import shapely

from conftest import ocorrencias
from pipeline import prediagnostico
from pipeline.fontes import (funai_terras_indigenas, ibge_territorios_quilombolas, incra_quilombolas,
                             mma_unidades_conservacao)
from pipeline.validacao import ErroDeValidacao, ResultadoFonte
from test_prediagnostico import DENTRO, FORA, X0, Y0, alertas, car, embargos, lista_suja, prodes, situacoes

PRJ_SIRGAS = 'GEOGCS["GCS_SIRGAS_2000",DATUM["D_SIRGAS_2000"]]'
# Área protegida grande que cobre o CAR inteiro, e uma que só encosta na borda leste (faixa de ~5 m).
COBRE = shapely.box(X0 - 0.05, Y0 - 0.05, X0 + 0.05, Y0 + 0.05)
BORDA = shapely.box(X0 + 0.01 - 0.00005, Y0 - 0.05, X0 + 0.06, Y0 + 0.05)


# --- Fontes -------------------------------------------------------------------------------------------------------

def feicao_ti(codigo, fase="Regularizada", geometria=COBRE, data="05/09/2023", uf="MG"):
    return {"type": "Feature", "geometry": shapely.geometry.mapping(geometria) if geometria else None,
            "properties": {"terrai_codigo": codigo, "terrai_nome": f"TI {codigo}", "etnia_nome": "Etnia",
                           "fase_ti": fase, "modalidade_ti": "Tradicionalmente ocupada", "uf_sigla": uf,
                           "municipio_nome": "Município", "superficie_perimetro_ha": 1000.0,
                           "data_atualizacao": data}}


def resposta_ti(feicoes, anunciado=None):
    return {"type": "FeatureCollection", "features": feicoes,
            "numberMatched": len(feicoes) if anunciado is None else anunciado,
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}}}


def test_ti_sem_geometria_e_codigo_repetido_sao_descartados_e_data_ausente_e_alerta():
    r = ResultadoFonte("funai", "teste")
    saida, descartados = funai_terras_indigenas.transformar(resposta_ti([
        feicao_ti(1), feicao_ti(1), feicao_ti(2, geometria=None), feicao_ti(3, data=""),
        feicao_ti(4, fase="Outra", uf="XX,MG")]), r)
    assert saida["terrai_codigo"].tolist() == ["1", "3", "4"] and len(descartados) == 2
    assert ocorrencias(r, "TI_DATA_ATUALIZACAO_AUSENTE") == 1
    assert ocorrencias(r, "TI_FASE_FORA_DO_DOMINIO") == 1 and ocorrencias(r, "TI_UF_INVALIDA") == 1


def test_ti_resposta_incompleta_interrompe():
    with pytest.raises(ErroDeValidacao, match="TI_RESPOSTA_INCOMPLETA"):
        funai_terras_indigenas.transformar(resposta_ti([feicao_ti(1)], anunciado=665),
                                           ResultadoFonte("funai", "teste"))


def camada_cnuc(*linhas):
    """linhas: (código, categoria, grupo, geometria, qualidade)."""
    registros = [{"cd_cnuc": c, "nome_uc": f"UC {c}", "categoria": cat, "grupo": g, "esfera": "Estadual", "uf": "MG",
                  "org_gestor": "Órgão", "cria_ano": "07-11-1983", "quali_pol": q} for c, cat, g, _, q in linhas]
    return registros, np.array([geo for *_, geo, _ in linhas], dtype=object), PRJ_SIRGAS, 0


def pontos_cnuc(*linhas):
    registros = [{"codigo_uc": c, "nome_uc": f"UC {c}", "categoria": "Parque", "grupo": "PI", "esfera": "estadual",
                  "org_gestor": "Órgão\xa0", "ano_criaca": "2001", "qualidade": "Esquemático"} for c, _ in linhas]
    return registros, np.array([geo for _, geo in linhas], dtype=object), PRJ_SIRGAS, 0


def test_cnuc_junta_poligonos_e_pontos_e_marca_esquematico_e_so_ponto():
    r = ResultadoFonte("cnuc", "teste")
    saida, descartados = mma_unidades_conservacao.transformar(
        camada_cnuc(("1", "Parque", "Proteção Integral", COBRE, "Polígono corresponde ao memorial descritivo"),
                    ("2", "Área de Proteção Ambiental", "Uso Sustentável", COBRE,
                     "Polígono é uma representação esquemática da localização da UC"),
                    ("3", "Parque", "Proteção Integral", None, "")),
        pontos_cnuc(("4", shapely.Point(X0, Y0))), r)
    assert saida["cd_cnuc"].tolist() == ["1", "2", "4"] and len(descartados) == 1
    assert saida.set_index("cd_cnuc").at["4", "grupo"] == "Proteção Integral"
    assert ocorrencias(r, "UC_SO_PONTO") == 1 and ocorrencias(r, "UC_POLIGONO_ESQUEMATICO") == 1


def test_cnuc_em_outro_sistema_de_referencia_interrompe():
    registros, geoms, _, n = camada_cnuc(("1", "Parque", "Proteção Integral", COBRE, ""))
    with pytest.raises(ErroDeValidacao, match="UC_CRS_INESPERADO"):
        mma_unidades_conservacao.transformar((registros, geoms, 'GEOGCS["SAD69"]', n), pontos_cnuc(),
                                             ResultadoFonte("cnuc", "teste"))


def test_cnuc_escolhe_o_shapefile_mais_recente_com_endereco_estavel():
    pacote = {"result": {"resources": [
        {"name": "2025_03", "format": "zip + shp", "created": "2025-05-15", "url": "https://dados.mma.gov.br/a.zip"},
        {"name": "2025_08", "format": "zip + shp", "created": "2025-09-03", "url": "https://dados.mma.gov.br/b.zip"},
        {"name": "2026_07", "format": "zip + shp", "created": "2026-08-21", "url": "https://x.sharepoint.com/c"},
        {"name": "csv", "format": "CSV", "created": "2026-08-21", "url": "https://dados.mma.gov.br/d.csv"}]}}
    assert mma_unidades_conservacao.escolher_recurso(pacote)["name"] == "2025_08"


def test_quilombola_com_situacao_fora_do_dominio_e_alerta():
    registros = [{"COD_TQ": "1", "NOM_TQ": "A", "STATUS": "TITULADO", "SG_UF": "MG"},
                 {"COD_TQ": "2", "NOM_TQ": "B", "STATUS": "OUTRO", "SG_UF": "MG"}]
    r = ResultadoFonte("tq", "teste")
    saida, _ = ibge_territorios_quilombolas.transformar(
        (registros, np.array([COBRE, FORA], dtype=object), PRJ_SIRGAS, 0), r)
    assert len(saida) == 2 and ocorrencias(r, "TQ_SITUACAO_FORA_DO_DOMINIO") == 1
    assert str(saida.at[0, "data_referencia"].date()) == "2022-07-31"


# --- Critérios no pré-diagnóstico --------------------------------------------------------------------------------

def ti(*linhas):
    """linhas: (código, fase, geometria)."""
    return pd.DataFrame([{"terrai_codigo": c, "nome": f"TI {c}", "etnia": "Etnia", "fase": f, "modalidade": "",
                          "uf": "MG", "municipio": "", "superficie_ha": 1.0,
                          "data_atualizacao": pd.Timestamp("2023-09-05"), "geometria_wkt": g.wkt, "alertas": ""}
                         for c, f, g in linhas], columns=funai_terras_indigenas.COLUNAS_SAIDA)


def uc(*linhas):
    """linhas: (código, categoria, grupo, geometria)."""
    return pd.DataFrame([{"cd_cnuc": c, "nome": f"UC {c}", "categoria": cat, "grupo": g, "esfera": "Estadual",
                          "uf": "MG", "orgao_gestor": "", "ano_criacao": 2000,
                          "qualidade_poligono": "Polígono corresponde ao memorial descritivo",
                          "so_ponto": geo.geom_type == "Point", "geometria_wkt": geo.wkt, "alertas": ""}
                         for c, cat, g, geo in linhas], columns=mma_unidades_conservacao.COLUNAS_SAIDA)


def tq(*linhas, base="INCRA"):
    """Camada combinada (INCRA e IBGE 2022): linhas (código, situação, geometria)."""
    return pd.DataFrame([{"codigo": c, "nome": f"Território {c}", "situacao": s, "uf": "MG", "base": base,
                          "data_referencia": pd.Timestamp("2026-10-28"), "geometria_wkt": g.wkt, "alertas": ""}
                         for c, s, g in linhas], columns=incra_quilombolas.COLUNAS_SAIDA)


def com_protegidas(**camadas):
    """Ficha de um CAR sem nada nas outras fontes, com as camadas dadas (None = fonte não carregada)."""
    protegidas = {k: None if v is None else (v, None) for k, v in camadas.items()}
    return prediagnostico.diagnosticar(car(), embargos(), alertas(), lista_suja(), prodes(), ultimo_ano_prodes=2025,
                                       protegidas=protegidas)


@pytest.mark.parametrize("fase, esperado", [("Regularizada", "pendência"), ("Declarada", "pendência"),
                                            ("Em Estudo", "indício")])
def test_terra_indigena_sobre_o_car(fase, esperado):
    ficha = com_protegidas(terra_indigena=ti(("1", fase, COBRE)))
    assert situacoes(ficha)["terra_indigena"] == esperado
    assert ficha["evidencias"]["terra_indigena"].at[0, "fracao_car"] == pytest.approx(1.0)


def test_terra_indigena_so_na_borda_nao_conta():
    ficha = com_protegidas(terra_indigena=ti(("1", "Regularizada", BORDA)))
    criterio = next(c for c in ficha["criterios"] if c["chave"] == "terra_indigena")
    assert criterio["situacao"] == "sem ocorrência" and "1 só na borda" in criterio["evidencia"]


@pytest.mark.parametrize("categoria, grupo, esperado", [
    ("Parque", "Proteção Integral", "pendência"), ("Floresta", "Uso Sustentável", "pendência"),
    ("Área de Proteção Ambiental", "Uso Sustentável", "indício"),
    ("Reserva Particular do Patrimônio Natural", "Uso Sustentável", "indício")])
def test_unidade_de_conservacao_por_categoria(categoria, grupo, esperado):
    ficha = com_protegidas(unidade_conservacao=uc(("1", categoria, grupo, COBRE)))
    assert situacoes(ficha)["unidade_conservacao"] == esperado


def test_uc_so_com_ponto_dentro_do_car_e_indicio():
    ficha = com_protegidas(unidade_conservacao=uc(("1", "Parque", "Proteção Integral", shapely.Point(X0 + 0.003,
                                                                                                    Y0 + 0.003))))
    assert situacoes(ficha)["unidade_conservacao"] == "indício"


@pytest.mark.parametrize("situacao, esperado", [("TITULADO", "pendência"), ("RTID", "pendência"),
                                                  ("PORTARIA", "pendência"), ("ESTUDO TÉCNICO", "indício"),
                                                  ("TITULO ANULADO", "indício"), ("FASE NÃO INFORMADA", "indício")])
def test_quilombola_delimitado_e_pendencia_e_em_estudo_ou_sem_fase_e_indicio(situacao, esperado):
    ficha = com_protegidas(quilombola=tq(("1", situacao, DENTRO)))
    assert situacoes(ficha)["quilombola"] == esperado
    criterio = next(c for c in ficha["criterios"] if c["chave"] == "quilombola")
    assert "base INCRA" in criterio["evidencia"]


# --- INCRA (CMR/FUNAI) e camada combinada --------------------------------------------------------------------------

def feicao_qi(i, fase="RTID", geometria=COBRE, processo="54100.000001/2020-01"):
    return {"type": "Feature", "id": f"lim_quilombolas_a.{i}",
            "geometry": shapely.geometry.mapping(geometria) if geometria else None,
            "properties": {"no_comunidade": f"Comunidade {i}", "ds_fase": fase, "sg_uf": "MG",
                           "no_municipio": "Município", "nu_processo": processo, "co_sr": "SR-06",
                           "nu_area_ha": 10.0, "dt_publica": None, "dt_cadastro": "2026-10-28T16:40:03Z"}}


def test_incra_fase_em_branco_vira_indicio_e_caixa_e_normalizada():
    r = ResultadoFonte("incra", "teste")
    saida, descartados = incra_quilombolas.transformar(resposta_ti([
        feicao_qi(1), feicao_qi(2, fase=None), feicao_qi(3, fase="titulado"), feicao_qi(4, fase="OUTRA"),
        feicao_qi(5, geometria=None), feicao_qi(6, processo=None)]), r)
    assert saida["situacao"].tolist() == ["RTID", "FASE NÃO INFORMADA", "TITULADO", "OUTRA", "RTID"]
    assert len(descartados) == 1
    assert [ocorrencias(r, c) for c in ("QI_FASE_AUSENTE", "QI_FASE_CAIXA_DIFERENTE", "QI_FASE_FORA_DO_DOMINIO",
                                        "QI_PROCESSO_AUSENTE")] == [1, 1, 1, 1]
    assert str(saida.at[0, "data_cadastro"].date()) == "2026-10-28"


def test_incra_resposta_incompleta_interrompe():
    with pytest.raises(ErroDeValidacao, match="QI_RESPOSTA_INCOMPLETA"):
        incra_quilombolas.transformar(resposta_ti([feicao_qi(1)], anunciado=2), ResultadoFonte("incra", "teste"))


def test_combinada_fica_com_o_incra_e_o_territorio_que_so_o_ibge_tem():
    r = ResultadoFonte("incra", "teste")
    incra, _ = incra_quilombolas.transformar(resposta_ti([feicao_qi(1, geometria=COBRE)]), r)
    so_ibge = shapely.box(X0 + 1, Y0, X0 + 1.01, Y0 + 0.01)
    # O território 1 do IBGE é o mesmo do INCRA (desenho um pouco diferente); o 2 só existe no IBGE.
    ibge, _ = ibge_territorios_quilombolas.transformar(
        ([{"COD_TQ": "1", "NOM_TQ": "A", "STATUS": "TITULADO", "SG_UF": "MG"},
          {"COD_TQ": "2", "NOM_TQ": "B", "STATUS": "ESTUDO TÉCNICO", "SG_UF": "MG"}],
         np.array([COBRE.buffer(-0.001), so_ibge], dtype=object), PRJ_SIRGAS, 0), r)
    combinada = incra_quilombolas.combinar(incra, ibge, r)
    assert combinada["codigo"].tolist() == ["INCRA:lim_quilombolas_a.1", "IBGE:2"]
    assert combinada["base"].tolist() == ["INCRA", "IBGE 2022"] and ocorrencias(r, "QUILOMBOLA_NAS_DUAS_BASES") == 1


def test_fonte_nao_carregada_e_inconclusiva_e_impede_sem_pendencia():
    ficha = com_protegidas(terra_indigena=None)
    assert situacoes(ficha)["terra_indigena"] == "inconclusivo"
    assert ficha["resultado"]["situacao"] == "inconclusivo"


def test_pendencia_continua_aparecendo_com_outro_criterio_inconclusivo():
    ficha = com_protegidas(terra_indigena=None, unidade_conservacao=uc(("1", "Parque", "Proteção Integral", COBRE)))
    assert ficha["resultado"]["situacao"] == "com pendência"
    assert "1 critério(s) inconclusivo(s)" in ficha["resultado"]["resumo"]


def test_prodes_que_nao_respondeu_deixa_o_desmatamento_inconclusivo():
    ficha = prediagnostico.diagnosticar(car(), embargos(), alertas(("a1", DENTRO, "2023-09-10")), lista_suja(),
                                        prodes(), falha_prodes="PRODES indisponível em 2026-10-30 (HTTPError)")
    assert situacoes(ficha)["desmatamento"] == "inconclusivo"
    assert ficha["resultado"]["situacao"] == "inconclusivo"


def test_bioma_sem_deter_fica_sem_ocorrencia_com_aviso_de_cobertura():
    aviso = prediagnostico.aviso_cobertura(["mata_atlantica"], {"mata_atlantica": "2025-10-16"})
    assert aviso.startswith("Mata Atlântica sem DETER: sem cobertura de 16/10/2025 até hoje")
    assert prediagnostico.aviso_cobertura(["cerrado"], {"cerrado": "2026-08-12"}) is None
    ficha = prediagnostico.diagnosticar(car(), embargos(), alertas(), lista_suja(), prodes(),
                                        aviso_desmatamento=aviso)
    criterio = next(c for c in ficha["criterios"] if c["chave"] == "desmatamento")
    assert criterio["situacao"] == "sem ocorrência" and criterio["aviso"] == aviso
    assert ficha["resultado"]["situacao"] == "sem pendência nas fontes verificadas"
