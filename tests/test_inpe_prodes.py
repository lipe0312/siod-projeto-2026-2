import pandas as pd
import pytest
import shapely

from conftest import ocorrencias
from pipeline.fontes import inpe_prodes
from pipeline.validacao import ErroDeValidacao, ResultadoFonte

X0, Y0 = -46.99, -18.95
FIM_2025 = pd.Timestamp("2025-07-31")


def quadrado(x, y, lado=0.01):
    return {"type": "MultiPolygon", "coordinates": [[[[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]]]}


def poligono(uuid, ano=2022, data="2022-07-20", classe="DESMATAMENTO", uf="MINAS GERAIS", geometria=None, area=None):
    geometria = geometria or quadrado(X0, Y0)
    if area is None:
        area = inpe_prodes.area_km2(shapely.geometry.shape(geometria))
    props = {"uuid": uuid, "state": uf, "main_class": classe, "class_name": f"d{ano}", "year": ano,
             "image_date": data, "publish_year": f"{ano}-01-01", "area_km": area, "satellite": "Sentinel-2",
             "sensor": "MSI"}
    return {"type": "Feature", "id": f"yearly_deforestation.{uuid}", "geometry": geometria, "properties": props}


def resposta(features, anunciado=None):
    return {"type": "FeatureCollection", "features": features,
            "numberMatched": len(features) if anunciado is None else anunciado,
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}}}


def processar(*respostas):
    resultado = ResultadoFonte("inpe_prodes", "teste")
    saida, descartados = inpe_prodes.transformar(list(respostas), "cerrado", resultado)
    return saida, descartados, resultado


def test_classe_fora_do_dominio_e_uuid_repetido_sao_descartados():
    saida, descartados, r = processar(resposta([poligono("a"), poligono("a"), poligono("b", classe="RESERVATORIO")]))
    assert saida["uuid"].tolist() == ["a"]
    assert sorted(descartados["motivo"]) == ["PRODES_CLASSE_FORA_DO_DOMINIO", "PRODES_UUID_DUPLICADO"]


def test_uf_por_extenso_vira_sigla():
    saida, _, r = processar(resposta([poligono("a"), poligono("b", uf="MG")]))
    assert saida["uf"].tolist() == ["MG", "MG"] and ocorrencias(r, "PRODES_UF_NORMALIZADA") == 1


def test_imagem_fora_do_ano_prodes_e_alerta_e_publish_year_e_ignorado():
    saida, _, r = processar(resposta([poligono("a", ano=2022, data="2022-08-15"), poligono("b", data="2022-07-20")]))
    assert ocorrencias(r, "PRODES_DATA_FORA_DO_ANO_PRODES") == 1
    assert saida.loc[0, "alertas"] == "DATA_FORA_DO_ANO_PRODES" and "publish_year" not in saida
    assert any("publish_year ignorado" in t for t in r.transformacoes)


def test_particao_incompleta_interrompe():
    with pytest.raises(ErroDeValidacao, match="PRODES_PARTICAO_INCOMPLETA"):
        processar(resposta([poligono("a")], anunciado=5))


def test_filtro_por_bbox_usa_lat_lon_e_uf_por_extenso_no_cerrado():
    assert inpe_prodes.filtro(2021, (-47.0, -19.0, -46.5, -18.5), "MG", "cerrado") == \
        "BBOX(geom,-19.0,-47.0,-18.5,-46.5) AND state='MINAS GERAIS' AND year=2021"
    assert inpe_prodes.filtro(2021, uf="MG", bioma="mata_atlantica") == "state='MG' AND year=2021"


def test_consulta_sem_recorte_e_recusada():
    with pytest.raises(ValueError):
        inpe_prodes.consultar("cerrado")


@pytest.mark.parametrize("posterior, anterior, data, esperado", [
    (0.50, 0.00, "2023-03-01", "confirmado"),
    (0.05, 0.80, "2023-03-01", "já suprimido antes"),
    (0.05, 0.05, "2023-03-01", "não confirmado"),
    (0.00, 0.00, "2025-09-01", "aguardando consolidação"),
])
def test_regra_de_confirmacao(posterior, anterior, data, esperado):
    assert inpe_prodes.classificar_alerta(posterior, anterior, pd.Timestamp(data), FIM_2025) == esperado


def test_confirmar_alertas_com_poligonos():
    def wkt(x, lado=0.01):
        return shapely.box(X0 + x, Y0, X0 + x + lado, Y0 + lado).wkt

    prodes = pd.DataFrame({
        "uuid": ["p1", "p2", "p3"], "ano_prodes": [2023, 2021, 2025],
        "data_imagem": pd.to_datetime(["2023-07-20", "2021-07-20", "2025-07-20"]),
        "geometria_wkt": [wkt(0), wkt(0.1), wkt(0.5)]})
    alertas = pd.DataFrame({
        "id_alerta": ["confirmado", "antes", "nao", "aguardando", "sem_area"],
        "data_imagem": pd.to_datetime(["2023-03-01", "2023-03-01", "2023-03-01", "2025-09-01", "2023-03-01"]),
        "geometria_wkt": [wkt(0), wkt(0.1), wkt(0.3), wkt(0.3), "LINESTRING (-46.9 -18.9, -46.8 -18.9)"]})
    situacao = inpe_prodes.confirmar_alertas(alertas, prodes).set_index("id_alerta")["situacao"]
    assert situacao.to_dict() == {"confirmado": "confirmado", "antes": "já suprimido antes", "nao": "não confirmado",
                                  "aguardando": "aguardando consolidação", "sem_area": "geometria sem área"}


def test_ano_prodes_comeca_em_agosto():
    assert inpe_prodes.ano_prodes(pd.Series(["2020-07-31", "2020-08-01"])).tolist() == [2020, 2021]
