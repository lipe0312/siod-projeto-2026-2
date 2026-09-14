import pandas as pd
import pytest

from conftest import HOJE, ocorrencias
from pipeline.fontes import inpe_deter
from pipeline.validacao import ErroDeValidacao, ResultadoFonte

QUADRADO = {"type": "MultiPolygon", "coordinates": [[[[-50.6, -3.8], [-50.5, -3.8], [-50.5, -3.7], [-50.6, -3.7], [-50.6, -3.8]]]]}


def quadrado(deslocamento):
    d = deslocamento / 10
    anel = [[-50.6 + d, -3.8], [-50.5 + d, -3.8], [-50.5 + d, -3.7], [-50.6 + d, -3.7], [-50.6 + d, -3.8]]
    return {"type": "MultiPolygon", "coordinates": [[anel]]}


def feature(gid, municipio="PACAJA", uf="PA", classe="DESMATAMENTO_CR", data="2022-03-01", geocod="1505486",
            area=0.1, geometria=QUADRADO):
    props = {"gid": gid, "classname": classe, "view_date": data, "publish_month": "2022-03-01", "uf": uf,
             "municipality": municipio, "areamunkm": area, "satellite": "AMAZONIA-1", "sensor": "WFI"}
    if geocod is not None:
        props["mun_geocod"] = geocod
    return {"type": "Feature", "id": f"x.{gid}", "geometry": geometria, "properties": props}


def resposta(features, crs="urn:ogc:def:crs:EPSG::4674"):
    return {"type": "FeatureCollection", "features": features, "crs": {"type": "name", "properties": {"name": crs}}}


def processar(ref, amazonia=None, cerrado=None, esperados=None):
    paginas = {k: v for k, v in (("amazonia", amazonia), ("cerrado", cerrado)) if v is not None}
    esperados = esperados or {k: sum(len(r["features"]) for r in v) for k, v in paginas.items()}
    resultado = ResultadoFonte("inpe_deter", "API")
    saida, descartados = inpe_deter.transformar(paginas, esperados, ref, "2021-01-01", HOJE, resultado)
    return saida, descartados, resultado


def test_alerta_valido(ref_municipios):
    saida, descartados, _ = processar(ref_municipios, amazonia=[resposta([feature("1_hist")])])
    r = saida.iloc[0]
    assert r["id_alerta"].startswith("amazonia:1_hist:") and len(r["id_alerta"].split(":")[2]) == 12
    assert r["cod_municipio"] == "1505486"
    assert r["alertas"] == "" and r["geometria_wkt"].startswith("MULTIPOLYGON") and len(descartados) == 0


def test_estrutura_de_resposta_invalida_interrompe(ref_municipios):
    with pytest.raises(ErroDeValidacao, match="DETER_ESTRUTURA_RESPOSTA"):
        processar(ref_municipios, amazonia=[{"type": "FeatureCollection"}], esperados={"amazonia": 0})


def test_crs_inesperado_interrompe(ref_municipios):
    with pytest.raises(ErroDeValidacao, match="DETER_CRS_INESPERADO"):
        processar(ref_municipios, amazonia=[resposta([feature("1")], crs="EPSG:4326")])


def test_propriedade_obrigatoria_ausente_interrompe(ref_municipios):
    f = feature("1")
    del f["properties"]["view_date"]
    with pytest.raises(ErroDeValidacao, match="DETER_PROPRIEDADE_VIEW_DATE_AUSENTE"):
        processar(ref_municipios, amazonia=[resposta([f])])


def test_contagem_divergente_gera_alerta(ref_municipios):
    _, _, res = processar(ref_municipios, amazonia=[resposta([feature("1")])], esperados={"amazonia": 5})
    assert ocorrencias(res, "DETER_CONTAGEM_DIVERGENTE_AMAZONIA") == 1


def test_mesmo_gid_em_municipios_diferentes_nao_e_duplicata(ref_municipios):
    cerrado = [resposta([feature("7", "BELO HORIZONTE", "MG", geocod=None),
                         feature("7", "SANTO ANTONIO DO LEVERGER", "MT", geocod=None),
                         feature("7", "SANTO ANTONIO DO LEVERGER", "MT", geocod=None)])]
    saida, descartados, res = processar(ref_municipios, cerrado=cerrado)
    assert len(saida) == 2 and descartados["motivo"].tolist() == ["DETER_ALERTA_DUPLICADO"]
    assert set(saida["cod_municipio"]) == {"3106200", "5107800"}
    assert ocorrencias(res, "DETER_MUNICIPIO_APELIDO") == 1


def test_descartes_por_classe_data_e_geometria(ref_municipios):
    features = [feature("1", classe="CICATRIZ_DE_QUEIMADA"), feature("2", data="2019-05-01"),
                feature("3", data="2022-13-40"), feature("4", geometria=None),
                feature("5", geometria={"type": "Polygon", "coordinates": [[[10, 10], [11, 10], [11, 11], [10, 10]]]}),
                feature("6")]
    saida, descartados, _ = processar(ref_municipios, amazonia=[resposta(features)])
    assert saida["gid"].tolist() == ["6"]
    assert descartados.sort_values("gid")["motivo"].tolist() == [
        "DETER_CLASSE_FORA_DO_RECORTE", "DETER_DATA_FORA_DO_RECORTE", "DETER_DATA_INVALIDA",
        "DETER_GEOM_AUSENTE", "DETER_GEOM_FORA_BRASIL"]


def test_alertas_de_municipio_area_e_geometria(ref_municipios):
    laco = {"type": "Polygon", "coordinates": [[[-50.6, -3.8], [-50.5, -3.7], [-50.5, -3.8], [-50.6, -3.7], [-50.6, -3.8]]]}
    features = [feature("1", geocod="2927408", geometria=quadrado(1)),
                feature("2", municipio="LUGAR NENHUM", geocod=None, geometria=quadrado(2)),
                feature("3", area=0, geometria=quadrado(3)), feature("4", geometria=laco)]
    saida, _, _ = processar(ref_municipios, amazonia=[resposta(features)])
    alertas = saida.set_index("gid")["alertas"]
    assert alertas["1"] == "MUNICIPIO_CODIGO_DIVERGENTE"
    assert alertas["2"] == "MUNICIPIO_NAO_IDENTIFICADO"
    assert alertas["3"] == "AREA_NAO_POSITIVA" and pd.isna(saida.set_index("gid").loc["3", "area_km2"])
    assert alertas["4"] == "GEOM_INVALIDA"


def test_geometria_repetida_em_gids_diferentes(ref_municipios):
    saida, _, res = processar(ref_municipios, amazonia=[resposta([feature("1"), feature("2")])])
    assert ocorrencias(res, "DETER_GEOMETRIA_REPETIDA") == 2


def test_gid_ausente_descartado_e_uf_invalida_marcada(ref_municipios):
    features = [feature(None, geometria=quadrado(1)), feature("2", uf="XX", geometria=quadrado(2))]
    saida, descartados, res = processar(ref_municipios, amazonia=[resposta(features)])
    assert descartados["motivo"].tolist() == ["DETER_GID_AUSENTE"]
    assert ocorrencias(res, "DETER_UF_INVALIDA") == 1
    assert "UF_INVALIDA" in saida.set_index("gid").loc["2", "alertas"]


def test_gid_reutilizado_em_outra_data_nao_e_duplicata(ref_municipios):
    features = [feature("9_hist", data="2021-07-01", geometria=quadrado(1)),
                feature("9_hist", data="2023-02-01", geometria=quadrado(5))]
    saida, descartados, _ = processar(ref_municipios, amazonia=[resposta(features)])
    assert len(saida) == 2 and saida["id_alerta"].nunique() == 2 and len(descartados) == 0


def test_particao_incompleta_interrompe(ref_municipios):
    parcial = resposta([feature("1")])
    parcial["numberMatched"] = 3
    with pytest.raises(ErroDeValidacao, match="DETER_PARTICAO_INCOMPLETA"):
        processar(ref_municipios, amazonia=[parcial], esperados={"amazonia": 3})


def test_particoes_mensais_cobrem_todo_o_periodo():
    assert inpe_deter.particoes_mensais("2021-01-15", pd.Timestamp("2021-03-10")) == [
        ("2021-01-15", "2021-02-01"), ("2021-02-01", "2021-03-01"), ("2021-03-01", "2021-04-01")]
