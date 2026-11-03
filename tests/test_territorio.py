"""Referência territorial: UF e bioma pelo contorno, com contornos fictícios (sem rede)."""

import json

import pandas as pd
import pytest
import shapely

from apoio_lago import relogio_que_avanca
from pipeline import config, territorio
from pipeline.armazenamento import lago
from pipeline.fontes import sicar
from pipeline.validacao import ErroDeValidacao, ResultadoFonte

# Duas UFs vizinhas fictícias: MG a oeste de -45, SP a leste. Dois biomas que cortam as duas.
MG = shapely.box(-48, -20, -45, -17)
SP = shapely.box(-45, -20, -42, -17)
CERRADO = shapely.box(-48, -18.5, -42, -17)
MATA = shapely.box(-48, -20, -42, -18.5)


UFS = pd.DataFrame({"uf": ["MG", "SP"], "cod_uf": ["31", "35"], "geometria_wkt": [MG.wkt, SP.wkt]})
BIOMAS = pd.DataFrame({"bioma": ["cerrado", "mata_atlantica"], "nome": ["Cerrado", "Mata Atlântica"],
                       "geometria_wkt": [CERRADO.wkt, MATA.wkt]})


def gravar_contornos(tmp_path, monkeypatch, ufs=UFS, biomas=BIOMAS):
    """Aponta o lago para uma pasta de teste e grava geo.uf e geo.bioma (None = não grava)."""
    monkeypatch.setattr(config, "LAGO", tmp_path / "lago")
    r = ResultadoFonte("territorio", "teste", carga_id="territorio:20261103T100000")
    for tabela, df in (("geo.uf", ufs), ("geo.bioma", biomas)):
        if df is not None:
            lago.gravar(tabela, df, r)
    territorio._ufs.cache_clear()
    territorio._biomas.cache_clear()


@pytest.fixture
def contornos(tmp_path, monkeypatch):
    gravar_contornos(tmp_path, monkeypatch)
    territorio._biomas.cache_clear()
    yield
    territorio._ufs.cache_clear()
    territorio._biomas.cache_clear()


def test_uf_do_ponto_pelo_contorno_e_fora_do_brasil(contornos):
    assert territorio.uf_do_ponto(-18.94, -46.99) == "MG"
    assert territorio.uf_do_ponto(-18.0, -43.0) == "SP"
    assert territorio.uf_do_ponto(-18.0, -30.0) is None  # no mar


def test_poligono_de_divisa_toca_as_duas_ufs_e_fica_com_a_do_ponto_representativo(contornos):
    divisa = shapely.box(-45.3, -18, -44.9, -17.8)  # 0,3° em MG e 0,1° em SP
    assert territorio.ufs_da_geometria(divisa) == ["MG", "SP"]
    assert territorio.uf_por_contorno(shapely.from_wkt([divisa.wkt]))[0] == "MG"


def test_biomas_do_imovel(contornos):
    assert territorio.biomas_da_geometria(shapely.box(-47, -18.6, -46.9, -18.4)) == ["cerrado", "mata_atlantica"]


def test_sicar_por_ponto_usa_a_uf_do_contorno(contornos, monkeypatch):
    camadas = []
    monkeypatch.setattr(sicar, "_consultar_filtro", lambda tipo, cql, uf, atualizar: camadas.append(uf))
    sicar.consultar_ponto(-18.0, -43.0)
    sicar.consultar_bbox((-47.0, -19.0, -46.9, -18.9))
    assert camadas == ["SP", "MG"]
    with pytest.raises(ValueError, match="fora do território"):
        sicar.consultar_ponto(-18.0, -30.0)


def test_sicar_por_municipio_usa_a_uf_do_codigo_ibge(monkeypatch):
    assert sicar.uf_do_municipio("1505502") == "PA" and sicar.uf_do_municipio("3148103") == "MG"
    with pytest.raises(ValueError, match="UFs diferentes"):
        sicar.consultar_municipios(["1505502", "3148103"])


def test_malha_sem_as_27_ufs_interrompe():
    resposta = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codarea": "31"}, "geometry": shapely.geometry.mapping(MG)}]}
    with pytest.raises(ErroDeValidacao, match="UF_QUANTIDADE"):
        territorio.construir_ufs(resposta, ResultadoFonte("territorio", "teste"))


def malha(*contornos):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codarea": cod}, "geometry": shapely.geometry.mapping(g)}
        for cod, g in contornos]}


def test_carregar_grava_no_lago_e_so_cria_carga_nova_quando_o_contorno_muda(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LAGO", tmp_path / "lago")
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    relogio_que_avanca(monkeypatch)
    monkeypatch.setattr(config, "DADOS_BRUTOS", tmp_path / "raw")
    monkeypatch.setattr(config, "UFS", ["MG", "SP"])
    monkeypatch.setattr(config, "CODIGO_UF_IBGE", {"31": "MG", "35": "SP"})
    monkeypatch.setattr(config, "BIOMAS_INPE", {"Cerrado": "cerrado", "Mata Atlântica": "mata_atlantica"})
    monkeypatch.setattr(territorio, "baixar", lambda *a, **k: {})
    (tmp_path / "raw").mkdir()
    arq_ufs, arq_biomas = tmp_path / "raw" / "ibge_malha_ufs.geojson", tmp_path / "raw" / "inpe_biomas.geojson"
    arq_ufs.write_text(json.dumps(malha(("31", MG), ("35", SP))))
    arq_biomas.write_text(json.dumps({
        "type": "FeatureCollection", "crs": {"properties": {"name": f"urn:ogc:def:crs:{config.CRS_ESPERADO_WFS}"}},
        "features": [{"type": "Feature", "properties": {"bioma": b}, "geometry": shapely.geometry.mapping(g)}
                     for b, g in (("Cerrado", CERRADO), ("Mata Atlântica", MATA))]}))

    primeira, igual = territorio.carregar(), territorio.carregar()
    assert [primeira.saida["tabelas"][t]["novo"] for t in ("geo.uf", "geo.bioma")] == [True, True]
    assert [igual.saida["tabelas"][t]["novo"] for t in ("geo.uf", "geo.bioma")] == [False, False]
    assert primeira.saida["arquivos"] == ["lago/geo/uf", "lago/geo/bioma"]

    arq_ufs.write_text(json.dumps(malha(("31", MG), ("35", shapely.box(-45, -20, -41, -17)))))
    mudou = territorio.carregar()
    assert mudou.saida["tabelas"]["geo.uf"]["novo"] and not mudou.saida["tabelas"]["geo.bioma"]["novo"]
    assert len(lago.ler("geo.uf", vigente=False)) == 4  # as duas cargas de UF ficam guardadas
    assert territorio.uf_do_ponto(-18.0, -41.5) == "SP"  # o cache foi limpo e a leitura vem da carga vigente


def test_contornos_ausentes_no_lago_sao_carregados_na_primeira_consulta(tmp_path, monkeypatch):
    gravar_contornos(tmp_path, monkeypatch, ufs=None, biomas=None)
    chamadas = []
    monkeypatch.setattr(territorio, "carregar", lambda: chamadas.append(1) or gravar_contornos(
        tmp_path, monkeypatch))
    assert territorio.uf_do_ponto(-18.94, -46.99) == "MG" and chamadas == [1]


def test_tabela_de_codigos_cobre_as_27_ufs():
    assert sorted(config.CODIGO_UF_IBGE.values()) == sorted(config.UFS)
