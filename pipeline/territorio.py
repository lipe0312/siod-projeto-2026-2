"""Referência territorial: contorno das UFs (malha do IBGE) e dos biomas (INPE), em data/processed/.

A UF de um ponto (sede do imóvel), de um polígono PRODES ou de um imóvel vem do contorno, não de um campo de texto da
fonte (ADR 0013): o campo `state` do PRODES pode trazer a UF vizinha num polígono de divisa, e a consulta por ponto
ao SICAR precisa saber em que camada (uma por UF) procurar.
"""

import functools
import json

import numpy as np
import pandas as pd
import shapely
from shapely.strtree import STRtree

from pipeline import config, vetor
from pipeline.download import baixar
from pipeline.validacao import ResultadoFonte

ARQ_UFS = config.DADOS_PROCESSADOS / "ibge_ufs.parquet"
ARQ_BIOMAS = config.DADOS_PROCESSADOS / "inpe_biomas.parquet"


def _feicoes(resposta: dict, resultado: ResultadoFonte, prefixo: str) -> list[dict]:
    estrutura = isinstance(resposta, dict) and isinstance(resposta.get("features"), list)
    resultado.validar(f"{prefixo}_ESTRUTURA_RESPOSTA", "Resposta é FeatureCollection com lista de features", "erro",
                      "interrompe a referência", int(not estrutura), 1)
    return resposta["features"]


def _geometrias(feicoes: list[dict], resultado: ResultadoFonte, prefixo: str) -> np.ndarray:
    geoms = np.array([shapely.geometry.shape(f["geometry"]) if f.get("geometry") else None for f in feicoes])
    ausente = np.array([g is None or g.is_empty for g in geoms])
    resultado.validar(f"{prefixo}_GEOM_AUSENTE", "Feição sem geometria", "erro", "interrompe a referência",
                      int(ausente.sum()), len(geoms))
    invalida = ~shapely.is_valid(geoms)
    resultado.validar(f"{prefixo}_GEOM_INVALIDA", "Geometria inválida (shapely is_valid)", "correcao",
                      "shapely.make_valid", int(invalida.sum()), len(geoms))
    return vetor.tornar_validas(geoms)


def construir_ufs(resposta: dict, resultado: ResultadoFonte) -> pd.DataFrame:
    feicoes = _feicoes(resposta, resultado, "UF")
    codigos = [str((f.get("properties") or {}).get("codarea")) for f in feicoes]
    siglas = [config.CODIGO_UF_IBGE.get(c) for c in codigos]
    resultado.validar("UF_CODIGO_DESCONHECIDO", "codarea fora da tabela de UFs do IBGE", "erro",
                      "interrompe a referência", sum(s is None for s in siglas), len(siglas))
    resultado.validar("UF_QUANTIDADE", "Malha com as 27 UFs, cada uma uma vez", "erro", "interrompe a referência",
                      int(sorted(siglas) != sorted(config.UFS)), 1)
    geoms = _geometrias(feicoes, resultado, "UF")
    return pd.DataFrame({"uf": siglas, "cod_uf": codigos, "geometria_wkt": shapely.to_wkt(geoms, rounding_precision=-1)})


def construir_biomas(resposta: dict, resultado: ResultadoFonte) -> pd.DataFrame:
    feicoes = _feicoes(resposta, resultado, "BIOMA")
    nomes = [(f.get("properties") or {}).get("bioma") for f in feicoes]
    chaves = [config.BIOMAS_INPE.get(n) for n in nomes]
    resultado.validar("BIOMA_DESCONHECIDO", "Nome de bioma fora da tabela do projeto", "erro",
                      "interrompe a referência", sum(c is None for c in chaves), len(chaves))
    resultado.validar("BIOMA_QUANTIDADE", "Os seis biomas, cada um uma vez", "erro", "interrompe a referência",
                      int(sorted(chaves) != sorted(config.BIOMAS_INPE.values())), 1)
    crs = json.dumps(resposta.get("crs", {}))
    resultado.validar("BIOMA_CRS_INESPERADO", f"CRS diferente de {config.CRS_ESPERADO_WFS} (SIRGAS 2000)", "erro",
                      "interrompe a referência", int(config.CRS_ESPERADO_WFS not in crs), 1)
    geoms = _geometrias(feicoes, resultado, "BIOMA")
    return pd.DataFrame({"bioma": chaves, "nome": nomes, "geometria_wkt": shapely.to_wkt(geoms, rounding_precision=-1)})


def carregar(atualizar: bool = False) -> ResultadoFonte:
    """Baixa (ou reaproveita) a malha de UFs e os biomas, valida e grava os dois parquets."""
    resultado = ResultadoFonte("territorio", "API (GeoJSON), referência")
    destinos = {"ufs": config.DADOS_BRUTOS / "ibge_malha_ufs.geojson",
                "biomas": config.DADOS_BRUTOS / "inpe_biomas.geojson"}
    resultado.entrada = {"ufs": baixar(config.URL_IBGE_MALHA_UFS, destinos["ufs"], atualizar),
                         "biomas": baixar(config.URL_INPE_BIOMAS, destinos["biomas"], atualizar)}
    ufs = construir_ufs(json.loads(destinos["ufs"].read_text()), resultado)
    biomas = construir_biomas(json.loads(destinos["biomas"].read_text()), resultado)
    resultado.transformar("Código da UF (codarea) convertido para a sigla; nome do bioma para a chave do projeto")
    config.DADOS_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    ufs.to_parquet(ARQ_UFS, index=False)
    biomas.to_parquet(ARQ_BIOMAS, index=False)
    for f in (_ufs, _biomas):
        f.cache_clear()
    resultado.saida = {"arquivos": [str(ARQ_UFS.relative_to(config.RAIZ)), str(ARQ_BIOMAS.relative_to(config.RAIZ))],
                       "registros_produzidos": len(ufs) + len(biomas)}
    resultado.status = "ok"
    return resultado


@functools.cache
def _ufs() -> tuple[list[str], np.ndarray, STRtree]:
    if not ARQ_UFS.exists():
        carregar()
    df = pd.read_parquet(ARQ_UFS)
    geoms = shapely.from_wkt(df["geometria_wkt"].to_numpy())
    return df["uf"].tolist(), geoms, STRtree(geoms)


@functools.cache
def _biomas() -> tuple[list[str], np.ndarray, STRtree]:
    if not ARQ_BIOMAS.exists():
        carregar()
    df = pd.read_parquet(ARQ_BIOMAS)
    geoms = shapely.from_wkt(df["geometria_wkt"].to_numpy())
    return df["bioma"].tolist(), geoms, STRtree(geoms)


def _que_intersectam(geom, referencia) -> list[str]:
    nomes, _, arvore = referencia
    return sorted({nomes[i] for i in arvore.query(geom, predicate="intersects")})


def uf_do_ponto(lat: float, lon: float) -> str | None:
    """UF cujo contorno contém o ponto; None fora do Brasil (ou no mar)."""
    nomes, _, arvore = _ufs()
    achados = arvore.query(shapely.Point(lon, lat), predicate="intersects")
    return nomes[achados[0]] if len(achados) else None


def ufs_da_geometria(geom) -> list[str]:
    return _que_intersectam(geom, _ufs())


def biomas_da_geometria(geom) -> list[str]:
    return _que_intersectam(geom, _biomas())


def contorno_uf(uf: str):
    nomes, geoms, _ = _ufs()
    return geoms[nomes.index(uf)]


def uf_por_contorno(geoms: np.ndarray) -> np.ndarray:
    """Para cada geometria, a UF que contém o seu ponto representativo (None se cair fora de todas, como no mar)."""
    nomes, _, arvore = _ufs()
    pontos = shapely.point_on_surface(geoms)
    i_geom, i_uf = arvore.query(pontos, predicate="intersects")
    saida = np.full(len(geoms), None, dtype=object)
    saida[i_geom[::-1]] = np.array(nomes, dtype=object)[i_uf[::-1]]  # se o ponto cair na divisa, vale a primeira
    return saida
