"""Leitura de shapefile dentro de um zip (CNUC do MMA, territórios quilombolas do IBGE) e validações de geometria
comuns às camadas de sobreposição (terras indígenas, unidades de conservação, quilombolas)."""

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import shapefile
import shapely
from shapely.errors import GEOSException

from pipeline.validacao import ResultadoFonte

SIRGAS_2000 = "SIRGAS_2000"


def tornar_valida(geom):
    """make_valid que não para no anel degenerado (poucos pontos): o método padrão do GEOS recusa a geometria com
    "Overlay input is mixed-dimension" (visto no PRODES Mata Atlântica 2024); aí vale o método "structure", e só as
    partes de área ficam."""
    if geom is None or geom.is_empty or geom.is_valid:
        return geom
    try:
        return shapely.make_valid(geom)
    except GEOSException:
        corrigida = shapely.make_valid(geom, method="structure", keep_collapsed=False)
        partes = [g for g in getattr(corrigida, "geoms", [corrigida]) if g.geom_type in ("Polygon", "MultiPolygon")]
        return shapely.union_all(partes) if partes else shapely.Polygon()


def tornar_validas(geoms: np.ndarray) -> np.ndarray:
    return np.array([tornar_valida(g) for g in geoms], dtype=object)


def ler_shapefile_zip(caminho: Path, base: str) -> tuple[list[dict], np.ndarray, str, int]:
    """Registros (dict por feição), geometrias 2D, texto do .prj e quantos textos precisaram de troca de caractere.

    `base`: final do nome do arquivo, sem extensão (o zip pode ter mais de uma camada). Texto truncado no meio de um
    caractere UTF-8 (acontece no CNUC) é lido com o caractere de substituição em vez de interromper a leitura.
    """
    z = zipfile.ZipFile(caminho)
    nomes = {n.rsplit(".", 1)[-1].lower(): n for n in z.namelist() if n.rsplit(".", 1)[0].endswith(base)}
    leitor = shapefile.Reader(shp=io.BytesIO(z.read(nomes["shp"])), dbf=io.BytesIO(z.read(nomes["dbf"])),
                              shx=io.BytesIO(z.read(nomes["shx"])), encoding="utf-8", encodingErrors="replace")
    registros = [r.as_dict() for r in leitor.records()]
    geoms = np.array([shapely.force_2d(shapely.geometry.shape(s.__geo_interface__)) if s.shapeType else None
                      for s in leitor.shapes()], dtype=object)
    trocados = sum(any("�" in str(v) for v in r.values()) for r in registros)
    prj = z.read(nomes["prj"]).decode("utf-8", "replace") if "prj" in nomes else ""
    return registros, geoms, prj, trocados


def validar_geometrias(prefixo: str, geoms: np.ndarray, resultado: ResultadoFonte) -> tuple[np.ndarray, pd.Series]:
    """Descarta ausentes (devolve a máscara do que fica) e corrige inválidas com make_valid."""
    ausente = pd.Series([g is None or g.is_empty for g in geoms])
    resultado.validar(f"{prefixo}_GEOM_AUSENTE", "Feição sem geometria", "descarte", "registro vai para descartados",
                      ausente, len(geoms))
    validas = geoms.copy()
    presentes = ~ausente.to_numpy()
    invalida = np.zeros(len(geoms), dtype=bool)
    invalida[presentes] = ~shapely.is_valid(geoms[presentes].astype(object))
    resultado.validar(f"{prefixo}_GEOM_INVALIDA", "Geometria inválida (shapely is_valid)", "correcao",
                      "shapely.make_valid antes de qualquer interseção", int(invalida.sum()), int(presentes.sum()))
    validas[presentes] = tornar_validas(geoms[presentes])
    return validas, ~ausente


def validar_crs_sirgas(prefixo: str, prj: str, resultado: ResultadoFonte) -> None:
    resultado.validar(f"{prefixo}_CRS_INESPERADO", "Sistema de referência diferente de SIRGAS 2000 no .prj", "erro",
                      "interrompe a fonte", int(not prj or SIRGAS_2000 not in prj.upper()), 1)
