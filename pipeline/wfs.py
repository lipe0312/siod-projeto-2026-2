"""Acesso comum aos serviços WFS 2.0 (TerraBrasilis do INPE e SICAR): requisição, contagem, filtros espaciais e
leitura da resposta GeoJSON. Usado pelo DETER (lote) e pelo PRODES e SICAR (sob demanda)."""

import json
import logging
import re
import time
from pathlib import Path

import requests

from pipeline import config
from pipeline.download import consultar

log = logging.getLogger("pipeline")


def requisitar(url: str, tipo: str, parametros: dict, sessao: requests.Session | None = None,
               tentativas: int = 4) -> requests.Response:
    """GetFeature com repetição em falha de rede ou de servidor."""
    base = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeName": tipo}
    cliente = sessao or requests
    for tentativa in range(1, tentativas + 1):
        try:
            r = cliente.get(url, params={**base, **parametros}, timeout=300, headers={"User-Agent": config.USER_AGENT})
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if tentativa == tentativas:
                raise
            espera = 5 * tentativa
            log.warning("Falha na requisição ao WFS %s (%s); nova tentativa em %ss", url, type(e).__name__, espera)
            time.sleep(espera)


def numero_anunciado(texto: str) -> int:
    """Lê `numberMatched` de uma resposta `resultType=hits`."""
    achado = re.search(r'numberMatched="(\d+)"', texto)
    if not achado:
        raise ValueError("resposta de contagem do WFS sem numberMatched")
    return int(achado.group(1))


def contar(url: str, tipo: str, cql: str, sessao: requests.Session | None = None, tentativas: int = 4) -> int:
    return numero_anunciado(requisitar(url, tipo, {"resultType": "hits", "CQL_FILTER": cql}, sessao,
                                       tentativas).text)


def _lat_lon(lat: float, lon: float) -> tuple[float, float]:
    """Põe o par na ordem que o filtro espera (config.ORDEM_EIXOS_FILTRO)."""
    return (lat, lon) if config.ORDEM_EIXOS_FILTRO == ("lat", "lon") else (lon, lat)


def filtro_bbox(campo: str, limites: tuple[float, float, float, float]) -> str:
    """`limites` no formato do shapely: (lon_min, lat_min, lon_max, lat_max). Sem SRS, o serviço lê (lat, lon)."""
    lon_min, lat_min, lon_max, lat_max = limites
    a0, b0 = _lat_lon(lat_min, lon_min)
    a1, b1 = _lat_lon(lat_max, lon_max)
    return f"BBOX({campo},{a0},{b0},{a1},{b1})"


def filtro_ponto(campo: str, lat: float, lon: float) -> str:
    a, b = _lat_lon(lat, lon)
    return f"INTERSECTS({campo},POINT({a} {b}))"


def consultar_geojson(url: str, tipo: str, cql: str, destino: Path, sessao: requests.Session | None = None,
                      atualizar: bool = False, limite: int | None = None, tentativas: int = 4) -> tuple[dict, dict]:
    """GetFeature em GeoJSON com cache em `destino` (ver pipeline.download.consultar). Devolve (resposta, meta).
    Erro de servidor (5xx, comum no TerraBrasilis) é repetido com espera crescente; 4xx não."""
    parametros = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeName": tipo,
                  "outputFormat": "application/json", "CQL_FILTER": cql}
    if limite:
        parametros["count"] = limite
    for tentativa in range(1, tentativas + 1):
        # Na repetição, consulta de novo: o que ficou gravado é a resposta de erro.
        conteudo, meta = consultar(url, destino, parametros, sessao, atualizar or tentativa > 1,
                                   pausa=config.PAUSA_ENTRE_CONSULTAS_S)
        status = meta.get("status_http")
        if status == 200:
            break
        if status is not None and status < 500 or tentativa == tentativas:
            raise requests.HTTPError(f"WFS respondeu HTTP {status} para {cql}")
        log.warning("WFS respondeu HTTP %s para %s; nova tentativa em %ss", status, cql, 10 * tentativa)
        time.sleep(10 * tentativa)
    arquivo = destino.relative_to(config.RAIZ) if destino.is_relative_to(config.RAIZ) else destino
    return json.loads(conteudo), {**meta, "arquivo": str(arquivo)}


def problema_estrutural(resposta) -> str | None:
    """Descrição do problema, ou None se a resposta for uma FeatureCollection com lista de features."""
    if not isinstance(resposta, dict):
        return "resposta não é um objeto JSON"
    if resposta.get("type") != "FeatureCollection":
        return "type diferente de FeatureCollection"
    if not isinstance(resposta.get("features"), list):
        return "campo features ausente ou não é lista"
    return None


def crs_esperado(resposta: dict) -> bool:
    return config.CRS_ESPERADO_WFS in json.dumps(resposta.get("crs", {}))


def incompleta(resposta: dict) -> bool:
    """O próprio serviço anunciou mais feições do que mandou."""
    anunciados = resposta.get("numberMatched")
    return isinstance(anunciados, int) and len(resposta["features"]) != anunciados
