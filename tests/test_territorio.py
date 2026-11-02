"""Referência territorial: UF e bioma pelo contorno, com contornos fictícios (sem rede)."""

import pandas as pd
import pytest
import shapely

from pipeline import config, territorio
from pipeline.fontes import sicar
from pipeline.validacao import ErroDeValidacao, ResultadoFonte

# Duas UFs vizinhas fictícias: MG a oeste de -45, SP a leste. Dois biomas que cortam as duas.
MG = shapely.box(-48, -20, -45, -17)
SP = shapely.box(-45, -20, -42, -17)
CERRADO = shapely.box(-48, -18.5, -42, -17)
MATA = shapely.box(-48, -20, -42, -18.5)


@pytest.fixture
def contornos(tmp_path, monkeypatch):
    monkeypatch.setattr(territorio, "ARQ_UFS", tmp_path / "ufs.parquet")
    monkeypatch.setattr(territorio, "ARQ_BIOMAS", tmp_path / "biomas.parquet")
    pd.DataFrame({"uf": ["MG", "SP"], "cod_uf": ["31", "35"], "geometria_wkt": [MG.wkt, SP.wkt]}).to_parquet(
        territorio.ARQ_UFS)
    pd.DataFrame({"bioma": ["cerrado", "mata_atlantica"], "nome": ["Cerrado", "Mata Atlântica"],
                  "geometria_wkt": [CERRADO.wkt, MATA.wkt]}).to_parquet(territorio.ARQ_BIOMAS)
    territorio._ufs.cache_clear()
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


def test_tabela_de_codigos_cobre_as_27_ufs():
    assert sorted(config.CODIGO_UF_IBGE.values()) == sorted(config.UFS)
