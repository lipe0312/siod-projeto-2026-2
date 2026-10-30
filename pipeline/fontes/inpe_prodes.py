"""Fonte PRODES do INPE (incremento anual de desmatamento), pelo WFS do TerraBrasilis. Duas formas de uso:

- em lote (`executar`, chamado por `python -m pipeline --fontes prodes`): os anos desde config.PRODES_DESDE nas UFs
  de config.PRODES_UFS_LOTE viram data/processed/inpe_prodes.parquet. A publicação é verificada a cada
  config.PRODES_INTERVALO_VERIFICACAO_DIAS (ver `verificar_e_baixar`);
- sob demanda (`consultar`): por bioma e retângulo (BBOX) ou UF, para imóvel fora do recorte do lote.

Um ano PRODES por requisição, com a resposta bruta gravada compactada em data/raw/inpe_prodes/.

Regras de leitura (docs/atividade-03/prodes-e-escada-de-fontes.md):
- a data que vale para a data de corte é `image_date` (recomendação do INPE); `publish_year` é sempre 01/01 do
  `year` e não informa a publicação, por isso é ignorado;
- o ano PRODES vai de 01/08 do ano anterior a 31/07 do ano; imagem fora desse intervalo é comum (período seco);
- o identificador é o `uuid`; a UF vem por extenso no Cerrado ("MINAS GERAIS") e como sigla na Mata Atlântica.
"""

import gzip
import hashlib
import json
import logging
import math
from datetime import datetime, timezone

import pandas as pd
import shapely
from shapely.strtree import STRtree

from pipeline import config, download, wfs
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


def transformar(respostas: list[dict], bioma: str | list[str], resultado: ResultadoFonte,
               hoje: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`bioma`: um para todas as respostas, ou um por resposta (o lote junta os biomas numa só tabela)."""
    problemas = [p for p in map(wfs.problema_estrutural, respostas) if p]
    resultado.validar("PRODES_ESTRUTURA_RESPOSTA", "Resposta é FeatureCollection com lista de features"
                      + (f" ({problemas[0]})" if problemas else ""), "erro", "interrompe a consulta",
                      len(problemas), len(respostas))
    resultado.validar("PRODES_PARTICAO_INCOMPLETA", "Recebido diferente do numberMatched anunciado pelo serviço",
                      "erro", "interrompe a consulta; repetir", sum(map(wfs.incompleta, respostas)), len(respostas))
    resultado.validar("PRODES_CRS_INESPERADO", f"CRS diferente de {config.CRS_ESPERADO_WFS} (SIRGAS 2000)", "erro",
                      "interrompe a consulta", sum(not wfs.crs_esperado(r) for r in respostas if r["features"]),
                      len(respostas))
    biomas = [bioma] * len(respostas) if isinstance(bioma, str) else bioma
    tabelas = [resposta_para_tabela(r).assign(bioma=b) for r, b in zip(respostas, biomas)]
    df = (pd.concat(tabelas, ignore_index=True) if tabelas else
          resposta_para_tabela({"features": []}).assign(bioma=pd.Series(dtype="object")))
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
    if hoje is not None:
        futura = df["data_imagem"] > hoje
        resultado.validar("PRODES_DATA_IMAGEM_FUTURA", "image_date depois da data da execução", "alerta",
                          "mantido e marcado", futura, n)
        marcas.marcar("DATA_IMAGEM_FUTURA", futura)
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


# ---------------------------------------------------------------------------------------------------------------
# Lote: recorte por UF, com verificação mensal da publicação
# ---------------------------------------------------------------------------------------------------------------

PASTA_LOTE = config.DADOS_BRUTOS / "inpe_prodes" / "lote"
ARQ_SAIDA = config.DADOS_PROCESSADOS / "inpe_prodes.parquet"
ARQ_DESCARTADOS = config.DADOS_PROCESSADOS / "inpe_prodes_descartados.parquet"
ARQ_PUBLICACAO = config.DADOS_PROCESSADOS / "inpe_prodes_publicacao.json"


def _relativo(caminho) -> str:
    return str(caminho.relative_to(config.RAIZ)) if caminho.is_relative_to(config.RAIZ) else str(caminho)


def hash_conteudo(resposta: dict) -> str:
    """SHA-256 das feições ordenadas pelo uuid. O hash da resposta inteira muda a cada pedido (o GeoServer grava
    `timeStamp`), então é este que diz se o INPE mudou um ano já baixado."""
    feicoes = sorted(resposta["features"], key=lambda f: str((f.get("properties") or {}).get("uuid")))
    return hashlib.sha256(json.dumps(feicoes, sort_keys=True).encode()).hexdigest()


def contagem_por_ano(bioma: str, ate: int) -> dict[str, int]:
    """Polígonos anunciados pelo serviço em cada ano, no Brasil inteiro (diz se o ano foi publicado)."""
    camada = config.CAMADAS_PRODES[bioma]
    return {str(ano): wfs.contar(_url(camada), camada["tipo"], f"year={ano}")
            for ano in range(config.PRODES_DESDE, ate + 1)}


def ultimo_ano(contagens: dict[str, int]) -> int | None:
    publicados = [int(a) for a, n in contagens.items() if n]
    return max(publicados) if publicados else None


def _datas(resposta: dict) -> tuple[str | None, str | None]:
    datas = sorted(d for f in resposta["features"] if (d := (f.get("properties") or {}).get("image_date")))
    return (datas[0], datas[-1]) if datas else (None, None)


def _verificacao_em_dia(anterior: dict | None, hoje: pd.Timestamp) -> bool:
    if not anterior or anterior.get("ufs") != list(config.PRODES_UFS_LOTE) or anterior.get("desde") != config.PRODES_DESDE:
        return False
    ultima = pd.Timestamp(anterior["verificado_em_utc"][:10])
    return (hoje.normalize() - ultima).days < config.PRODES_INTERVALO_VERIFICACAO_DIAS


def verificar_e_baixar(hoje: pd.Timestamp, atualizar: bool = False, verificar: bool = False) -> tuple[dict, bool]:
    """Verifica a publicação e baixa só o que mudou. Devolve (manifesto, se a verificação foi feita agora).

    Dentro do intervalo de verificação (e sem `atualizar` nem `verificar`), reaproveita o manifesto sem ir à rede.
    Fora dele, para cada bioma: conta os polígonos de cada ano no Brasil (o último ano com polígono é o último
    publicado) e, em cada ano e UF do recorte, compara a contagem com a do manifesto. Baixa de novo o ano cuja
    contagem mudou, o ano que ainda não estava no manifesto e sempre o último ano publicado (o INPE pode revisá-lo
    sem mudar a contagem). Cada mudança encontrada vai para o histórico do manifesto.
    """
    arq = PASTA_LOTE / "manifesto.json"
    anterior = json.loads(arq.read_text()) if arq.exists() else None
    if _verificacao_em_dia(anterior, hoje) and not (atualizar or verificar):
        log.info("[inpe_prodes] verificação de %s ainda vale (a cada %d dias); sem consulta ao serviço",
                 anterior["verificado_em_utc"][:10], config.PRODES_INTERVALO_VERIFICACAO_DIAS)
        return anterior, False
    mesmo_recorte = bool(anterior) and anterior.get("ufs") == list(config.PRODES_UFS_LOTE) and \
        anterior.get("desde") == config.PRODES_DESDE
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifesto = {"ufs": list(config.PRODES_UFS_LOTE), "desde": config.PRODES_DESDE, "verificado_em_utc": agora,
                 "proxima_verificacao": (hoje + pd.Timedelta(days=config.PRODES_INTERVALO_VERIFICACAO_DIAS))
                 .strftime("%Y-%m-%d"), "biomas": {}, "mudancas": [],
                 "historico": (anterior or {}).get("historico", []) if mesmo_recorte else []}
    for bioma, camada in config.CAMADAS_PRODES.items():
        antes = anterior["biomas"].get(bioma, {}) if mesmo_recorte else {}
        contagens = contagem_por_ano(bioma, hoje.year + 1)
        ultimo = ultimo_ano(contagens)
        info = {"camada": camada["tipo"], "servico": _url(camada), "anunciado_brasil": contagens,
                "ultimo_ano_publicado": ultimo, "anos": {}}
        ultimo_antes = antes.get("ultimo_ano_publicado")
        if ultimo_antes and ultimo != ultimo_antes:
            manifesto["mudancas"].append({"bioma": bioma, "ano": ultimo,
                                          "tipo": "novo ano publicado" if (ultimo or 0) > ultimo_antes
                                          else "último ano publicado recuou", "antes": ultimo_antes, "agora": ultimo})
        log.info("[inpe_prodes] %s: último ano publicado %s", bioma, ultimo)
        for ano in range(config.PRODES_DESDE, (ultimo or 0) + 1):
            for uf in config.PRODES_UFS_LOTE:
                chave = f"{ano}/{uf}"
                velho = antes.get("anos", {}).get(chave)
                cql = filtro(ano, uf=uf, bioma=bioma)
                anunciado = wfs.contar(_url(camada), camada["tipo"], cql)
                destino = PASTA_LOTE / bioma / uf.lower() / f"{ano}.json.gz"
                if (velho and not atualizar and velho["anunciado"] == anunciado and ano != ultimo
                        and destino.exists()):
                    info["anos"][chave] = velho
                    continue
                resposta, meta = wfs.consultar_geojson(_url(camada), camada["tipo"], cql, destino, atualizar=True,
                                                       limite=config.PRODES_LIMITE_POR_REQUISICAO)
                inicio, fim = _datas(resposta)
                registro = {"ano": ano, "uf": uf, "cql": cql, "anunciado": resposta.get("numberMatched", anunciado),
                            "recebido": len(resposta.get("features") or []), "arquivo": meta["arquivo"],
                            "baixado_em_utc": meta["consultado_em_utc"], "sha256_resposta": meta["sha256"],
                            "sha256_conteudo": hash_conteudo(resposta), "data_imagem_min": inicio,
                            "data_imagem_max": fim}
                if velho and velho["sha256_conteudo"] != registro["sha256_conteudo"]:
                    manifesto["mudancas"].append({
                        "bioma": bioma, "ano": ano, "uf": uf, "antes": velho["anunciado"], "agora": registro["anunciado"],
                        "tipo": "ano consolidado alterado" if ultimo and ano < ultimo else "último ano revisado"})
                elif not velho and mesmo_recorte:
                    manifesto["mudancas"].append({"bioma": bioma, "ano": ano, "uf": uf, "tipo": "ano baixado pela "
                                                  "primeira vez", "antes": None, "agora": registro["anunciado"]})
                info["anos"][chave] = registro
        manifesto["biomas"][bioma] = info
    manifesto["historico"].append({"verificado_em_utc": agora, "mudancas": manifesto["mudancas"],
                                   "ultimo_ano_publicado": {b: i["ultimo_ano_publicado"]
                                                            for b, i in manifesto["biomas"].items()}})
    PASTA_LOTE.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(manifesto, indent=2, ensure_ascii=False))
    return manifesto, True


def executar(hoje: pd.Timestamp, atualizar: bool = False, verificar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("inpe_prodes", "API (WFS/GeoJSON), lote com verificação mensal")
    manifesto, verificado_agora = verificar_e_baixar(hoje, atualizar, verificar)
    biomas = manifesto["biomas"]
    resultado.entrada = {
        "servico": config.URL_WFS_INPE.format(workspace="{bioma}"), "ufs": manifesto["ufs"],
        "desde": manifesto["desde"], "manifesto": _relativo(PASTA_LOTE / "manifesto.json"),
        "verificacao": "feita nesta execução" if verificado_agora else "reaproveitada (dentro do intervalo)",
        "verificado_em_utc": manifesto["verificado_em_utc"], "proxima_verificacao": manifesto["proxima_verificacao"],
        "ultimo_ano_publicado": {b: i["ultimo_ano_publicado"] for b, i in biomas.items()},
        "mudancas": manifesto["mudancas"] if verificado_agora else [],
    }
    resultado.transformar(f"Verificação da publicação a cada {config.PRODES_INTERVALO_VERIFICACAO_DIAS} dias: "
                          "contagem por ano no Brasil e por ano e UF no recorte; baixa só o que mudou e sempre o "
                          "último ano publicado")
    mudancas = resultado.entrada["mudancas"]
    n_anos = sum(len(i["anos"]) for i in biomas.values())
    resultado.validar("PRODES_ULTIMO_ANO_RECUOU", "Último ano publicado menor que o da verificação anterior", "erro",
                      "interrompe; conferir o serviço antes de substituir o parquet",
                      sum(m["tipo"] == "último ano publicado recuou" for m in mudancas), len(biomas))
    resultado.validar("PRODES_SEM_ANO_PUBLICADO", "Bioma sem nenhum ano com polígono no serviço", "erro",
                      "interrompe a fonte", sum(i["ultimo_ano_publicado"] is None for i in biomas.values()), len(biomas))
    resultado.validar("PRODES_NOVO_ANO_PUBLICADO", "Ano PRODES novo desde a verificação anterior", "alerta",
                      "baixado; alertas DETER do ano passam a ser confirmados ou não",
                      sum(m["tipo"] == "novo ano publicado" for m in mudancas), len(biomas))
    resultado.validar("PRODES_ANO_CONSOLIDADO_ALTERADO", "Ano anterior ao último mudou de conteúdo (o PRODES "
                      "consolidado não deveria mudar)", "alerta", "substituído pelo novo; mudança fica no histórico do "
                      "manifesto", sum(m["tipo"] == "ano consolidado alterado" for m in mudancas), n_anos)
    vazios = [c for i in biomas.values() for c, a in i["anos"].items() if a["anunciado"] == 0]
    resultado.validar("PRODES_ANO_SEM_POLIGONO_NO_RECORTE", "Ano publicado sem nenhum polígono numa UF do recorte",
                      "alerta", "mantido; conferir se a UF está no bioma", len(vazios), n_anos)

    respostas, rotulos = [], []
    for bioma, info in biomas.items():
        for a in info["anos"].values():
            respostas.append(json.loads(gzip.decompress((config.RAIZ / a["arquivo"]).read_bytes())))
            rotulos.append(bioma)
    saida, descartados = transformar(respostas, rotulos, resultado, hoje)
    config.DADOS_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    saida.to_parquet(ARQ_SAIDA, index=False)
    descartados.to_parquet(ARQ_DESCARTADOS, index=False)
    publicacao = {
        "verificado_em_utc": manifesto["verificado_em_utc"], "proxima_verificacao": manifesto["proxima_verificacao"],
        "ufs": manifesto["ufs"], "desde": manifesto["desde"],
        "ultimo_ano_publicado": resultado.entrada["ultimo_ano_publicado"],
        "anos": {b: {c: {k: a[k] for k in ("anunciado", "data_imagem_min", "data_imagem_max", "baixado_em_utc")}
                     for c, a in i["anos"].items()} for b, i in biomas.items()},
        "arquivo": _relativo(ARQ_SAIDA), "sha256": download.sha256(ARQ_SAIDA),
        "historico": manifesto["historico"],
    }
    ARQ_PUBLICACAO.write_text(json.dumps(publicacao, indent=2, ensure_ascii=False))
    resultado.saida = {
        "arquivo": _relativo(ARQ_SAIDA), "registros_produzidos": len(saida),
        "registros_com_alerta": int((saida["alertas"] != "").sum()),
        "por_bioma_e_ano": {f"{b}/{a}": int(n) for (b, a), n in saida.groupby(["bioma", "ano_prodes"]).size().items()},
        "colunas": list(saida.columns), "arquivo_descartados": _relativo(ARQ_DESCARTADOS),
        "registros_descartados": len(descartados), "arquivo_publicacao": _relativo(ARQ_PUBLICACAO),
    }
    resultado.status = "ok"
    return resultado


def ler_publicacao() -> dict | None:
    """Situação do PRODES em lote (inpe_prodes_publicacao.json), ou None se o lote ainda não rodou."""
    if not (ARQ_PUBLICACAO.exists() and ARQ_SAIDA.exists()):
        return None
    return json.loads(ARQ_PUBLICACAO.read_text())


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


