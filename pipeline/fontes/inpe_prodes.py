"""Fonte PRODES do INPE (incremento anual de desmatamento), pelo WFS do TerraBrasilis. Duas formas de uso:

- em lote (`executar`, chamado por `python -m pipeline --fontes prodes`, e `garantir_uf`, chamado pelo
  pré-diagnóstico): os anos desde config.PRODES_DESDE dos biomas de cada UF ativa viram uma partição por UF da tabela
  ref.desmatamento_prodes do lago, data/lago/ref/desmatamento_prodes/uf=XX/part.parquet, recortada pelo contorno da UF
  (ADR 0013 e 0017). O lote começa com config.PRODES_UFS_INICIAIS e ganha a UF de cada imóvel novo. A publicação é
  verificada a cada config.PRODES_INTERVALO_VERIFICACAO_DIAS (ver `verificar_e_baixar`);
- sob demanda (`consultar`): por bioma e retângulo (BBOX) ou UF (campo state), usado no caderno da Atividade 03.

Um ano PRODES (e uma parte do retângulo) por requisição, com a resposta bruta gravada compactada em
data/raw/inpe_prodes/.

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
import re
import shutil
import zipfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import shapefile
import shapely
from shapely.strtree import STRtree

from pipeline import config, download, vetor, wfs
from pipeline.armazenamento import contratos, historico, lago
from pipeline.municipios import normalizar_nome
from pipeline.validacao import Marcas, ResultadoFonte, Validacao

log = logging.getLogger("pipeline")

CAMPO_GEOMETRIA = "geom"
CLASSE_DESMATAMENTO = "DESMATAMENTO"
LIMIAR_AREA_DIVERGENTE = 0.10
CASAS_DECIMAIS = 6

COLUNAS_SAIDA = [
    "uuid", "bioma", "ano_prodes", "data_imagem", "uf", "data_publicacao", "classe", "area_km2_fonte", "area_km2",
    "satelite", "sensor", "geometria_wkt", "alertas",
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
    colunas = ["uuid", "state", "main_class", "class_name", "year", "image_date", "publish_year", "pub_date", "area_km",
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
    resultado.transformar("Conversão de cada feature GeoJSON em linha: propriedades e geometria")
    return tratar(df, resultado, hoje)


def tratar(df: pd.DataFrame, resultado: ResultadoFonte, hoje: pd.Timestamp | None = None) -> tuple[pd.DataFrame,
                                                                                                   pd.DataFrame]:
    """Validações e tratamento de uma tabela com as colunas de `resposta_para_tabela` mais `bioma` (geometria
    shapely em `geom`). Vale para a resposta do WFS e para o shapefile do bioma: as duas trazem os mesmos campos."""
    resultado.entrada["registros_recebidos"] = resultado.entrada.get("registros_recebidos", 0) + len(df)
    descartes = []

    def descartar(codigo, descricao, mascara):
        nonlocal df
        resultado.validar(codigo, descricao, "descarte", "registro vai para descartados", mascara, len(df))
        descartes.append(df[mascara].assign(motivo=codigo))
        df = df[~mascara].copy()

    descartar("PRODES_UUID_AUSENTE", "Polígono sem uuid", df["uuid"].isna())
    descartar("PRODES_UUID_DUPLICADO", "uuid repetido (retângulos ou anos que se sobrepõem trazem o mesmo polígono)",
              df["uuid"].duplicated())
    # A camada da Amazônia grava 2019 e 2020 (e parte dos anos seguintes) como "desmatamento", em minúsculas.
    classe = df["main_class"].astype("string").str.strip().str.upper()
    resultado.validar("PRODES_CLASSE_CAIXA_DIFERENTE", f"main_class igual a {CLASSE_DESMATAMENTO} só sem diferenciar "
                      "maiúsculas", "correcao", "normalizada para maiúsculas",
                      ((classe != df["main_class"]) & (classe == CLASSE_DESMATAMENTO)).fillna(False).astype(bool), len(df))
    df["main_class"] = classe.fillna(df["main_class"]).astype(object)
    descartar("PRODES_CLASSE_FORA_DO_DOMINIO", f"main_class diferente de {CLASSE_DESMATAMENTO} (ex.: RESERVATORIO)",
              df["main_class"] != CLASSE_DESMATAMENTO)
    descartar("PRODES_GEOM_AUSENTE", "Geometria nula ou vazia",
              df["geom"].map(lambda g: g is None or g.is_empty).astype(bool))

    marcas = Marcas(df.index)
    n = len(df)
    invalida = df["geom"].map(lambda g: not g.is_valid).astype(bool)
    resultado.validar("PRODES_GEOM_INVALIDA", "Geometria inválida (shapely is_valid)", "correcao",
                      "shapely.make_valid antes de qualquer interseção", invalida, n)
    df["geom"] = [vetor.tornar_valida(g) for g in df["geom"]]  # anel degenerado não interrompe

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
    # O shapefile do bioma não traz publish_year: só se compara onde o campo existe.
    publish = (df["publish_year"].notna()
               & (df["publish_year"].astype("string") != df["ano_prodes"].astype("string") + "-01-01")).fillna(False)
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

    # pub_date (AAAAMMDD) só existe em algumas camadas (Cerrado e Pampa): é a data de publicação do polígono.
    df["data_publicacao"] = pd.to_datetime(df["pub_date"].astype("string"), format="%Y%m%d", errors="coerce")
    df["classe"] = df["class_name"]
    df["satelite"], df["sensor"] = df["satellite"], df["sensor"]
    # 6 casas decimais (~0,1 m): o shapefile vem com precisão completa; o WFS já chega com 4 (~11 m).
    df["geometria_wkt"] = shapely.to_wkt(df["geom"].to_numpy(), rounding_precision=CASAS_DECIMAIS, trim=True) if n else []
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
# Lote: recorte por UF pelo contorno do IBGE, UFs incluídas à medida que os imóveis entram, verificação mensal
# ---------------------------------------------------------------------------------------------------------------

PASTA_LOTE = config.DADOS_BRUTOS / "inpe_prodes" / "lote"
TABELA = "ref.desmatamento_prodes"
COLUNAS_LOTE = COLUNAS_SAIDA[:4] + ["uf", "uf_fonte"] + COLUNAS_SAIDA[5:]


def pasta_tabela():
    return lago.pasta(TABELA)


def pasta_pecas():
    """Peças bioma x UF, temporárias (config.TRABALHO)."""
    return config.TRABALHO / "inpe_prodes_pecas"


# Estado operacional da fonte (publicação e manifestos): arquivos com "_" na pasta da tabela, fora das partições.
def arquivo_publicacao():
    return pasta_tabela() / "_publicacao.json"


def _arquivo_manifesto_wfs():
    return pasta_tabela() / "_manifesto_wfs.json"


def _arquivo_manifesto_arquivos():
    return pasta_tabela() / "_manifesto_arquivos.json"


def _ler_json(arquivo, legado=None) -> dict | None:
    """JSON de estado da fonte; `legado` é onde ele ficava antes do lago (só leitura, na transição)."""
    if not arquivo.exists() and legado is not None and legado.exists():
        log.warning("[inpe_prodes] %s ainda não está no lago; lido de %s (legado)", arquivo.name, _relativo(legado))
        arquivo = legado
    return json.loads(arquivo.read_text()) if arquivo.exists() else None


def _gravar_json(arquivo, dados: dict) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False))


def arquivo_uf(uf: str):
    """Partição de uma UF no lago (o pré-diagnóstico lê só a UF do imóvel). O sha256 dela é a chave de cache do
    pré-diagnóstico; o lago só regrava a partição que mudou."""
    return pasta_tabela() / f"uf={uf}" / "part.parquet"


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
    return {str(ano): wfs.contar(_url(camada), camada["tipo"], f"year={ano}", tentativas=TENTATIVAS_CONTAGEM)
            for ano in range(config.PRODES_DESDE, ate + 1)}


# A contagem do Brasil inteiro (sem filtro espacial) é a requisição mais pesada e a que mais recebe 502.
TENTATIVAS_CONTAGEM = 6


def ultimo_ano(contagens: dict[str, int]) -> int | None:
    publicados = [int(a) for a, n in contagens.items() if n]
    return max(publicados) if publicados else None


def _datas(resposta: dict) -> tuple[str | None, str | None]:
    datas = sorted(d for f in resposta["features"] if (d := (f.get("properties") or {}).get("image_date")))
    return (datas[0], datas[-1]) if datas else (None, None)


def _publicacao(resposta: dict) -> str | None:
    """Maior `pub_date` (AAAAMMDD) das feições, quando a camada traz o campo (Cerrado e Pampa trazem)."""
    datas = [str(d) for f in resposta["features"] if (d := (f.get("properties") or {}).get("pub_date"))]
    return pd.to_datetime(max(datas), format="%Y%m%d", errors="coerce").strftime("%Y-%m-%d") if datas else None


def _quadrantes(limites: tuple) -> list[tuple]:
    x0, y0, x1, y1 = limites
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    return [(x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1)]


def partes(bioma: str, ano: int, limites: tuple, chave: str = "0") -> list[tuple[str, tuple, int]]:
    """Retângulos de um (bioma, ano) que cabem numa requisição: se a contagem passa de PRODES_POLIGONOS_POR_PARTE, o
    retângulo é dividido em quatro, de novo, até caber. Retângulo vazio fica de fora. Devolve (chave da parte,
    retângulo, contagem)."""
    camada = config.CAMADAS_PRODES[bioma]
    n = wfs.contar(_url(camada), camada["tipo"], filtro(ano, limites), tentativas=TENTATIVAS_CONTAGEM)
    if n == 0 and chave != "0":
        return []
    if n <= config.PRODES_POLIGONOS_POR_PARTE:
        return [(chave, limites, n)]
    return [p for k, q in enumerate(_quadrantes(limites)) for p in partes(bioma, ano, q, f"{chave}-{k}")]


def biomas_da_uf(uf: str) -> list[str]:
    from pipeline import territorio

    return [b for b in territorio.biomas_da_geometria(territorio.contorno_uf(uf)) if b in config.CAMADAS_PRODES]


def _ufs_ativas(anterior: dict | None) -> list[str]:
    return sorted(set(config.PRODES_UFS_INICIAIS) | set((anterior or {}).get("ufs", [])))


def _ler_manifesto() -> dict | None:
    return _ler_json(_arquivo_manifesto_wfs(), PASTA_LOTE / "manifesto.json")


def _verificacao_em_dia(anterior: dict | None, hoje: pd.Timestamp) -> bool:
    if not anterior or anterior.get("desde") != config.PRODES_DESDE or "verificado_em_utc" not in anterior:
        return False
    ultima = pd.Timestamp(anterior["verificado_em_utc"][:10])
    return (hoje.normalize() - ultima).days < config.PRODES_INTERVALO_VERIFICACAO_DIAS


def _baixar_uf(uf: str, bioma: str, ultimo: int, antes: dict, mudancas: list, atualizar: bool,
               reaproveitar: bool) -> dict:
    """Anos de um bioma numa UF, pelo retângulo do contorno. Baixa a parte cuja contagem mudou, a nova e sempre o
    último ano publicado; com `reaproveitar` (UF que acabou de entrar), usa o que já estiver gravado, para retomar uma
    carga interrompida."""
    from pipeline import territorio

    camada = config.CAMADAS_PRODES[bioma]
    limites = territorio.contorno_uf(uf).bounds
    registros = {}
    for ano in range(config.PRODES_DESDE, ultimo + 1):
        pendentes = partes(bioma, ano, limites)
        while pendentes:
            parte, retangulo, anunciado = pendentes.pop(0)
            chave = f"{ano}/{uf}/{parte}"
            velho = antes.get(chave)
            destino = PASTA_LOTE / bioma / uf.lower() / f"{ano}_{parte}.json.gz"
            if (velho and not atualizar and velho["anunciado"] == anunciado and ano != ultimo and destino.exists()):
                registros[chave] = velho
                continue
            cql = filtro(ano, retangulo)
            try:
                resposta, meta = wfs.consultar_geojson(_url(camada), camada["tipo"], cql, destino,
                                                       atualizar=not reaproveitar or atualizar,
                                                       limite=config.PRODES_LIMITE_POR_REQUISICAO, tentativas=2)
            except requests.HTTPError as e:
                # 5xx mesmo abaixo do limite de polígonos: o gateway desistiu de esperar. Pede em quatro partes.
                if anunciado <= 1 or "HTTP 5" not in str(e):
                    raise
                log.warning("[inpe_prodes] %s %s %s: %s; dividindo a parte %s", bioma, uf, ano, e, parte)
                destino.unlink(missing_ok=True)
                destino.with_name(destino.name.removesuffix(".json.gz") + ".meta.json").unlink(missing_ok=True)
                pendentes[:0] = [p for k, q in enumerate(_quadrantes(retangulo))
                                 for p in partes(bioma, ano, q, f"{parte}-{k}")]
                continue
            inicio, fim = _datas(resposta)
            registro = {"ano": ano, "uf": uf, "parte": parte, "retangulo": list(retangulo), "cql": cql,
                        "anunciado": resposta.get("numberMatched", anunciado),
                        "recebido": len(resposta.get("features") or []), "arquivo": meta["arquivo"],
                        "baixado_em_utc": meta["consultado_em_utc"], "sha256_resposta": meta["sha256"],
                        "sha256_conteudo": hash_conteudo(resposta), "data_imagem_min": inicio,
                        "data_imagem_max": fim, "data_publicacao": _publicacao(resposta)}
            if velho and velho["sha256_conteudo"] != registro["sha256_conteudo"]:
                mudancas.append({"bioma": bioma, "ano": ano, "uf": uf, "antes": velho["anunciado"],
                                 "agora": registro["anunciado"],
                                 "tipo": "ano consolidado alterado" if ano < ultimo else "último ano revisado"})
            registros[chave] = registro
    return registros


def verificar_e_baixar(hoje: pd.Timestamp, atualizar: bool = False, verificar: bool = False,
                       incluir: tuple[str, ...] = ()) -> tuple[dict, bool, list[str]]:
    """Verifica a publicação e baixa só o que mudou. Devolve (manifesto, se a verificação foi feita agora, UFs
    cujos arquivos foram baixados ou revistos).

    Dentro do intervalo de verificação (e sem `atualizar` nem `verificar`), reaproveita o manifesto e só baixa as UFs
    de `incluir` que ainda não estão no lote (o último ano publicado de cada bioma vem da verificação anterior). Fora
    dele, para cada bioma: conta os polígonos de cada ano no Brasil (o último ano com polígono é o último publicado)
    e, em cada UF ativa, compara a contagem de cada ano e parte com a do manifesto. Cada mudança encontrada vai para o
    histórico do manifesto.
    """
    anterior = _ler_manifesto()
    # Manifesto de outro recorte (outro ano inicial, ou o formato por campo state, sem ufs_biomas): recomeça.
    if anterior and (anterior.get("desde") != config.PRODES_DESDE or "ufs_biomas" not in anterior):
        anterior = None
    ufs_antes = _ufs_ativas(anterior) if anterior else []
    ufs = sorted(set(_ufs_ativas(anterior)) | set(incluir))
    novas = [u for u in ufs if u not in ufs_antes]
    em_dia = _verificacao_em_dia(anterior, hoje) and not (atualizar or verificar)
    if em_dia and not novas:
        log.info("[inpe_prodes] verificação de %s ainda vale (a cada %d dias); sem consulta ao serviço",
                 anterior["verificado_em_utc"][:10], config.PRODES_INTERVALO_VERIFICACAO_DIAS)
        return anterior, False, []

    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifesto = {"desde": config.PRODES_DESDE, "ufs": ufs, "ufs_biomas": dict((anterior or {}).get("ufs_biomas", {})),
                 "biomas": {}, "mudancas": [], "historico": (anterior or {}).get("historico", [])}
    if em_dia:
        manifesto.update({k: anterior[k] for k in ("verificado_em_utc", "proxima_verificacao")})
    else:
        manifesto.update({"verificado_em_utc": agora, "proxima_verificacao": (
            hoje + pd.Timedelta(days=config.PRODES_INTERVALO_VERIFICACAO_DIAS)).strftime("%Y-%m-%d")})
    a_baixar = novas if em_dia else ufs
    for uf in a_baixar:
        manifesto["ufs_biomas"][uf] = biomas_da_uf(uf)
    em_uso = {b for uf in ufs for b in manifesto["ufs_biomas"][uf]}
    for bioma, camada in config.CAMADAS_PRODES.items():
        if bioma not in em_uso:  # nenhuma UF ativa tem o bioma: não conta nem baixa
            continue
        antes = (anterior or {}).get("biomas", {}).get(bioma, {})
        if em_dia and antes.get("ultimo_ano_publicado"):
            info = {**antes, "anos": dict(antes.get("anos", {}))}
            ultimo = info["ultimo_ano_publicado"]
        else:
            contagens = contagem_por_ano(bioma, hoje.year + 1)
            ultimo = ultimo_ano(contagens)
            info = {"camada": camada["tipo"], "servico": _url(camada), "anunciado_brasil": contagens,
                    "ultimo_ano_publicado": ultimo, "anos": {k: v for k, v in antes.get("anos", {}).items()
                                                             if k.split("/")[1] not in a_baixar}}
            ultimo_antes = antes.get("ultimo_ano_publicado")
            if ultimo_antes and ultimo != ultimo_antes:
                manifesto["mudancas"].append({"bioma": bioma, "ano": ultimo,
                                              "tipo": "novo ano publicado" if (ultimo or 0) > ultimo_antes
                                              else "último ano publicado recuou", "antes": ultimo_antes,
                                              "agora": ultimo})
            log.info("[inpe_prodes] %s: último ano publicado %s", bioma, ultimo)
        for uf in a_baixar:
            if bioma not in manifesto["ufs_biomas"][uf] or not ultimo:
                continue
            antes_uf = {k: v for k, v in antes.get("anos", {}).items() if k.split("/")[1] == uf}
            info["anos"].update(_baixar_uf(uf, bioma, ultimo, antes_uf, manifesto["mudancas"], atualizar,
                                           reaproveitar=uf in novas))
        manifesto["biomas"][bioma] = info
    for uf in novas:
        if ufs_antes:
            manifesto["mudancas"].append({"uf": uf, "tipo": "UF incluída no lote", "biomas": manifesto["ufs_biomas"][uf]})
    manifesto["historico"].append({"verificado_em_utc": agora, "mudancas": manifesto["mudancas"],
                                   "ufs": ufs, "ultimo_ano_publicado": {b: i["ultimo_ano_publicado"]
                                                                        for b, i in manifesto["biomas"].items()}})
    _gravar_json(_arquivo_manifesto_wfs(), manifesto)
    return manifesto, not em_dia, a_baixar


def _juntar(resultado: ResultadoFonte, parciais: list[ResultadoFonte]) -> None:
    """Soma as validações de cada UF numa linha por código, na ordem em que aparecem."""
    soma: dict[str, Validacao] = {}
    for p in parciais:
        for v in p.validacoes:
            if v.codigo in soma:
                soma[v.codigo].verificados += v.verificados
                soma[v.codigo].ocorrencias += v.ocorrencias
            else:
                soma[v.codigo] = Validacao(v.codigo, v.descricao, v.severidade, v.tratamento, v.verificados,
                                           v.ocorrencias)
    resultado.validacoes.extend(soma.values())


def construir_uf(uf: str, manifesto: dict, hoje: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.DataFrame,
                                                                                         ResultadoFonte]:
    """Partição de uma UF: todas as respostas da UF, tratadas, e só os polígonos que tocam o contorno da UF.

    `uf` é a UF da partição (um polígono de divisa entra nas duas UFs, uma linha em cada, como pede a chave
    [uuid, uf] do contrato); `uf_fonte` é o campo `state` do INPE. O alerta UF_DIFERE_DO_CONTORNO compara `state`
    com a UF do contorno que contém o ponto representativo do polígono.
    """
    from pipeline import territorio

    parcial = ResultadoFonte("inpe_prodes", "lote")
    respostas, rotulos = [], []
    for bioma, info in manifesto["biomas"].items():
        for chave, a in info["anos"].items():
            if chave.split("/")[1] == uf:
                respostas.append(json.loads(gzip.decompress((config.RAIZ / a["arquivo"]).read_bytes())))
                rotulos.append(bioma)
    saida, descartados = transformar(respostas, rotulos, parcial, hoje)
    geoms = shapely.from_wkt(saida["geometria_wkt"].to_numpy())
    contorno = territorio.contorno_uf(uf)
    shapely.prepare(contorno)
    dentro = shapely.intersects(contorno, geoms)
    parcial.validar("PRODES_FORA_DO_CONTORNO_DA_UF", "Polígono do retângulo da UF que não toca o contorno da UF",
                    "descarte", "fica fora da partição da UF (é de UF vizinha)", int((~dentro).sum()), len(saida))
    saida, geoms = saida[dentro].reset_index(drop=True), geoms[dentro]
    saida = saida.rename(columns={"uf": "uf_fonte"})
    uf_ponto = pd.Series(territorio.uf_por_contorno(geoms), index=saida.index, dtype=object)
    saida["uf"] = uf
    difere = saida["uf_fonte"].notna() & (saida["uf_fonte"] != uf_ponto)
    parcial.validar("PRODES_UF_DIFERE_DO_CONTORNO", "Campo state diferente da UF do contorno (polígono de divisa ou "
                    "gravado com a UF vizinha)", "alerta", "vale a UF do contorno; state fica em uf_fonte", difere,
                    len(saida))
    saida["alertas"] = saida["alertas"].where(~difere, (saida["alertas"] + ";UF_DIFERE_DO_CONTORNO").str.lstrip(";"))
    return saida[COLUNAS_LOTE], descartados.assign(uf_lote=uf), parcial


def _ultima_imagem_da_particao(uf: str, manifesto: dict) -> dict[str, str | None]:
    df = pd.read_parquet(arquivo_uf(uf), columns=["bioma", "ano_prodes", "data_imagem"])
    saida = {}
    for bioma in manifesto["ufs_biomas"].get(uf, []):
        ultimo = manifesto["biomas"].get(bioma, {}).get("ultimo_ano_publicado")
        datas = df.loc[(df["bioma"] == bioma) & (df["ano_prodes"] == ultimo), "data_imagem"].dropna()
        saida[bioma] = datas.max().strftime("%Y-%m-%d") if len(datas) else None
    return saida


def _gravar_publicacao(manifesto: dict) -> dict:
    biomas = manifesto["biomas"]
    publicacao = {
        "verificado_em_utc": manifesto["verificado_em_utc"], "proxima_verificacao": manifesto["proxima_verificacao"],
        "ufs": manifesto["ufs"], "ufs_biomas": manifesto["ufs_biomas"], "desde": manifesto["desde"],
        "ultimo_ano_publicado": {b: i["ultimo_ano_publicado"] for b, i in biomas.items()},
        "ultima_imagem": {b: max((a["data_imagem_max"] for a in i["anos"].values()
                                  if a["ano"] == i["ultimo_ano_publicado"] and a["data_imagem_max"]), default=None)
                          for b, i in biomas.items()},
        # Por UF: a última imagem do último ano varia de uma UF para outra; o aviso de "sem cobertura" de um imóvel usa a
        # da UF dele, lida da partição (já recortada pelo contorno), não do retângulo pedido ao serviço.
        "ultima_imagem_uf": {uf: _ultima_imagem_da_particao(uf, manifesto) for uf in manifesto["ufs"]
                             if arquivo_uf(uf).exists()},
        "data_publicacao": {b: max((a["data_publicacao"] for a in i["anos"].values() if a.get("data_publicacao")),
                                   default=None) for b, i in biomas.items()},
        "anos": {b: {c: {k: a.get(k) for k in ("anunciado", "data_imagem_min", "data_imagem_max", "baixado_em_utc")}
                     for c, a in i["anos"].items()} for b, i in biomas.items()},
        "particoes": {uf: {"arquivo": _relativo(arquivo_uf(uf)), "sha256": download.sha256(arquivo_uf(uf))}
                      for uf in manifesto["ufs"] if arquivo_uf(uf).exists()},
        "historico": manifesto["historico"],
    }
    _gravar_json(arquivo_publicacao(), publicacao)
    return publicacao


def _gravar_uf(df: pd.DataFrame, resultado: ResultadoFonte) -> bool:
    """Grava a partição de uma UF no lago (só se mudou) e soma o resumo no do resultado. Devolve se gravou."""
    resumo = lago.gravar(TABELA, df, carga_id=resultado.carga_id)
    total = resultado.saida.setdefault("tabelas", {}).setdefault(
        TABELA, {"historico": "acrescimo", "inseridos": 0, "alterados": 0, "removidos": 0, "particoes_gravadas": []})
    for k in ("inseridos", "alterados", "removidos"):
        total[k] += resumo[k]
    total["particoes_gravadas"] += resumo["particoes_gravadas"]
    return bool(resumo["particoes_gravadas"])


def _gravar_uf_vazia(uf: str) -> None:
    """UF sem polígono no recorte do WFS: partição vazia, para a UF constar da publicação (o lago não grava DataFrame
    vazio)."""
    contrato = contratos.carregar(TABELA)
    historico.gravar_parquet(pd.DataFrame(columns=[*contrato.nomes, *contrato.controle]), arquivo_uf(uf))


def _fechar_tabela(resultado: ResultadoFonte) -> None:
    resumo = resultado.saida.get("tabelas", {}).get(TABELA)
    if resumo:
        resultado.transformar(f"Gravado em {TABELA} (acrescimo, partição da UF substituída só quando muda): "
                              f"inseridos {resumo['inseridos']}, alterados {resumo['alterados']}, "
                              f"removidos {resumo['removidos']}, partições gravadas {len(resumo['particoes_gravadas'])}")


def _gravar_particoes(ufs: list[str], manifesto: dict, resultado: ResultadoFonte,
                      hoje: pd.Timestamp | None) -> dict[str, int]:
    """Constrói e grava a partição de cada UF; devolve as UFs cuja partição foi regravada, com o número de linhas."""
    parciais, descartes, produzidos = [], [], {}
    for uf in ufs:
        saida, descartados, parcial = construir_uf(uf, manifesto, hoje)
        if saida.empty:
            _gravar_uf_vazia(uf)
            produzidos[uf] = 0
        elif _gravar_uf(saida, resultado):
            produzidos[uf] = len(saida)
        parciais.append(parcial)
        descartes.append(descartados)
    _juntar(resultado, parciais)
    if descartes:
        lago.gravar_descartes(pd.concat(descartes, ignore_index=True), resultado, "uuid")
    _fechar_tabela(resultado)
    return produzidos


def garantir_uf(uf: str, hoje: pd.Timestamp | None = None) -> dict:
    """Inclui a UF no lote se ainda não estiver (o recorte cresce à medida que os imóveis entram) e devolve a
    publicação. A primeira carga de uma UF reaproveita o que já tiver sido baixado, para retomar se o serviço cair."""
    hoje = hoje or pd.Timestamp.today()
    publicacao = ler_publicacao()
    if publicacao and uf in publicacao["particoes"] and arquivo_uf(uf).exists():
        return publicacao
    if publicacao and publicacao.get("origem", "").startswith("arquivo"):
        # O lote pelo arquivo já cobre as 27 UFs: UF ausente é UF sem polígono (ou partição apagada); refaz o lote.
        log.info("[inpe_prodes] UF %s sem partição no lote pelo arquivo; refazendo as partições", uf)
        executar_arquivos(hoje)
        return ler_publicacao()
    log.info("[inpe_prodes] UF %s entra no lote", uf)
    manifesto, _, baixadas = verificar_e_baixar(hoje, incluir=(uf,))
    _gravar_particoes(sorted(set(baixadas) | {uf}), manifesto, ResultadoFonte("inpe_prodes", "lote"), hoje)
    return _gravar_publicacao(manifesto)


def executar(hoje: pd.Timestamp, atualizar: bool = False, verificar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("inpe_prodes", "API (WFS/GeoJSON), lote por UF com verificação mensal")
    manifesto, verificado_agora, baixadas = verificar_e_baixar(hoje, atualizar, verificar)
    biomas = manifesto["biomas"]
    resultado.entrada = {
        "servico": config.URL_WFS_INPE.format(workspace="{bioma}"), "ufs": manifesto["ufs"],
        "ufs_biomas": manifesto["ufs_biomas"], "desde": manifesto["desde"],
        "manifesto": _relativo(_arquivo_manifesto_wfs()),
        "verificacao": "feita nesta execução" if verificado_agora else "reaproveitada (dentro do intervalo)",
        "verificado_em_utc": manifesto["verificado_em_utc"], "proxima_verificacao": manifesto["proxima_verificacao"],
        "ultimo_ano_publicado": {b: i["ultimo_ano_publicado"] for b, i in biomas.items()},
        "mudancas": manifesto["mudancas"] if verificado_agora else [],
    }
    resultado.transformar(f"Verificação da publicação a cada {config.PRODES_INTERVALO_VERIFICACAO_DIAS} dias: "
                          "contagem por ano no Brasil e por ano, UF e parte do retângulo da UF; baixa só o que mudou e "
                          "sempre o último ano publicado")
    resultado.transformar("Requisição pelo retângulo do contorno da UF (IBGE), dividido em quatro enquanto passar de "
                          f"{config.PRODES_POLIGONOS_POR_PARTE} polígonos; o campo state não é usado no filtro")
    mudancas = resultado.entrada["mudancas"]
    n_anos = sum(len(i["anos"]) for i in biomas.values())
    resultado.validar("PRODES_ULTIMO_ANO_RECUOU", "Último ano publicado menor que o da verificação anterior", "erro",
                      "interrompe; conferir o serviço antes de substituir o lote",
                      sum(m["tipo"] == "último ano publicado recuou" for m in mudancas), len(biomas))
    resultado.validar("PRODES_SEM_ANO_PUBLICADO", "Bioma sem nenhum ano com polígono no serviço", "erro",
                      "interrompe a fonte", sum(i["ultimo_ano_publicado"] is None for i in biomas.values()), len(biomas))
    resultado.validar("PRODES_NOVO_ANO_PUBLICADO", "Ano PRODES novo desde a verificação anterior", "alerta",
                      "baixado; alertas DETER do ano passam a ser confirmados ou não",
                      sum(m["tipo"] == "novo ano publicado" for m in mudancas), len(biomas))
    resultado.validar("PRODES_ANO_CONSOLIDADO_ALTERADO", "Ano anterior ao último mudou de conteúdo (o PRODES "
                      "consolidado não deveria mudar)", "alerta", "substituído pelo novo; mudança fica no histórico do "
                      "manifesto", sum(m["tipo"] == "ano consolidado alterado" for m in mudancas), n_anos)
    divididos = sum(1 for i in biomas.values() for c in i["anos"] if not c.endswith("/0"))
    resultado.validar("PRODES_RETANGULO_DIVIDIDO", f"Ano e UF com mais de {config.PRODES_POLIGONOS_POR_PARTE} "
                      "polígonos no retângulo, pedido em partes", "correcao", "dividido em quatro até caber",
                      divididos, n_anos)

    a_gravar = [u for u in manifesto["ufs"] if u in baixadas or not arquivo_uf(u).exists()]
    produzidos = _gravar_particoes(a_gravar, manifesto, resultado, hoje)
    publicacao = _gravar_publicacao(manifesto)
    totais = {uf: len(pd.read_parquet(arquivo_uf(uf), columns=["uuid"])) for uf in manifesto["ufs"]
              if arquivo_uf(uf).exists()}
    resultado.saida.update({
        "arquivo": _relativo(pasta_tabela()), "particoes_regravadas": produzidos, "registros_por_uf": totais,
        "registros_produzidos": sum(totais.values()), "tabela_descartados": "meta.descarte",
        "arquivo_publicacao": _relativo(arquivo_publicacao()), "ultima_imagem": publicacao["ultima_imagem"],
        "colunas": COLUNAS_LOTE,
    })
    resultado.status = "ok"
    return resultado


# ---------------------------------------------------------------------------------------------------------------
# Lote pelo arquivo do bioma (ADR 0015): o shapefile completo que o INPE publica na área de download do TerraBrasilis.
# Contagem por ano idêntica à do WFS nos seis biomas (02/11/2026), em minutos em vez de horas, e as 27 UFs de uma vez.
# ---------------------------------------------------------------------------------------------------------------

PASTA_ARQUIVOS = config.DADOS_BRUTOS / "inpe_prodes" / "arquivo_bioma"
# Peças bioma x UF (pasta_pecas, em config.TRABALHO): com versão nova de um bioma, só as peças dele são refeitas e as
# partições das UFs são juntadas de novo.
_PADRAO_ARQUIVO = re.compile(r"/vector/yearly_deforestation_biome_(?P<bioma>[a-z_]+)_v(?P<versao>\d{8})\.zip$")
CAMPOS_ARQUIVO = ["uuid", "state", "main_class", "class_name", "year", "image_date", "area_km", "satellite", "sensor",
                  "fid", "pub_date"]


def catalogo(itens: list[dict]) -> dict[str, dict]:
    """Arquivo vetorial do incremento anual de cada bioma no catálogo do TerraBrasilis: {bioma: {url, versao,
    arquivo}}. O catálogo repete cada arquivo em português e em inglês; havendo duas versões, vale a mais nova. Ficam
    de fora as variantes da Amazônia (não floresta, polígonos menores que 6,25 ha), que o WFS do bioma também não traz."""
    saida: dict[str, dict] = {}
    for item in itens:
        m = _PADRAO_ARQUIVO.search(item.get("link") or "")
        if not m or m["bioma"] not in config.CAMADAS_PRODES or item.get("enabled") is False:
            continue
        v = m["versao"]
        versao = f"{v[:4]}-{v[4:6]}-{v[6:]}"
        if versao > saida.get(m["bioma"], {}).get("versao", ""):
            saida[m["bioma"]] = {"url": config.URL_TERRABRASILIS + item["link"], "versao": versao,
                                 "arquivo": item["link"].rsplit("/", 1)[-1]}
    return saida


def consultar_catalogo() -> dict[str, dict]:
    r = requests.get(config.URL_CATALOGO_TERRABRASILIS, timeout=60, headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    return catalogo(r.json())


def _texto_data(valor, formato: str) -> str | None:
    if valor in (None, ""):
        return None
    return valor.strftime(formato) if hasattr(valor, "strftime") else str(valor)


def _codificacao_dbf(caminho) -> str:
    """UTF-8 se todos os textos decodificam assim; senão latin1. O zip não traz .cpg."""
    leitor = shapefile.Reader(str(caminho), encoding="utf-8")
    textos = [f[0] for f in leitor.fields[1:] if f[1] == "C"]
    try:
        for _ in leitor.iterRecords(fields=textos):
            pass
        return "utf-8"
    except (shapefile.ShapefileException, UnicodeDecodeError):
        return "latin1"
    finally:
        leitor.close()


def ler_arquivo(caminho, bioma: str, resultado: ResultadoFonte, desde: int | None = None) -> pd.DataFrame:
    """Shapefile do bioma (zip) na forma de `resposta_para_tabela`, só com os anos desde `desde` (o arquivo começa em
    2000). Lê o DBF inteiro e só as geometrias dos anos que entram."""
    desde = config.PRODES_DESDE if desde is None else desde
    with zipfile.ZipFile(caminho) as z:
        prj = next((z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.lower().endswith(".prj")), "")
        # O .shx tem um cabeçalho de 100 bytes e 8 bytes por geometria.
        n_geoms = next(((i.file_size - 100) // 8 for i in z.infolist() if i.filename.lower().endswith(".shx")), -1)
    vetor.validar_crs_sirgas("PRODES", prj, resultado)
    codificacao = _codificacao_dbf(caminho)
    resultado.validar("PRODES_DBF_LATIN1", "DBF gravado em latin1, não em UTF-8 (o Cerrado grava assim)", "correcao",
                      "lido em latin1", int(codificacao == "latin1"), 1)
    leitor = shapefile.Reader(str(caminho), encoding=codificacao)
    resultado.validar("PRODES_ARQUIVO_INCOMPLETO", "Número de registros do DBF diferente do de geometrias do SHX",
                      "erro", "interrompe; baixar de novo", int(leitor.numRecords != n_geoms), 1)
    nomes = [f[0] for f in leitor.fields[1:]]
    campos = [c for c in CAMPOS_ARQUIVO if c in nomes]
    linhas, indices = [], []
    for i, registro in enumerate(leitor.iterRecords(fields=campos)):
        d = registro.as_dict()
        if (d.get("year") or 0) >= desde:
            linhas.append(d)
            indices.append(i)
    geoms = [shapely.force_2d(shapely.geometry.shape(s.__geo_interface__)) if s.shapeType else None
             for s in map(leitor.shape, indices)]
    leitor.close()
    df = pd.DataFrame(linhas, columns=campos)
    df["image_date"] = [_texto_data(v, "%Y-%m-%d") for v in df["image_date"]]
    df["pub_date"] = [_texto_data(v, "%Y%m%d") for v in df["pub_date"]] if "pub_date" in df else None
    df["id_feature"] = df.pop("fid") if "fid" in df else None
    df["publish_year"] = None  # o shapefile não traz o campo
    df["geom"] = pd.Series(geoms, index=df.index, dtype=object)
    resultado.transformar(f"Leitura do shapefile {caminho.name}: anos desde {desde}, geometria 2D")
    return df.reindex(columns=resposta_para_tabela({"features": []}).columns).assign(bioma=bioma)


def pecas_por_uf(saida: pd.DataFrame, resultado: ResultadoFonte) -> dict[str, pd.DataFrame]:
    """Polígonos tratados de um bioma divididos pelas UFs cujo contorno tocam (o de divisa entra nas duas, uma linha em
    cada). `uf` é a UF da peça; `uf_fonte`, o campo `state` do INPE. O alerta UF_DIFERE_DO_CONTORNO compara `state` com
    a UF do contorno que contém o ponto representativo."""
    from pipeline import territorio

    nomes, _, arvore = territorio._ufs()
    geoms = shapely.from_wkt(saida["geometria_wkt"].to_numpy())
    i_geom, i_uf = arvore.query(geoms, predicate="intersects")
    fora = np.ones(len(saida), dtype=bool)
    fora[i_geom] = False
    resultado.validar("PRODES_FORA_DE_TODAS_AS_UFS", "Polígono que não toca o contorno de nenhuma UF (IBGE)", "descarte",
                      "fica fora do lote", int(fora.sum()), len(saida))
    saida = saida.rename(columns={"uf": "uf_fonte"})
    uf_ponto = pd.Series(territorio.uf_por_contorno(geoms), index=saida.index, dtype=object)
    saida["uf"] = None
    difere = saida["uf_fonte"].notna() & uf_ponto.notna() & (saida["uf_fonte"] != uf_ponto)
    resultado.validar("PRODES_UF_DIFERE_DO_CONTORNO", "Campo state diferente da UF do contorno (polígono de divisa ou "
                      "gravado com a UF vizinha)", "alerta", "vale a UF do contorno; state fica em uf_fonte", difere,
                      len(saida))
    saida["alertas"] = saida["alertas"].where(~difere, (saida["alertas"] + ";UF_DIFERE_DO_CONTORNO").str.lstrip(";"))
    saida = saida[COLUNAS_LOTE]
    return {nomes[k]: saida.iloc[np.sort(i_geom[i_uf == k])].assign(uf=nomes[k]).reset_index(drop=True)
            for k in np.unique(i_uf)}


def _peca(bioma: str, uf: str):
    return pasta_pecas() / bioma / f"uf={uf}.parquet"


def processar_bioma(bioma: str, caminho, hoje: pd.Timestamp | None, parcial: ResultadoFonte) -> tuple[dict,
                                                                                                    pd.DataFrame]:
    """Lê, trata e grava as peças bioma x UF, temporárias (validações em `parcial`). Devolve o resumo do bioma para o
    manifesto e os descartados."""
    df = ler_arquivo(caminho, bioma, parcial)
    saida, descartados = tratar(df, parcial, hoje)
    del df
    pecas = pecas_por_uf(saida, parcial)
    shutil.rmtree(pasta_pecas() / bioma, ignore_errors=True)
    (pasta_pecas() / bioma).mkdir(parents=True, exist_ok=True)
    for uf, peca in pecas.items():
        peca.to_parquet(_peca(bioma, uf), index=False)
    ultimo = int(saida["ano_prodes"].max()) if len(saida) else None
    datas_ultimo = saida.loc[saida["ano_prodes"] == ultimo, "data_imagem"].dropna()
    publicacao = saida["data_publicacao"].dropna()
    info = {"ultimo_ano_publicado": ultimo, "ufs": sorted(pecas),
            "ultima_imagem": datas_ultimo.max().strftime("%Y-%m-%d") if len(datas_ultimo) else None,
            "data_publicacao": publicacao.max().strftime("%Y-%m-%d") if len(publicacao) else None,
            "anos": {str(a): int(n) for a, n in saida["ano_prodes"].value_counts().sort_index().items()},
            "registros": len(saida), "descartados": len(descartados)}
    return info, descartados.assign(bioma=bioma)


def juntar_particoes(ufs: list[str], refeitos: list[str], resultado: ResultadoFonte | None = None) -> dict[str, int]:
    """Partição de cada UF: as linhas que já estavam nela, dos biomas que não foram refeitos, mais as peças novas dos
    biomas refeitos, gravadas no lago (que só regrava a partição que mudou). Assim a versão nova de um bioma não obriga
    a ler os outros de novo. O mesmo uuid em dois biomas fica uma vez. Devolve as UFs regravadas, com as linhas."""
    produzidos, repetidos, total = {}, 0, 0
    destino = resultado or ResultadoFonte("inpe_prodes", "arquivo do bioma")
    for uf in ufs:
        partes = []
        if arquivo_uf(uf).exists():
            velha = pd.read_parquet(arquivo_uf(uf))
            partes.append(velha[~velha["bioma"].isin(refeitos)])
        partes += [pd.read_parquet(_peca(b, uf)) for b in refeitos if _peca(b, uf).exists()]
        partes = [p for p in partes if len(p)]
        if not partes:
            arquivo_uf(uf).unlink(missing_ok=True)
            continue
        df = pd.concat(partes, ignore_index=True)
        dup = df["uuid"].duplicated()
        repetidos, total = repetidos + int(dup.sum()), total + len(df)
        df = df[~dup].sort_values(["bioma", "ano_prodes", "uuid"]).reset_index(drop=True)
        if _gravar_uf(df, destino):
            produzidos[uf] = len(df)
    if resultado is not None:
        resultado.validar("PRODES_UUID_EM_DOIS_BIOMAS", "uuid presente no arquivo de dois biomas", "alerta",
                          "fica uma vez na partição", repetidos, total)
        _fechar_tabela(resultado)
    return produzidos


def _publicacao_arquivos(manifesto: dict) -> dict:
    """_publicacao.json no mesmo formato do lote pelo WFS (o pré-diagnóstico e a página leem os dois)."""
    biomas = manifesto["biomas"]
    particoes = {uf: {"arquivo": _relativo(arquivo_uf(uf)), "sha256": download.sha256(arquivo_uf(uf))}
                 for uf in sorted(config.UFS) if arquivo_uf(uf).exists()}
    ufs_biomas = {uf: sorted(b for b, i in biomas.items() if uf in i["ufs"]) for uf in particoes}
    ultima_uf = {}
    for uf in particoes:
        df = pd.read_parquet(arquivo_uf(uf), columns=["bioma", "ano_prodes", "data_imagem"])
        ultima_uf[uf] = {}
        for b in ufs_biomas[uf]:
            datas = df.loc[(df["bioma"] == b) & (df["ano_prodes"] == biomas[b]["ultimo_ano_publicado"]), "data_imagem"]
            ultima_uf[uf][b] = datas.max().strftime("%Y-%m-%d") if datas.notna().any() else None
    publicacao = {
        "origem": "arquivo do bioma (TerraBrasilis, área de download)",
        "verificado_em_utc": manifesto["verificado_em_utc"], "proxima_verificacao": manifesto["proxima_verificacao"],
        "ufs": sorted(particoes), "ufs_biomas": ufs_biomas, "desde": manifesto["desde"],
        "ultimo_ano_publicado": {b: i["ultimo_ano_publicado"] for b, i in biomas.items()},
        "ultima_imagem": {b: i["ultima_imagem"] for b, i in biomas.items()},
        "ultima_imagem_uf": ultima_uf,
        "data_publicacao": {b: i["data_publicacao"] or i["versao"] for b, i in biomas.items()},
        "arquivos": {b: {k: i[k] for k in ("url", "versao", "arquivo", "sha256", "tamanho_bytes", "baixado_em_utc")}
                     for b, i in biomas.items()},
        "anos": {b: {a: {"anunciado": n} for a, n in i["anos"].items()} for b, i in biomas.items()},
        "particoes": particoes, "historico": manifesto["historico"],
    }
    _gravar_json(arquivo_publicacao(), publicacao)
    return publicacao


def executar_arquivos(hoje: pd.Timestamp, atualizar: bool = False, verificar: bool = False,
                      catalogo_atual: dict | None = None) -> ResultadoFonte:
    """Lote das 27 UFs pelo arquivo de cada bioma. A cada PRODES_INTERVALO_VERIFICACAO_DIAS (ou com `verificar`),
    consulta o catálogo do TerraBrasilis; o bioma com versão nova é baixado e tratado de novo, e as partições das UFs
    que ele toca são juntadas de novo. Dentro do intervalo, não vai à rede."""
    resultado = ResultadoFonte("inpe_prodes", "arquivo (shapefile por bioma), lote das 27 UFs com verificação mensal")
    arq_manifesto = _arquivo_manifesto_arquivos()
    anterior = _ler_json(arq_manifesto, PASTA_ARQUIVOS / "manifesto.json")
    if anterior and anterior.get("desde") != config.PRODES_DESDE:
        anterior = None
    em_dia = (anterior is not None and not (atualizar or verificar)
              and (hoje.normalize() - pd.Timestamp(anterior["verificado_em_utc"][:10])).days
              < config.PRODES_INTERVALO_VERIFICACAO_DIAS)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mudancas, refeitos, parciais, descartes = [], [], [], []

    def processar(bioma: str, item: dict, destino) -> dict:
        meta = download.baixar(item["url"], destino, atualizar)
        parciais.append(ResultadoFonte("inpe_prodes", "arquivo do bioma"))
        resumo, descartados = processar_bioma(bioma, destino, hoje, parciais[-1])
        descartes.append(descartados)
        refeitos.append(bioma)
        log.info("[inpe_prodes] %s: versão %s, último ano %s, %d polígonos desde %d em %d UFs", bioma, item["versao"],
                 resumo["ultimo_ano_publicado"], resumo["registros"], config.PRODES_DESDE, len(resumo["ufs"]))
        return {**item, "sha256": meta["sha256"], "tamanho_bytes": meta["tamanho_bytes"],
                "baixado_em_utc": meta.get("baixado_em_utc"), **resumo}

    if em_dia:
        manifesto = anterior
        log.info("[inpe_prodes] verificação de %s ainda vale (a cada %d dias); sem consulta ao serviço",
                 anterior["verificado_em_utc"][:10], config.PRODES_INTERVALO_VERIFICACAO_DIAS)
    else:
        itens = catalogo_atual if catalogo_atual is not None else consultar_catalogo()
        faltando = sorted(set(config.CAMADAS_PRODES) - set(itens))
        resultado.validar("PRODES_BIOMA_FORA_DO_CATALOGO", "Bioma sem arquivo de incremento anual no catálogo do "
                          "TerraBrasilis" + (f" ({', '.join(faltando)})" if faltando else ""), "erro",
                          "interrompe; o lote anterior continua valendo", len(faltando), len(config.CAMADAS_PRODES))
        manifesto = {"desde": config.PRODES_DESDE, "verificado_em_utc": agora,
                     "proxima_verificacao": (hoje + pd.Timedelta(days=config.PRODES_INTERVALO_VERIFICACAO_DIAS)
                                             ).strftime("%Y-%m-%d"),
                     "biomas": dict((anterior or {}).get("biomas", {})),
                     # Na troca do WFS pelo arquivo, o histórico das verificações anteriores continua.
                     "historico": list((anterior or {}).get("historico") or (ler_publicacao() or {}).get("historico", []))}
        for bioma, item in sorted(itens.items()):
            antes = manifesto["biomas"].get(bioma)
            destino = PASTA_ARQUIVOS / item["arquivo"]
            if antes and antes["versao"] == item["versao"] and not atualizar:
                continue
            info = processar(bioma, item, destino)
            if antes:
                tipo = ("novo ano publicado" if (info["ultimo_ano_publicado"] or 0) > (antes["ultimo_ano_publicado"] or 0)
                        else "último ano publicado recuou" if (info["ultimo_ano_publicado"] or 0)
                        < (antes["ultimo_ano_publicado"] or 0) else "nova versão do arquivo")
                mudancas.append({"bioma": bioma, "ano": info["ultimo_ano_publicado"], "tipo": tipo,
                                 "antes": antes["versao"], "agora": info["versao"]})
                velho = PASTA_ARQUIVOS / antes["arquivo"]
                if velho != destino:
                    velho.unlink(missing_ok=True)
                    velho.with_suffix(".meta.json").unlink(missing_ok=True)
            manifesto["biomas"][bioma] = info
        manifesto["historico"].append({"verificado_em_utc": agora, "mudancas": mudancas, "biomas_refeitos": refeitos,
                                       "ultimo_ano_publicado": {b: i["ultimo_ano_publicado"]
                                                                for b, i in manifesto["biomas"].items()}})
    biomas = manifesto["biomas"]
    # UF sem partição (lote novo ou partição apagada): os biomas dela são tratados de novo a partir do arquivo local.
    faltam = sorted(u for u in config.UFS if not arquivo_uf(u).exists() and any(u in i["ufs"] for i in biomas.values()))
    for bioma in sorted({b for u in faltam for b, i in biomas.items() if u in i["ufs"]} - set(refeitos)):
        log.info("[inpe_prodes] %s tratado de novo a partir do arquivo local (UF sem partição: %s)", bioma,
                 ", ".join(u for u in faltam if u in biomas[bioma]["ufs"]))
        biomas[bioma] = processar(bioma, biomas[bioma], PASTA_ARQUIVOS / biomas[bioma]["arquivo"])
    _juntar(resultado, parciais)
    resultado.validar("PRODES_ULTIMO_ANO_RECUOU", "Último ano publicado menor que o da versão anterior do arquivo",
                      "alerta", "lote regravado com a versão nova; conferir o catálogo",
                      sum(m["tipo"] == "último ano publicado recuou" for m in mudancas), len(biomas))
    resultado.validar("PRODES_NOVO_ANO_PUBLICADO", "Ano PRODES novo desde a verificação anterior", "alerta",
                      "baixado; alertas DETER do ano passam a ser confirmados ou não",
                      sum(m["tipo"] == "novo ano publicado" for m in mudancas), len(biomas))
    # UFs que um bioma refeito toca, antes ou agora (a UF que perdeu todos os polígonos do bioma também é regravada).
    antes_ufs = {b: set(i.get("ufs", [])) for b, i in ((anterior or {}).get("biomas") or {}).items()}
    ufs = sorted({u for b in refeitos for u in set(biomas[b]["ufs"]) | antes_ufs.get(b, set())} | set(faltam))
    produzidos = juntar_particoes(ufs, refeitos, resultado) if ufs else {}
    shutil.rmtree(pasta_pecas(), ignore_errors=True)
    if descartes:
        lago.gravar_descartes(pd.concat(descartes, ignore_index=True), resultado, "uuid")
    if refeitos or not em_dia:
        _gravar_json(arq_manifesto, manifesto)
    publicacao = _publicacao_arquivos(manifesto) if (produzidos or not arquivo_publicacao().exists() or not em_dia) \
        else ler_publicacao()
    resultado.entrada = {
        "catalogo": config.URL_CATALOGO_TERRABRASILIS, "desde": manifesto["desde"],
        "arquivos": {b: {k: i[k] for k in ("url", "versao", "sha256")} for b, i in biomas.items()},
        "verificacao": "reaproveitada (dentro do intervalo)" if em_dia else "feita nesta execução",
        "verificado_em_utc": manifesto["verificado_em_utc"], "proxima_verificacao": manifesto["proxima_verificacao"],
        "ultimo_ano_publicado": {b: i["ultimo_ano_publicado"] for b, i in biomas.items()},
        "biomas_refeitos": refeitos, "mudancas": mudancas,
    }
    resultado.transformar("Catálogo do TerraBrasilis consultado a cada "
                          f"{config.PRODES_INTERVALO_VERIFICACAO_DIAS} dias; baixa e trata só o bioma com versão nova")
    resultado.transformar("Peças bioma x UF pelo contorno do IBGE (o polígono de divisa entra nas duas UFs); a partição "
                          "da UF troca só as linhas dos biomas refeitos")
    totais = {uf: p["arquivo"] for uf, p in publicacao["particoes"].items()}
    resultado.saida.update({"arquivo": _relativo(pasta_tabela()), "particoes_regravadas": produzidos,
                            "ufs": sorted(totais), "registros_produzidos": sum(i["registros"] for i in biomas.values()),
                            "arquivo_publicacao": _relativo(arquivo_publicacao()),
                            "tabela_descartados": "meta.descarte", "ultima_imagem": publicacao["ultima_imagem"],
                            "colunas": COLUNAS_LOTE})
    resultado.status = "ok"
    return resultado


def ler_publicacao() -> dict | None:
    """Situação do PRODES em lote (_publicacao.json na pasta da tabela), ou None se o lote ainda não rodou no formato
    por UF. Enquanto o lago não tem a publicação, vale a de data/processed (legado)."""
    publicacao = _ler_json(arquivo_publicacao(), config.DADOS_PROCESSADOS / "inpe_prodes_publicacao.json")
    return publicacao if publicacao and "particoes" in publicacao else None


def ler_uf(uf: str) -> pd.DataFrame:
    """Partição de uma UF no estado vigente (colunas do contrato mais carga_id)."""
    return lago.ler(TABELA, particao=uf)


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
    pg = [vetor.tornar_valida(g) for g in shapely.from_wkt(prodes["geometria_wkt"].to_numpy())]
    datas_prodes = prodes["data_imagem"].to_numpy()
    anos_prodes = prodes["ano_prodes"].to_numpy()
    fim_ultimo_ano = pd.Timestamp(f"{int(ultimo_ano or prodes['ano_prodes'].max())}-07-31")
    arvore = STRtree(pg)
    linhas = []
    for wkt, d in zip(alertas["geometria_wkt"], pd.to_datetime(alertas["data_imagem"])):
        g = vetor.tornar_valida(shapely.from_wkt(wkt))
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


