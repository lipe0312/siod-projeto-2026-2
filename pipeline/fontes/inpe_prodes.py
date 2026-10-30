"""Fonte sob demanda: PRODES do INPE (incremento anual de desmatamento), pelo WFS do TerraBrasilis.

Consulta por bioma e retângulo (BBOX) ou UF, um ano PRODES por requisição, com cache da resposta bruta em
data/raw/inpe_prodes/. Devolve o DataFrame tratado e o ResultadoFonte.

Regras de leitura (docs/atividade-03/prodes-e-escada-de-fontes.md):
- a data que vale para a data de corte é `image_date` (recomendação do INPE); `publish_year` é sempre 01/01 do
  `year` e não informa a publicação, por isso é ignorado;
- o ano PRODES vai de 01/08 do ano anterior a 31/07 do ano; imagem fora desse intervalo é comum (período seco);
- o identificador é o `uuid`; a UF vem por extenso no Cerrado ("MINAS GERAIS") e como sigla na Mata Atlântica.
"""

import logging
import math

import pandas as pd
import shapely
from shapely.strtree import STRtree

from pipeline import config, wfs
from pipeline.municipios import normalizar_nome
from pipeline.validacao import Marcas, ResultadoFonte

log = logging.getLogger("pipeline")

CAMPO_GEOMETRIA = "geom"
CLASSE_DESMATAMENTO = "DESMATAMENTO"
LIMIAR_AREA_DIVERGENTE = 0.10

COLUNAS_SAIDA = [
    "uuid", "bioma", "ano_prodes", "data_imagem", "uf", "classe", "area_km2_fonte", "area_km2", "satelite", "sensor",
    "geometria_wkt", "alertas",
]
SITUACOES = ("confirmado", "já suprimido antes", "não confirmado", "aguardando consolidação", "geometria sem área")


def area_km2(geom) -> float:
    """Área aproximada (projeção equivalente local): suficiente para comparar com `area_km` e calcular proporções."""
    if geom is None or geom.is_empty:
        return 0.0
    lat0 = geom.centroid.y
    kx, ky = 111.320 * math.cos(math.radians(lat0)), 110.574
    return shapely.transform(geom, lambda c: c * [kx, ky]).area


def _url(camada: dict) -> str:
    return config.URL_WFS_INPE.format(workspace=camada["workspace"])


def filtro(ano: int, limites: tuple | None = None, uf: str | None = None, bioma: str = "cerrado") -> str:
    """CQL de um ano PRODES, por retângulo (lon_min, lat_min, lon_max, lat_max) e/ou UF (sigla)."""
    partes = [f"year={ano}"]
    if uf:
        por_extenso = config.CAMADAS_PRODES[bioma]["uf_por_extenso"]
        nome = {v: k for k, v in config.NOMES_UF.items()}[uf] if por_extenso else uf
        partes.insert(0, f"state='{nome}'")
    if limites:
        partes.insert(0, wfs.filtro_bbox(CAMPO_GEOMETRIA, limites))
    return " AND ".join(partes)


def resposta_para_tabela(resposta: dict) -> pd.DataFrame:
    linhas = []
    for f in resposta["features"]:
        g = f.get("geometry")
        linhas.append({**(f.get("properties") or {}), "id_feature": f.get("id"),
                       "geom": shapely.geometry.shape(g) if g else None})
    colunas = ["uuid", "state", "main_class", "class_name", "year", "image_date", "publish_year", "area_km",
               "satellite", "sensor", "id_feature", "geom"]
    return pd.DataFrame(linhas).reindex(columns=colunas)


def transformar(respostas: list[dict], bioma: str, resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    problemas = [p for p in map(wfs.problema_estrutural, respostas) if p]
    resultado.validar("PRODES_ESTRUTURA_RESPOSTA", "Resposta é FeatureCollection com lista de features"
                      + (f" ({problemas[0]})" if problemas else ""), "erro", "interrompe a consulta",
                      len(problemas), len(respostas))
    resultado.validar("PRODES_PARTICAO_INCOMPLETA", "Recebido diferente do numberMatched anunciado pelo serviço",
                      "erro", "interrompe a consulta; repetir", sum(map(wfs.incompleta, respostas)), len(respostas))
    resultado.validar("PRODES_CRS_INESPERADO", f"CRS diferente de {config.CRS_ESPERADO_WFS} (SIRGAS 2000)", "erro",
                      "interrompe a consulta", sum(not wfs.crs_esperado(r) for r in respostas if r["features"]),
                      len(respostas))
    tabelas = [resposta_para_tabela(r) for r in respostas]
    df = pd.concat(tabelas, ignore_index=True) if tabelas else resposta_para_tabela({"features": []})
    resultado.entrada["registros_recebidos"] = len(df)
    resultado.transformar("Conversão de cada feature GeoJSON em linha: propriedades e geometria")

    descartes = []

    def descartar(codigo, descricao, mascara):
        nonlocal df
        resultado.validar(codigo, descricao, "descarte", "registro vai para descartados", mascara, len(df))
        descartes.append(df[mascara].assign(motivo=codigo))
        df = df[~mascara].copy()

    descartar("PRODES_UUID_AUSENTE", "Polígono sem uuid", df["uuid"].isna())
    descartar("PRODES_UUID_DUPLICADO", "uuid repetido (retângulos ou anos que se sobrepõem trazem o mesmo polígono)",
              df["uuid"].duplicated())
    descartar("PRODES_CLASSE_FORA_DO_DOMINIO", f"main_class diferente de {CLASSE_DESMATAMENTO} (ex.: RESERVATORIO)",
              df["main_class"] != CLASSE_DESMATAMENTO)
    descartar("PRODES_GEOM_AUSENTE", "Geometria nula ou vazia",
              df["geom"].map(lambda g: g is None or g.is_empty).astype(bool))

    marcas = Marcas(df.index)
    n = len(df)
    invalida = df["geom"].map(lambda g: not g.is_valid).astype(bool)
    resultado.validar("PRODES_GEOM_INVALIDA", "Geometria inválida (shapely is_valid)", "correcao",
                      "shapely.make_valid antes de qualquer interseção", invalida, n)
    df["geom"] = [shapely.make_valid(g) for g in df["geom"]]

    uf_texto = df["state"].map(normalizar_nome)
    sigla = uf_texto.map(config.NOMES_UF).fillna(uf_texto.where(uf_texto.isin(config.UFS)))
    por_extenso = uf_texto.isin(config.NOMES_UF.keys())
    resultado.validar("PRODES_UF_NORMALIZADA", "UF gravada por extenso (ex.: MINAS GERAIS)", "correcao",
                      "convertida para a sigla", por_extenso, n)
    uf_invalida = sigla.isna()
    resultado.validar("PRODES_UF_INVALIDA", "UF que não é sigla nem nome de UF", "alerta", "UF anulada", uf_invalida, n)
    marcas.marcar("UF_INVALIDA", uf_invalida)
    df["uf"] = sigla

    df["ano_prodes"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["data_imagem"] = pd.to_datetime(df["image_date"], format="%Y-%m-%d", errors="coerce")
    sem_data = df["data_imagem"].isna()
    resultado.validar("PRODES_DATA_IMAGEM_AUSENTE", "image_date nula ou fora do formato AAAA-MM-DD", "alerta",
                      "sem data não entra na comparação com a data de corte", sem_data, n)
    marcas.marcar("DATA_IMAGEM_AUSENTE", sem_data)
    inicio = pd.to_datetime((df["ano_prodes"] - 1).astype("string") + "-08-01", errors="coerce")
    fim = pd.to_datetime(df["ano_prodes"].astype("string") + "-07-31", errors="coerce")
    fora_do_ano = (df["data_imagem"] < inicio) | (df["data_imagem"] > fim)
    resultado.validar("PRODES_DATA_FORA_DO_ANO_PRODES", "image_date fora de 01/08 do ano anterior a 31/07 do year",
                      "alerta", "mantido; a regra usa image_date, não year", fora_do_ano, n)
    marcas.marcar("DATA_FORA_DO_ANO_PRODES", fora_do_ano)
    publish = df["publish_year"].astype("string") != df["ano_prodes"].astype("string") + "-01-01"
    resultado.validar("PRODES_PUBLISH_YEAR_DIVERGENTE", "publish_year diferente de 01/01 do year", "alerta",
                      "campo ignorado", publish, n)
    resultado.transformar("publish_year ignorado: repete 01/01 do year e não informa a data de publicação; "
                          "vale image_date (data da imagem usada no mapeamento)")

    df["area_km2_fonte"] = pd.to_numeric(df["area_km"], errors="coerce")
    df["area_km2"] = df["geom"].map(area_km2)
    divergente = ((df["area_km2"] - df["area_km2_fonte"]).abs() / df["area_km2_fonte"] > LIMIAR_AREA_DIVERGENTE)
    resultado.validar("PRODES_AREA_DIVERGENTE", f"area_km difere mais de {LIMIAR_AREA_DIVERGENTE:.0%} da área "
                      "calculada da geometria", "alerta", "usar a área calculada", divergente, n)
    marcas.marcar("AREA_DIVERGENTE", divergente)
    resultado.transformar("Área calculada da geometria em projeção equivalente local (km²)")

    df["bioma"] = bioma
    df["classe"] = df["class_name"]
    df["satelite"], df["sensor"] = df["satellite"], df["sensor"]
    df["geometria_wkt"] = shapely.to_wkt(df["geom"].to_numpy(), rounding_precision=-1, trim=True) if n else []
    df["alertas"] = marcas.coluna()
    saida = df[COLUNAS_SAIDA].reset_index(drop=True)
    descartados = (pd.concat(descartes) if descartes else pd.DataFrame()).reindex(
        columns=["uuid", "main_class", "year", "state", "motivo"]).reset_index(drop=True)
    return saida, descartados


def consultar(bioma: str = "cerrado", limites: tuple | None = None, uf: str | None = None, desde: int = 2019,
              ate: int | None = None, atualizar: bool = False) -> tuple[pd.DataFrame, ResultadoFonte]:
    """PRODES de um bioma no retângulo `limites` (lon_min, lat_min, lon_max, lat_max) e/ou na UF, de `desde` até
    `ate` (anos PRODES, inclusive; padrão: o ano corrente). Um ano por requisição."""
    if limites is None and uf is None:
        raise ValueError("informe o retângulo, a UF ou os dois: o PRODES não é consultado em lote")
    camada = config.CAMADAS_PRODES[bioma]
    ate = ate or pd.Timestamp.today().year
    resultado = ResultadoFonte("inpe_prodes", "API (WFS/GeoJSON), sob demanda")
    resultado.entrada = {"servico": _url(camada), "camada": camada["tipo"], "requisicoes": []}
    recorte = (f"uf_{uf.lower()}" if uf else "") + ("_" if uf and limites else "") + (
        "bbox_" + "_".join(f"{v:.4f}" for v in limites) if limites else "")
    respostas = []
    for ano in range(desde, ate + 1):
        cql = filtro(ano, limites, uf, bioma)
        destino = config.DADOS_BRUTOS / "inpe_prodes" / bioma / recorte / f"{ano}.json.gz"
        resposta, meta = wfs.consultar_geojson(_url(camada), camada["tipo"], cql, destino, atualizar=atualizar,
                                               limite=config.PRODES_LIMITE_POR_REQUISICAO)
        resultado.entrada["requisicoes"].append({
            "ano": ano, "cql": cql, "arquivo": meta["arquivo"], "anunciado": resposta.get("numberMatched"),
            "recebido": len(resposta.get("features") or []), "consultado_em_utc": meta["consultado_em_utc"],
            "sha256": meta["sha256"]})
        respostas.append(resposta)
    resultado.transformar("Requisição ao WFS por ano PRODES, com cada resposta gravada compactada em "
                          "data/raw/inpe_prodes/")
    saida, descartados = transformar(respostas, bioma, resultado)
    resultado.saida = {"registros_produzidos": len(saida), "registros_descartados": len(descartados),
                       "por_ano": saida["ano_prodes"].value_counts().sort_index().to_dict()}
    resultado.status = "ok"
    return saida, resultado


def classificar_alerta(fracao_posterior: float, fracao_anterior: float, data_alerta: pd.Timestamp,
                       fim_ultimo_ano: pd.Timestamp, limiar: float = config.PRODES_LIMIAR_CONFIRMACAO) -> str:
    """Regra da seção 6 do estudo do PRODES (ADR 0009), para um alerta com área."""
    if fracao_posterior >= limiar:
        return "confirmado"
    if fracao_anterior >= limiar:
        return "já suprimido antes"
    if data_alerta > fim_ultimo_ano:
        return "aguardando consolidação"
    return "não confirmado"


def confirmar_alertas(alertas: pd.DataFrame, prodes: pd.DataFrame,
                      limiar: float = config.PRODES_LIMIAR_CONFIRMACAO, ultimo_ano: int | None = None) -> pd.DataFrame:
    """Situação de cada alerta DETER (colunas data_imagem e geometria_wkt) diante do PRODES tratado.

    confirmado: PRODES com imagem na data do alerta ou depois cobre ao menos `limiar` do alerta;
    já suprimido antes: a cobertura só existe com PRODES de imagem anterior ao alerta;
    não confirmado: nenhuma das duas, com o alerta num ano PRODES já publicado;
    aguardando consolidação: nenhuma das duas, com o alerta depois de 31/07 do último ano publicado.

    `ultimo_ano`: último ano PRODES publicado. Sem ele, vale o maior ano presente em `prodes`, o que só serve quando
    `prodes` cobre uma área grande (num recorte pequeno, um ano publicado pode não ter polígono nenhum).
    """
    pg = [shapely.make_valid(g) for g in shapely.from_wkt(prodes["geometria_wkt"].to_numpy())]
    datas_prodes = prodes["data_imagem"].to_numpy()
    anos_prodes = prodes["ano_prodes"].to_numpy()
    fim_ultimo_ano = pd.Timestamp(f"{int(ultimo_ano or prodes['ano_prodes'].max())}-07-31")
    arvore = STRtree(pg)
    linhas = []
    for wkt, d in zip(alertas["geometria_wkt"], pd.to_datetime(alertas["data_imagem"])):
        g = shapely.make_valid(shapely.from_wkt(wkt))
        area = area_km2(g)
        if area == 0:
            linhas.append({"area_alerta_km2": 0.0, "fracao_prodes_posterior": None, "fracao_prodes_anterior": None,
                           "anos_prodes": "", "situacao": "geometria sem área"})
            continue
        depois, antes, anos = [], [], set()
        for i in arvore.query(g, predicate="intersects"):
            inter = g.intersection(pg[i])
            if datas_prodes[i] >= d:
                depois.append(inter)
                anos.add(int(anos_prodes[i]))
            else:
                antes.append(inter)
        f_depois = area_km2(shapely.union_all(depois)) / area if depois else 0.0
        f_antes = area_km2(shapely.union_all(antes)) / area if antes else 0.0
        linhas.append({"area_alerta_km2": area, "fracao_prodes_posterior": f_depois, "fracao_prodes_anterior": f_antes,
                       "anos_prodes": ";".join(map(str, sorted(anos))),
                       "situacao": classificar_alerta(f_depois, f_antes, d, fim_ultimo_ano, limiar)})
    return pd.concat([alertas.reset_index(drop=True), pd.DataFrame(linhas)], axis=1)


def ano_prodes(datas: pd.Series) -> pd.Series:
    """Ano PRODES de uma data: de 01/08 do ano anterior a 31/07 do ano."""
    datas = pd.to_datetime(datas)
    return (datas.dt.year + (datas.dt.month >= 8)).astype("Int64")


