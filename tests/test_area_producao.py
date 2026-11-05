"""Área de produção (EUDR): leitura do KML e do GeoJSON, cruzamento do desmatamento com ela, avisos e gravação em
cad.area_producao. Sem rede: a consulta da carteira é falsa e as fixtures são sintéticas (tests/dados/area_producao)."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import shapely

from conftest import CPF_VALIDO
from pipeline import cadastro, carteira, prediagnostico, vetor
from pipeline.armazenamento import lago
from test_prediagnostico import CAR, X0, Y0, alertas, car, embargos, lista_suja, prodes

DADOS = Path(__file__).parent / "dados" / "area_producao"
NO_TALHAO = shapely.box(X0 + 0.0025, Y0 + 0.0025, X0 + 0.0035, Y0 + 0.0035)  # dentro do talhão do KML, fora do furo
SO_NO_CAR = shapely.box(X0 + 0.007, Y0 + 0.007, X0 + 0.009, Y0 + 0.009)  # no imóvel, fora do talhão


def _area(geom, arquivo="talhao.kml"):
    return {"geometria": geom, "arquivo": arquivo, "crs": "WGS 84", "motivo": None}


def _ficha(area=None, *alerta):
    return prediagnostico.diagnosticar(car(), embargos(), alertas(*alerta), lista_suja(), prodes(),
                                       ultimo_ano_prodes=2025, area_producao=area)


def _desmatamento(ficha):
    return next(c for c in ficha["criterios"] if c["chave"] == "desmatamento")


# --- leitura --------------------------------------------------------------------------------------------------------

def test_kml_vira_multipolygon_4674_com_furo_e_ignora_o_ponto():
    geom, crs = vetor.ler_area_producao(DADOS / "talhao.kml")
    assert geom.geom_type == "MultiPolygon" and len(geom.geoms) == 1 and crs == "WGS 84"
    assert len(geom.geoms[0].interiors) == 1 and geom.within(CAR)


def test_geojson_com_crs_sirgas_2000_e_multipolygon():
    geom, crs = vetor.ler_area_producao(DADOS / "talhoes.geojson")
    assert geom.geom_type == "MultiPolygon" and len(geom.geoms) == 2 and crs == "SIRGAS 2000"


@pytest.mark.parametrize("nome, conteudo, motivo", [
    ("utm.geojson", {"type": "Feature", "crs": {"type": "name", "properties": {"name": "EPSG:31983"}},
                     "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
     "EPSG:31983 não aceito"),
    ("metros.geojson", {"type": "Polygon", "coordinates": [[[500000, 7900000], [500100, 7900000],
                                                            [500100, 7900100], [500000, 7900000]]]},
     "fora do Brasil"),
    ("ponto.geojson", {"type": "Point", "coordinates": [-46.98, -18.94]}, "nenhum Polygon ou MultiPolygon"),
    ("quebrado.kml", "<kml><Document><Polygon>", "KML mal formado"),
    ("quebrado.geojson", "{não é json", "GeoJSON mal formado"),
    ("talhao.shp", "x", "formato .shp não aceito"),
])
def test_arquivo_ilegivel_diz_o_motivo(tmp_path, nome, conteudo, motivo):
    arquivo = tmp_path / nome
    arquivo.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8")
    with pytest.raises(vetor.AreaIlegivel, match=motivo):
        vetor.ler_area_producao(arquivo)


def test_caminho_relativo_a_planilha_e_sem_sair_da_pasta(tmp_path):
    pasta = tmp_path / "planilhas"
    (pasta / "talhoes").mkdir(parents=True)
    shutil.copy(DADOS / "talhao.kml", pasta / "talhoes" / "talhao.kml")
    shutil.copy(DADOS / "talhao.kml", tmp_path / "fora.kml")
    lida = carteira.area_producao("talhoes\\talhao.kml", pasta)
    assert lida["motivo"] is None and lida["arquivo"] == "talhoes/talhao.kml" and lida["crs"] == "WGS 84"
    for caminho in ("../fora.kml", str(tmp_path / "fora.kml")):
        fora = carteira.area_producao(caminho, pasta)
        assert fora["geometria"] is None and "fora da pasta da planilha" in fora["motivo"]
    assert "não encontrado" in carteira.area_producao("talhoes/nao_existe.kml", pasta)["motivo"]
    assert carteira.area_producao(None, pasta) is None


# --- cruzamento -----------------------------------------------------------------------------------------------------

def test_desmatamento_cruza_a_area_de_producao_e_diz_qual_poligono():
    talhao, _ = vetor.ler_area_producao(DADOS / "talhao.kml")
    alerta_fora_do_talhao = ("a1", SO_NO_CAR, "2024-06-01")
    assert _desmatamento(_ficha(None, alerta_fora_do_talhao))["situacao"] == "indício"  # imóvel inteiro: conta

    ficha = _ficha(_area(talhao), alerta_fora_do_talhao)
    crit = _desmatamento(ficha)
    assert crit["situacao"] == "sem ocorrência" and crit["aviso"] is None
    assert "dentro da área de produção · cruzado com a área de produção (talhao.kml" in crit["evidencia"]
    assert ficha["area_producao"]["usada"] and ficha["area_producao"]["fracao_fora_do_car"] == 0

    crit = _desmatamento(_ficha(_area(talhao), ("a2", NO_TALHAO, "2024-06-01")))
    assert crit["situacao"] == "indício" and "ha na área de produção" in crit["evidencia"]


def test_area_fora_do_car_ou_mais_de_5_por_cento_fora_gera_aviso():
    metade_fora = shapely.MultiPolygon([shapely.box(X0 + 0.008, Y0 + 0.002, X0 + 0.012, Y0 + 0.004)])
    crit = _desmatamento(_ficha(_area(metade_fora)))
    assert crit["aviso"].startswith("50% da área de produção fora do imóvel do CAR")
    longe = shapely.MultiPolygon([shapely.box(X0 + 0.5, Y0, X0 + 0.51, Y0 + 0.01)])
    assert _desmatamento(_ficha(_area(longe)))["aviso"].startswith("área de produção fora do imóvel do CAR")
    quase_toda_dentro = shapely.MultiPolygon([shapely.box(X0 + 0.002, Y0 + 0.002, X0 + 0.0102, Y0 + 0.004)])
    assert _desmatamento(_ficha(_area(quase_toda_dentro)))["aviso"] is None  # ~2% fora: tolerado


def test_area_nao_lida_vira_aviso_e_o_cruzamento_volta_ao_imovel():
    area = {"geometria": None, "arquivo": "x.kml", "crs": None, "motivo": "KML mal formado (linha 1)"}
    crit = _desmatamento(_ficha(area, ("a1", SO_NO_CAR, "2024-06-01")))
    assert crit["aviso"] == "área de produção não lida: KML mal formado (linha 1); o cruzamento foi com o imóvel inteiro"
    assert crit["situacao"] == "indício" and crit["evidencia"].endswith("cruzado com o imóvel inteiro (CAR)")


# --- carteira e cadastro --------------------------------------------------------------------------------------------

def _consultar(chamadas):
    def consultar(cod, lat, lon, documento, baixar_prodes=True, area_producao=None):
        chamadas.append(area_producao)
        ficha = _ficha(area_producao, ("a1", SO_NO_CAR, "2024-06-01"))
        ficha["imovel"] = {**ficha["imovel"], "cod_imovel": cod}
        return {"consulta": {"gerado_em": "2026-11-05 10:00:00", "prodes": {}, "documento_informado": True}, **ficha,
                "procedencia": []}
    return consultar


def test_carteira_grava_a_area_em_cad_e_arquivo_ilegivel_nao_derruba(tmp_path):
    pasta = tmp_path / "planilha"
    pasta.mkdir()
    for nome in ("talhao.kml", "talhoes.geojson"):
        shutil.copy(DADOS / nome, pasta / nome)
    (pasta / "ruim.kml").write_text("<kml>", encoding="utf-8")
    arquivo = pasta / "carteira.csv"
    df = pd.DataFrame([
        {"id_produtor": "P1", "cod_car": "MG-1", "documento": CPF_VALIDO, "commodity": "café",
         "area_producao": "talhao.kml"},
        {"id_produtor": "P2", "cod_car": "MG-2", "documento": None, "commodity": "soja",
         "area_producao": "talhoes.geojson"},
        {"id_produtor": "P3", "cod_car": "MG-3", "documento": None, "commodity": None, "area_producao": "ruim.kml"},
        {"id_produtor": "P4", "cod_car": "MG-4", "documento": None, "commodity": None, "area_producao": None}])
    df.to_csv(arquivo, index=False)
    org = cadastro.organizacao("Coop Área")
    areas = carteira.areas_de_producao(df, pasta)
    assert sorted(areas) == [0, 1, 2] and areas[2]["motivo"].startswith("KML mal formado")
    _, ids = cadastro.importar_carteira(df, org, arquivo, areas=areas)
    cadastro.importar_carteira(df, org, arquivo, areas=areas)  # mês seguinte: a mesma área não se repete

    gravadas = lago.ler("cad.area_producao").sort_values("commodity")
    assert len(gravadas) == 2 and set(gravadas["organizacao_id"]) == {org}
    assert gravadas["commodity"].tolist() == ["café", "soja"]
    assert gravadas["imovel_id"].tolist() == [ids[0]["imovel_id"], ids[1]["imovel_id"]]
    assert gravadas["origem"].tolist() == ["planilha carteira.csv: talhao.kml (WGS 84)",
                                           "planilha carteira.csv: talhoes.geojson (SIRGAS 2000)"]
    assert shapely.from_wkt(gravadas["geometria_wkt"].iloc[0]).geom_type == "MultiPolygon"

    chamadas = []
    saida = carteira.processar(df, tmp_path / "saida", consultar=_consultar(chamadas), areas=areas)
    assert len(saida) == 4 and chamadas[3] is None and saida["problema_na_linha"].isna().all()
    por_produtor = saida.set_index("id_produtor")
    assert por_produtor.at["P1", "resultado"] == "sem pendência nas fontes verificadas"  # alerta fora do talhão
    assert por_produtor.at["P3", "aviso_area_producao"].startswith("área de produção não lida: KML mal formado")
    assert pd.isna(por_produtor.at["P4", "aviso_area_producao"])
    textos = [p.read_text(encoding="utf-8") for p in (tmp_path / "saida" / "fichas").iterdir()]
    assert any("área de produção não lida" in t for t in textos)
    for texto in [*textos, gravadas.to_csv(), saida.to_csv()]:
        assert CPF_VALIDO not in texto and "11144477735" not in texto


def test_sem_a_coluna_nada_muda(tmp_path):
    df = pd.DataFrame([{"id_produtor": "P1", "cod_car": "MG-1"}])
    assert carteira.areas_de_producao(df, tmp_path) == {}
    chamadas = []
    consultar = lambda cod, lat, lon, doc, baixar_prodes=True: chamadas.append(cod) or _consultar([])(cod, lat, lon, doc)
    saida = carteira.processar(df, tmp_path, consultar=consultar, areas={})
    assert chamadas == ["MG-1"] and "aviso_area_producao" not in saida
    assert "area_producao" not in _ficha(None)
    assert _desmatamento(_ficha(None))["evidencia"] == "Nenhum alerta DETER nem polígono PRODES após 2020 dentro do imóvel"
