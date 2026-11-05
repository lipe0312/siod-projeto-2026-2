"""Leitura de shapefile dentro de um zip (CNUC do MMA, territórios quilombolas do IBGE), validações de geometria
comuns às camadas de sobreposição (terras indígenas, unidades de conservação, quilombolas) e leitura do polígono da
área de produção que o técnico traz (KML ou GeoJSON, ler_area_producao)."""

import io
import json
import re
import xml.etree.ElementTree as ET
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
                      "interrompe a fonte", int(not eh_sirgas_2000(prj)), 1)


def eh_sirgas_2000(prj: str) -> bool:
    """SIRGAS 2000 geográfico: o ESRI grava GCS_SIRGAS_2000; o GDAL grava "SIRGAS 2000" com AUTHORITY EPSG 4674."""
    texto = (prj or "").upper().lstrip()
    if texto.startswith("PROJCS"):  # projetado (ex.: SIRGAS 2000 / UTM): coordenada em metros, não em graus
        return False
    return SIRGAS_2000 in texto or 'GEOGCS["SIRGAS 2000"' in texto or 'AUTHORITY["EPSG","4674"]' in texto


# ---------------------------------------------------------------------------------------------------------------
# Área de produção (EUDR): KML ou GeoJSON trazido pelo técnico
# ---------------------------------------------------------------------------------------------------------------

class AreaIlegivel(ValueError):
    """O arquivo da área de produção não pôde ser lido; a mensagem é o motivo, para a ficha."""


TAMANHO_MAXIMO_AREA = 20 * 1024 * 1024  # um talhão em KML tem poucos KB; acima disso não é o arquivo certo
# KML é sempre WGS 84; GeoJSON (RFC 7946) também, e o antigo (2008) podia declarar o CRS no membro "crs".
CRS_WGS84 = {"4326", "CRS84"}
CRS_SIRGAS = {"4674"}
BRASIL = (-74.0, -34.0, -28.0, 6.0)  # mesma caixa da conferência de lat/lon da carteira


def _crs_geojson(dado: dict) -> str:
    """'WGS 84' ou 'SIRGAS 2000'; AreaIlegivel para qualquer outro CRS declarado."""
    crs = dado.get("crs")
    if crs is None:
        return "WGS 84"
    props = (crs.get("properties") or {}) if isinstance(crs, dict) else {}
    texto = str(props.get("name") or props.get("code") or "")
    codigo = re.search(r"(CRS84|\d{4,5})\s*$", texto.upper())
    codigo = codigo.group(1) if codigo else ""
    if codigo in CRS_WGS84:
        return "WGS 84"
    if codigo in CRS_SIRGAS:
        return "SIRGAS 2000"
    raise AreaIlegivel(f"sistema de referência {texto or json.dumps(crs)[:80]} não aceito (use SIRGAS 2000 ou WGS 84)")


def _poligonos_geojson(dado) -> list:
    tipo = (dado or {}).get("type") if isinstance(dado, dict) else None
    if tipo == "FeatureCollection":
        return [g for f in dado.get("features") or [] for g in _poligonos_geojson(f)]
    if tipo == "Feature":
        return _poligonos_geojson(dado.get("geometry"))
    if tipo == "GeometryCollection":
        return [g for p in dado.get("geometries") or [] for g in _poligonos_geojson(p)]
    if tipo in ("Polygon", "MultiPolygon"):
        return [shapely.geometry.shape(dado)]
    return []


def _anel_kml(elemento) -> list[tuple[float, float]]:
    coordenadas = next((e for e in elemento.iter() if e.tag.rsplit("}", 1)[-1] == "coordinates"), None)
    if coordenadas is None or not (coordenadas.text or "").strip():
        raise AreaIlegivel("KML com polígono sem coordenadas")
    pontos = []
    for trio in coordenadas.text.split():
        partes = trio.split(",")
        try:
            pontos.append((float(partes[0]), float(partes[1])))
        except (ValueError, IndexError):
            raise AreaIlegivel(f"KML com coordenada que não é número: {trio[:40]!r}") from None
    return pontos


def _poligonos_kml(conteudo: bytes) -> list:
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError as e:
        raise AreaIlegivel(f"KML mal formado ({e})") from None
    local = lambda e: e.tag.rsplit("}", 1)[-1]
    poligonos = []
    for pol in (e for e in raiz.iter() if local(e) == "Polygon"):
        externo = [e for e in pol if local(e) == "outerBoundaryIs"]
        if not externo:
            raise AreaIlegivel("KML com polígono sem contorno externo (outerBoundaryIs)")
        furos = [_anel_kml(e) for e in pol if local(e) == "innerBoundaryIs"]
        poligonos.append(shapely.Polygon(_anel_kml(externo[0]), furos))
    return poligonos


def ler_area_producao(caminho: Path) -> tuple[shapely.MultiPolygon, str]:
    """MultiPolygon em SIRGAS 2000 (EPSG 4674) e o CRS de origem, de um .kml, .geojson ou .json.

    WGS 84 → SIRGAS 2000: a transformação oficial entre os dois é nula (diferença abaixo de 1 m), então as coordenadas
    ficam como estão e passam a valer como 4674. Só polígonos entram (ponto e linha são ignorados); a geometria passa
    por tornar_valida. Qualquer problema vira AreaIlegivel com o motivo."""
    caminho = Path(caminho)
    extensao = caminho.suffix.lower()
    if extensao not in (".kml", ".geojson", ".json"):
        raise AreaIlegivel(f"formato {extensao or 'sem extensão'} não aceito (use .kml, .geojson ou .json)")
    if not caminho.is_file():
        raise AreaIlegivel(f"arquivo {caminho.name} não encontrado")
    if caminho.stat().st_size > TAMANHO_MAXIMO_AREA:
        raise AreaIlegivel(f"arquivo {caminho.name} com mais de {TAMANHO_MAXIMO_AREA // 2**20} MB")
    conteudo = caminho.read_bytes()
    if extensao == ".kml":
        poligonos, crs = _poligonos_kml(conteudo), "WGS 84"
    else:
        try:
            dado = json.loads(conteudo.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise AreaIlegivel(f"GeoJSON mal formado ({type(e).__name__})") from None
        crs = _crs_geojson(dado if isinstance(dado, dict) else {})
        try:
            poligonos = _poligonos_geojson(dado)
        except (TypeError, ValueError, AttributeError, GEOSException) as e:
            raise AreaIlegivel(f"GeoJSON com geometria inválida ({type(e).__name__})") from None
    if not poligonos:
        raise AreaIlegivel("nenhum Polygon ou MultiPolygon no arquivo")
    try:
        geom = tornar_valida(shapely.union_all([tornar_valida(shapely.force_2d(p)) for p in poligonos]))
    except (GEOSException, ValueError) as e:
        raise AreaIlegivel(f"polígono que não pôde ser corrigido ({type(e).__name__})") from None
    partes = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type in ("Polygon", "MultiPolygon")]
    geom = shapely.union_all(partes) if partes else shapely.Polygon()
    if geom.is_empty or geom.area == 0:
        raise AreaIlegivel("polígono sem área")
    x0, y0, x1, y1 = geom.bounds
    if not (BRASIL[0] <= x0 and x1 <= BRASIL[2] and BRASIL[1] <= y0 and y1 <= BRASIL[3]):
        raise AreaIlegivel("coordenadas fora do Brasil (em metros, ou com latitude e longitude trocadas?)")
    return (geom if geom.geom_type == "MultiPolygon" else shapely.MultiPolygon([geom])), crs
