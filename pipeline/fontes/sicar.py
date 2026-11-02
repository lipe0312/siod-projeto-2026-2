"""Fonte sob demanda: CAR (Cadastro Ambiental Rural) pelo WFS público do SICAR.

Consulta por município, retângulo (BBOX) ou ponto, com cache da resposta bruta em data/raw/sicar/. Cada consulta
devolve o DataFrame tratado e o ResultadoFonte, com as mesmas validações nas três formas de consulta.

O servidor do SICAR só negocia TLS com cifras e renegociação antigas. A sessão usa um adaptador do `requests` que
baixa o nível de segurança das cifras e aceita a renegociação legada, com a verificação do certificado ligada.
"""

import hashlib
import json
import logging
import re
import ssl

import numpy as np
import pandas as pd
import requests
import shapely
from requests.adapters import HTTPAdapter

from pipeline import config, vetor, wfs
from pipeline.download import baixar
from pipeline.validacao import Marcas, ResultadoFonte

log = logging.getLogger("pipeline")

CAMPO_GEOMETRIA = "geo_area_imovel"
FORMATO_CODIGO = r"[A-Z]{2}-\d{7}-[0-9A-F]{32}"
LIMIAR_SOBREPOSTO = 0.95
LIMIAR_AREA_DIVERGENTE = 0.01

COLUNAS_SAIDA = [
    "cod_imovel", "uf", "cod_municipio", "municipio", "tipo_imovel", "status_imovel", "condicao", "area_declarada_ha",
    "area_geom_ha", "m_fiscal", "data_criacao", "data_atualizacao", "fracao_coberta_por_outros", "geometria_wkt",
    "alertas",
]


class AdaptadorTLSLegado(HTTPAdapter):
    """Contexto TLS padrão (certificado verificado) com cifras de nível 1 e renegociação legada."""

    def init_poolmanager(self, *args, **kwargs):
        contexto = ssl.create_default_context()
        contexto.set_ciphers("DEFAULT:@SECLEVEL=1")
        contexto.options |= ssl.OP_LEGACY_SERVER_CONNECT
        kwargs["ssl_context"] = contexto
        return super().init_poolmanager(*args, **kwargs)


def sessao() -> requests.Session:
    s = requests.Session()
    s.mount("https://geoserver.car.gov.br", AdaptadorTLSLegado())
    return s


# Projeção senoidal (igual-área) com meridiano central em -45°, que passa por MG. Basta para áreas e frações.
_R = 6371007.181
_LON0 = np.radians(-45.0)


def _senoidal(xy: np.ndarray) -> np.ndarray:
    lon, lat = np.radians(xy[:, 0]), np.radians(xy[:, 1])
    return np.column_stack([_R * (lon - _LON0) * np.cos(lat), _R * lat])


def projetar(geoms):
    return shapely.transform(geoms, _senoidal)


def area_ha(geoms) -> np.ndarray:
    return shapely.area(projetar(geoms)) / 10_000


def fracao_coberta(geoms: np.ndarray) -> np.ndarray:
    """Para cada polígono, a soma das interseções com os demais dividida pela sua área (projeção igual-área)."""
    p = projetar(geoms)
    area_m2 = shapely.area(p)
    i, j = shapely.STRtree(p).query(p, predicate="intersects")
    i, j = i[i < j], j[i < j]
    inter = shapely.area(shapely.intersection(p[i], p[j]))
    coberto = np.zeros(len(p))
    np.add.at(coberto, i, inter)
    np.add.at(coberto, j, inter)
    return np.divide(coberto, area_m2, out=np.zeros(len(p)), where=area_m2 > 0)


def camada(uf: str) -> str:
    return config.CAMADA_SICAR.format(uf=uf.lower())


def resposta_para_tabela(resposta: dict) -> pd.DataFrame:
    linhas = []
    for f in resposta["features"]:
        g = f.get("geometry")
        linhas.append({**(f.get("properties") or {}), "id_feature": f.get("id"),
                       "geom": shapely.from_geojson(json.dumps(g)) if g else None})
    colunas = ["cod_imovel", "status_imovel", "dat_criacao", "data_atualizacao", "area", "condicao", "uf",
               "municipio", "cod_municipio_ibge", "m_fiscal", "tipo_imovel", "id_feature", "geom"]
    return pd.DataFrame(linhas).reindex(columns=colunas)


def transformar(respostas: list[dict], resultado: ResultadoFonte,
                malhas: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Valida e trata uma ou mais respostas GeoJSON do SICAR. `malhas`: {cod_ibge: polígono do município}."""
    problemas = [p for p in map(wfs.problema_estrutural, respostas) if p]
    resultado.validar("CAR_ESTRUTURA_RESPOSTA", "Resposta é FeatureCollection com lista de features"
                      + (f" ({problemas[0]})" if problemas else ""), "erro", "interrompe a consulta",
                      len(problemas), len(respostas))
    resultado.validar("CAR_PARTICAO_INCOMPLETA", "Recebido diferente do numberMatched anunciado pelo serviço",
                      "erro", "interrompe a consulta; repetir", sum(map(wfs.incompleta, respostas)), len(respostas))
    resultado.validar("CAR_CRS_INESPERADO", f"CRS diferente de {config.CRS_ESPERADO_WFS} (SIRGAS 2000)", "erro",
                      "interrompe a consulta", sum(not wfs.crs_esperado(r) for r in respostas if r["features"]),
                      len(respostas))
    tabelas = [resposta_para_tabela(r) for r in respostas]
    df = pd.concat(tabelas, ignore_index=True) if tabelas else resposta_para_tabela({"features": []})
    texto = ["cod_imovel", "status_imovel", "condicao", "uf", "municipio", "tipo_imovel"]
    df[texto] = df[texto].astype("string")
    resultado.entrada["registros_recebidos"] = len(df)
    resultado.transformar("Conversão de cada feature GeoJSON em linha: propriedades e geometria")

    descartes = []

    def descartar(codigo, descricao, mascara):
        nonlocal df
        resultado.validar(codigo, descricao, "descarte", "registro vai para descartados", mascara, len(df))
        descartes.append(df[mascara].assign(motivo=codigo))
        df = df[~mascara].copy()

    descartar("CAR_CODIGO_INVALIDO", "cod_imovel fora do formato UF-IBGE(7)-32 hexadecimais",
              ~df["cod_imovel"].str.fullmatch(FORMATO_CODIGO).fillna(False).astype(bool))
    descartar("CAR_DUPLICADO", "cod_imovel repetido na consulta", df["cod_imovel"].duplicated())
    descartar("CAR_STATUS_DESCONHECIDO", "status_imovel fora de AT, PE, SU, CA",
              ~df["status_imovel"].isin(config.STATUS_CAR))
    descartar("CAR_GEOM_AUSENTE", "Imóvel sem geometria", df["geom"].isna())

    marcas = Marcas(df.index)
    n = len(df)
    g = df["geom"].to_numpy()
    invalida = pd.Series(~shapely.is_valid(g), index=df.index) if n else pd.Series(False, index=df.index)
    resultado.validar("CAR_GEOM_INVALIDA", "Geometria inválida (autointerseção)", "correcao",
                      "shapely.make_valid antes de medir", invalida, n)
    g = vetor.tornar_validas(g) if n else g
    df["geom"] = g
    df["area_geom_ha"] = area_ha(g) if n else []

    df["cod_municipio"] = pd.to_numeric(df["cod_municipio_ibge"], errors="coerce").astype("Int64").astype("string")
    prefixo_divergente = (df["cod_imovel"].str[3:10] != df["cod_municipio"]).fillna(True).astype(bool)
    resultado.validar("CAR_PREFIXO_MUNICIPIO_DIVERGENTE", "Município no código do CAR diferente de cod_municipio_ibge",
                      "alerta", "mantido cod_municipio_ibge; cruzar sempre pela geometria", prefixo_divergente, n)
    marcas.marcar("PREFIXO_MUNICIPIO_DIVERGENTE", prefixo_divergente)

    if malhas:
        com_malha = df["cod_municipio"].isin(malhas.keys())
        ponto = shapely.point_on_surface(df.loc[com_malha, "geom"].to_numpy())
        dentro = [shapely.contains(malhas[c], p) for c, p in zip(df.loc[com_malha, "cod_municipio"], ponto)]
        fora = pd.Series(False, index=df.index)
        fora[com_malha] = ~np.array(dentro, dtype=bool)
        resultado.validar("CAR_FORA_DO_MUNICIPIO", "Ponto interno do imóvel fora do município declarado (malha IBGE)",
                          "alerta", "mantido; atribuir o município pela geometria quando for preciso", fora,
                          int(com_malha.sum()))
        marcas.marcar("FORA_DO_MUNICIPIO", fora)

    # A razão área declarada / medida tem um viés constante da projeção; compara-se com a mediana.
    area_declarada = pd.to_numeric(df["area"], errors="coerce")
    razao = area_declarada / df["area_geom_ha"]
    divergente = ((razao / razao.median() - 1).abs() > LIMIAR_AREA_DIVERGENTE).fillna(False) if n else razao.notna()
    resultado.validar("CAR_AREA_DIVERGENTE", f"Área declarada difere mais de {LIMIAR_AREA_DIVERGENTE:.0%} da área "
                      "da geometria", "alerta", "usar a área da geometria nas frações", divergente, n)
    marcas.marcar("AREA_DIVERGENTE", divergente)

    cancelado = df["status_imovel"] == "CA"
    resultado.validar("CAR_CANCELADO", "status CA (cancelado)", "alerta", "mantido, mas não usar como CAR do imóvel",
                      cancelado, n)
    marcas.marcar("CANCELADO", cancelado)

    df["fracao_coberta_por_outros"] = fracao_coberta(g) if n else []
    sobreposto = df["fracao_coberta_por_outros"] >= LIMIAR_SOBREPOSTO
    resultado.validar("CAR_SOBREPOSTO_95", f"Imóvel com {LIMIAR_SOBREPOSTO:.0%} ou mais da área coberta por outros "
                      "imóveis da mesma consulta", "alerta", "marcar; a atribuição lista todos os CARs atingidos",
                      sobreposto, n)
    marcas.marcar("SOBREPOSTO_95", sobreposto)
    resultado.transformar("Área da geometria (projeção senoidal igual-área, meridiano -45°) e fração coberta por "
                          "outros imóveis da consulta")

    df["area_declarada_ha"] = area_declarada
    df["m_fiscal"] = pd.to_numeric(df["m_fiscal"], errors="coerce")
    df["data_criacao"] = pd.to_datetime(df["dat_criacao"], format="ISO8601", utc=True)
    df["data_atualizacao"] = pd.to_datetime(df["data_atualizacao"], format="ISO8601", utc=True)
    resultado.transformar("Datas de criação e atualização convertidas de texto ISO 8601 (UTC)")
    df["geometria_wkt"] = shapely.to_wkt(g, rounding_precision=-1, trim=True) if n else []
    df["alertas"] = marcas.coluna()
    saida = df[COLUNAS_SAIDA].reset_index(drop=True)
    colunas_desc = ["cod_imovel", "status_imovel", "cod_municipio_ibge", "motivo"]
    descartados = (pd.concat(descartes) if descartes else pd.DataFrame()).reindex(columns=colunas_desc)
    return saida, descartados.reset_index(drop=True)


def _consultar(cql: str, uf: str, nome: str, atualizar: bool) -> tuple[dict, dict]:
    destino = config.DADOS_BRUTOS / "sicar" / uf.lower() / f"{nome}.geojson.gz"
    return wfs.consultar_geojson(config.URL_WFS_SICAR, camada(uf), cql, destino, sessao(), atualizar)


def _resultado(tipo: str, cql: str, uf: str) -> ResultadoFonte:
    r = ResultadoFonte("sicar", f"API (WFS/GeoJSON), sob demanda por {tipo}")
    r.entrada = {"servico": config.URL_WFS_SICAR, "camada": camada(uf), "filtros": [cql], "requisicoes": []}
    return r


def _registrar(resultado: ResultadoFonte, meta: dict, resposta: dict) -> None:
    resultado.entrada["requisicoes"].append({
        "arquivo": meta.get("arquivo"), "anunciado": resposta.get("numberMatched"),
        "recebido": len(resposta.get("features") or []), "consultado_em_utc": meta["consultado_em_utc"],
        "sha256": meta["sha256"]})


def malha_municipio(cod_ibge: str, atualizar: bool = False):
    """Polígono do município (API de malhas do IBGE), com cache em data/raw/ibge_malhas/."""
    destino = config.DADOS_BRUTOS / "ibge_malhas" / f"{cod_ibge}.geojson"
    baixar(config.URL_MALHA_MUNICIPIO.format(cod=cod_ibge), destino, atualizar)
    fc = json.loads(destino.read_text())
    return vetor.tornar_valida(shapely.from_geojson(json.dumps(fc["features"][0]["geometry"])))


def uf_do_municipio(cod_ibge: str) -> str:
    uf = config.CODIGO_UF_IBGE.get(str(cod_ibge)[:2])
    if not uf:
        raise ValueError(f"código IBGE de município fora do formato: {cod_ibge!r}")
    return uf


def uf_da_area(lat: float, lon: float) -> str:
    """UF pelo contorno do IBGE (pipeline/territorio.py). Ponto fora do Brasil não é consultado."""
    from pipeline import territorio

    uf = territorio.uf_do_ponto(lat, lon)
    if not uf:
        raise ValueError(f"ponto fora do território brasileiro: lat {lat}, lon {lon}")
    return uf


def consultar_municipios(cods_ibge, uf: str | None = None, atualizar: bool = False,
                         conferir_malha: bool = True) -> tuple[pd.DataFrame, ResultadoFonte]:
    """Todos os imóveis de cada município (uma requisição por município, todos da mesma UF, deduzida do código IBGE).
    A sobreposição é medida no conjunto."""
    cods = [str(c) for c in cods_ibge]
    ufs = {uf_do_municipio(c) for c in cods}
    if uf is None and len(ufs) == 1:
        uf = ufs.pop()
    elif ufs != {uf}:
        raise ValueError(f"municípios de UFs diferentes ({sorted(ufs)}) ou fora da UF {uf}")
    resultado = _resultado("município", f"cod_municipio_ibge IN {cods}", uf)
    respostas = []
    for cod in cods:
        resposta, meta = _consultar(f"cod_municipio_ibge={cod}", uf, f"municipio_{cod}", atualizar)
        _registrar(resultado, meta, resposta)
        respostas.append(resposta)
    malhas = {c: malha_municipio(c, atualizar) for c in cods} if conferir_malha else None
    saida, descartados = transformar(respostas, resultado, malhas)
    resultado.saida = {"registros_produzidos": len(saida), "registros_descartados": len(descartados),
                       "registros_com_alerta": int((saida["alertas"] != "").sum())}
    resultado.status = "ok"
    return saida, resultado


def consultar_municipio(cod_ibge: str, uf: str | None = None,
                        atualizar: bool = False) -> tuple[pd.DataFrame, ResultadoFonte]:
    return consultar_municipios([cod_ibge], uf, atualizar)


def _consultar_filtro(tipo: str, cql: str, uf: str, atualizar: bool) -> tuple[pd.DataFrame, ResultadoFonte]:
    resultado = _resultado(tipo, cql, uf)
    nome = f"{tipo}_{hashlib.sha1(cql.encode()).hexdigest()[:16]}"
    resposta, meta = _consultar(cql, uf, nome, atualizar)
    _registrar(resultado, meta, resposta)
    saida, descartados = transformar([resposta], resultado)
    resultado.saida = {"registros_produzidos": len(saida), "registros_descartados": len(descartados)}
    resultado.status = "ok"
    return saida, resultado


def consultar_bbox(limites: tuple[float, float, float, float], uf: str | None = None,
                   atualizar: bool = False) -> tuple[pd.DataFrame, ResultadoFonte]:
    """Imóveis que tocam o retângulo `limites` = (lon_min, lat_min, lon_max, lat_max), sem filtro de município. Sem
    `uf`, vale a UF que contém o centro do retângulo (num retângulo de divisa, informe a UF de cada lado)."""
    if uf is None:
        uf = uf_da_area((limites[1] + limites[3]) / 2, (limites[0] + limites[2]) / 2)
    return _consultar_filtro("bbox", wfs.filtro_bbox(CAMPO_GEOMETRIA, limites), uf, atualizar)


def consultar_codigo(cod_imovel: str, atualizar: bool = False) -> tuple[pd.DataFrame, ResultadoFonte]:
    """O imóvel com o código dado; a UF sai do próprio código. Código fora do formato não é consultado."""
    cod = cod_imovel.strip().upper()
    if not re.fullmatch(FORMATO_CODIGO, cod):
        raise ValueError(f"código do CAR fora do formato UF-IBGE(7)-32 hexadecimais: {cod_imovel!r}")
    return _consultar_filtro("codigo", f"cod_imovel='{cod}'", cod[:2], atualizar)


def consultar_ponto(lat: float, lon: float, uf: str | None = None,
                    atualizar: bool = False) -> tuple[pd.DataFrame, ResultadoFonte]:
    """Imóveis que contêm o ponto (sede, coordenada de GPS). Sem `uf`, vale a UF do contorno que contém o ponto."""
    return _consultar_filtro("ponto", wfs.filtro_ponto(CAMPO_GEOMETRIA, lat, lon), uf or uf_da_area(lat, lon),
                             atualizar)


def geometrias(df: pd.DataFrame) -> np.ndarray:
    """Polígonos do DataFrame tratado (a geometria já passou por make_valid)."""
    return shapely.from_wkt(df["geometria_wkt"].to_numpy())
