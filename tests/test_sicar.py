import json
import ssl

import pandas as pd
import pytest
import shapely

from conftest import ocorrencias
from pipeline import config, wfs
from pipeline.fontes import sicar
from pipeline.validacao import ErroDeValidacao, ResultadoFonte

# Imóveis fictícios em Patrocínio (MG). Códigos no formato UF-IBGE-32 hexadecimais.
X0, Y0 = -46.99, -18.95


def quadrado(x, y, lado=0.01):
    return {"type": "MultiPolygon", "coordinates": [[[[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]]]}


def imovel(n, geometria=None, status="AT", area=None, municipio=3148103, codigo=None):
    geometria = geometria or quadrado(X0 + 0.02 * n, Y0)
    if area is None:
        area = float(sicar.area_ha(shapely.from_geojson(json.dumps(geometria))))
    props = {"cod_imovel": codigo or f"MG-{municipio}-{n:032X}", "status_imovel": status,
             "dat_criacao": "2015-06-04T00:26:59.605Z", "data_atualizacao": "2025-03-06T02:02:07.028Z",
             "area": area, "condicao": "Aguardando análise", "uf": "MG", "municipio": "Patrocínio",
             "cod_municipio_ibge": municipio, "m_fiscal": 1.0, "tipo_imovel": "IRU"}
    return {"type": "Feature", "id": f"sicar_imoveis_mg.{n}", "geometry": geometria, "properties": props}


def resposta(features, anunciado=None, crs="urn:ogc:def:crs:EPSG::4674"):
    return {"type": "FeatureCollection", "features": features,
            "numberMatched": len(features) if anunciado is None else anunciado,
            "crs": {"type": "name", "properties": {"name": crs}}}


def processar(*respostas, malhas=None):
    resultado = ResultadoFonte("sicar", "teste")
    saida, descartados = sicar.transformar(list(respostas), resultado, malhas)
    return saida, descartados, resultado


def test_imovel_valido():
    saida, descartados, _ = processar(resposta([imovel(1), imovel(2)]))
    assert len(saida) == 2 and len(descartados) == 0
    assert set(saida["alertas"]) == {""} and saida["cod_municipio"].tolist() == ["3148103", "3148103"]
    assert saida["geometria_wkt"].str.startswith("MULTIPOLYGON").all()


def test_particao_incompleta_interrompe():
    with pytest.raises(ErroDeValidacao, match="CAR_PARTICAO_INCOMPLETA"):
        processar(resposta([imovel(1)], anunciado=2))


def test_crs_inesperado_interrompe():
    with pytest.raises(ErroDeValidacao, match="CAR_CRS_INESPERADO"):
        processar(resposta([imovel(1)], crs="EPSG:4326"))


def test_codigo_invalido_duplicado_e_status_desconhecido_vao_para_descartados():
    feicoes = [imovel(1), imovel(1), imovel(2, codigo="MG-3148103-XYZ"), imovel(3, status="ZZ"), imovel(4)]
    saida, descartados, r = processar(resposta(feicoes))
    assert len(saida) == 2
    assert sorted(descartados["motivo"]) == ["CAR_CODIGO_INVALIDO", "CAR_DUPLICADO", "CAR_STATUS_DESCONHECIDO"]
    assert ocorrencias(r, "CAR_DUPLICADO") == 1


def test_geometria_invalida_e_corrigida():
    gravata = {"type": "Polygon", "coordinates": [[[X0, Y0], [X0 + 0.01, Y0 + 0.01], [X0 + 0.01, Y0], [X0, Y0 + 0.01], [X0, Y0]]]}
    saida, _, r = processar(resposta([imovel(1, geometria=gravata, area=50.0)]))
    assert ocorrencias(r, "CAR_GEOM_INVALIDA") == 1
    assert shapely.is_valid(shapely.from_wkt(saida.loc[0, "geometria_wkt"]))


def test_imovel_dentro_de_outro_e_marcado_como_sobreposto():
    grande = imovel(1, geometria=quadrado(X0, Y0, 0.02))
    contido = imovel(2, geometria=quadrado(X0 + 0.005, Y0 + 0.005, 0.005))
    saida, _, r = processar(resposta([grande, contido, imovel(5)]))
    assert ocorrencias(r, "CAR_SOBREPOSTO_95") == 1
    assert saida.set_index("cod_imovel").loc[contido["properties"]["cod_imovel"], "alertas"] == "SOBREPOSTO_95"


def test_area_declarada_divergente():
    feicoes = [imovel(1), imovel(2), imovel(3), imovel(4, area=500.0)]
    saida, _, r = processar(resposta(feicoes))
    assert ocorrencias(r, "CAR_AREA_DIVERGENTE") == 1 and saida.loc[3, "alertas"] == "AREA_DIVERGENTE"


def test_imovel_fora_do_municipio_declarado():
    municipio = shapely.box(X0 - 0.001, Y0 - 0.001, X0 + 0.03, Y0 + 0.02)
    saida, _, r = processar(resposta([imovel(1), imovel(4)]), malhas={"3148103": municipio})
    assert ocorrencias(r, "CAR_FORA_DO_MUNICIPIO") == 1 and saida.loc[1, "alertas"] == "FORA_DO_MUNICIPIO"


def test_resposta_vazia_nao_quebra():
    saida, descartados, r = processar(resposta([]))
    assert saida.empty and descartados.empty and r.entrada["registros_recebidos"] == 0


def test_ordem_dos_eixos_no_filtro_e_latitude_longitude():
    assert config.ORDEM_EIXOS_FILTRO == ("lat", "lon")
    assert wfs.filtro_bbox("g", (-47.0, -19.0, -46.5, -18.5)) == "BBOX(g,-19.0,-47.0,-18.5,-46.5)"
    assert wfs.filtro_ponto("g", -18.9, -46.9) == "INTERSECTS(g,POINT(-18.9 -46.9))"


def test_adaptador_tls_mantem_verificacao_do_certificado():
    adaptador = sicar.sessao().get_adapter("https://geoserver.car.gov.br/geoserver/sicar/wfs")
    contexto = adaptador.poolmanager.connection_pool_kw["ssl_context"]
    assert isinstance(adaptador, sicar.AdaptadorTLSLegado)
    assert contexto.verify_mode == ssl.CERT_REQUIRED and contexto.check_hostname
    assert contexto.options & ssl.OP_LEGACY_SERVER_CONNECT


@pytest.mark.rede
def test_rede_municipio_real_anunciado_igual_a_recebido(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(config, "DADOS_BRUTOS", tmp_path / "raw")
    saida, r = sicar.consultar_municipio("3129707", atualizar=True)  # Ibiraci (MG)
    requisicao = r.entrada["requisicoes"][0]
    assert requisicao["anunciado"] == requisicao["recebido"] == r.entrada["registros_recebidos"] > 0
    assert len(saida) == requisicao["recebido"]
    assert isinstance(saida, pd.DataFrame)
