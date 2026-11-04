"""Fonte API: alertas de desmatamento DETER do INPE (serviço WFS, resposta GeoJSON), e o DETER do Pantanal pelo
shapefile da área de download do TerraBrasilis (o WFS não tem a camada; config.DETER_ARQUIVOS)."""

import gzip
import hashlib
import json
import logging
from datetime import datetime, timezone

import pandas as pd
import requests
import shapely

from pipeline import config, download, vetor, wfs
from pipeline.armazenamento import lago
from pipeline.municipios import normalizar_nome, resolver_por_nome
from pipeline.validacao import Marcas, ResultadoFonte

log = logging.getLogger("pipeline")

PROPRIEDADES_OBRIGATORIAS = ("gid", "classname", "view_date", "uf", "municipality")

COLUNAS_SAIDA = [
    "id_alerta", "camada", "gid", "classe", "data_imagem", "mes_publicacao", "uf", "cod_municipio", "municipio",
    "area_km2", "satelite", "sensor", "geometria_wkt", "alertas",
]


def _relativo(caminho) -> str:
    return str(caminho.relative_to(config.RAIZ)) if caminho.is_relative_to(config.RAIZ) else str(caminho)


def filtro_classes() -> str:
    return "classname IN (" + ",".join(f"'{c}'" for c in config.CLASSES_DESMATAMENTO) + ")"


def particoes_mensais(desde: str, hoje: pd.Timestamp) -> list[tuple[str, str]]:
    """Intervalos [início, fim) de um mês, do dia `desde` até o fim do mês corrente."""
    inicio = pd.Timestamp(desde)
    limite = (hoje.normalize().replace(day=1) + pd.offsets.MonthBegin(1))
    intervalos = []
    while inicio < limite:
        fim = inicio.replace(day=1) + pd.offsets.MonthBegin(1)
        intervalos.append((inicio.strftime("%Y-%m-%d"), fim.strftime("%Y-%m-%d")))
        inicio = fim
    return intervalos


def _url(camada: dict) -> str:
    return config.URL_WFS_INPE.format(workspace=camada["workspace"])


def _requisitar(camada: dict, parametros: dict, tentativas: int = 4) -> requests.Response:
    return wfs.requisitar(_url(camada), camada["tipo"], parametros, tentativas=tentativas)


def contar(camada: dict, cql: str) -> int:
    return wfs.contar(_url(camada), camada["tipo"], cql)


def baixar_camada(nome: str, desde: str, hoje: pd.Timestamp, atualizar: bool) -> dict:
    """Pede cada mês em uma única requisição e grava a resposta compactada. Devolve o manifesto."""
    camada = config.CAMADAS_DETER[nome]
    pasta = config.DADOS_BRUTOS / "inpe_deter" / nome / f"desde_{desde}"
    manifesto_arq = pasta / "manifesto.json"
    if manifesto_arq.exists() and not atualizar:
        manifesto = json.loads(manifesto_arq.read_text())
        if manifesto.get("completo") and manifesto.get("filtro_classes") == filtro_classes():
            log.info("[inpe_deter] %s: reutilizando %d partições baixadas em %s", nome,
                     len(manifesto["particoes"]), manifesto["iniciado_em_utc"])
            return manifesto
    for antigo in pasta.glob("*.json.gz"):
        antigo.unlink()
    pasta.mkdir(parents=True, exist_ok=True)

    particoes = particoes_mensais(desde, hoje)
    total = contar(camada, f"view_date>='{desde}' AND {filtro_classes()}")
    manifesto = {"camada": camada["tipo"], "url": config.URL_WFS_INPE.format(workspace=camada["workspace"]),
                 "filtro_classes": filtro_classes(), "desde": desde,
                 "limite_por_requisicao": config.DETER_LIMITE_POR_REQUISICAO, "total_anunciado": total,
                 "iniciado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "particoes": [], "completo": False}
    log.info("[inpe_deter] %s: %d alertas anunciados, pedidos em %d partições mensais", nome, total, len(particoes))
    for i, (inicio, fim) in enumerate(particoes, start=1):
        cql = f"view_date>='{inicio}' AND view_date<'{fim}' AND {filtro_classes()}"
        r = _requisitar(camada, {"outputFormat": "application/json", "count": config.DETER_LIMITE_POR_REQUISICAO,
                                 "CQL_FILTER": cql})
        arquivo = pasta / f"{inicio[:7]}.json.gz"
        arquivo.write_bytes(gzip.compress(r.content))
        manifesto["particoes"].append({"inicio": inicio, "fim": fim, "arquivo": arquivo.name,
                                       "sha256": hashlib.sha256(r.content).hexdigest()})
        if i % 12 == 0 or i == len(particoes):
            log.info("[inpe_deter] %s: partição %d de %d", nome, i, len(particoes))
    manifesto["completo"] = True
    manifesto_arq.write_text(json.dumps(manifesto, indent=2))
    return manifesto


def validar_estrutura(resposta, nome: str) -> str | None:
    """Devolve a descrição do problema estrutural, ou None se a resposta estiver no formato esperado."""
    if not isinstance(resposta, dict):
        return f"{nome}: resposta não é um objeto JSON"
    if resposta.get("type") != "FeatureCollection":
        return f"{nome}: type diferente de FeatureCollection"
    if not isinstance(resposta.get("features"), list):
        return f"{nome}: campo features ausente ou não é lista"
    return None


def resposta_para_tabela(resposta: dict, nome: str) -> pd.DataFrame:
    linhas, geometrias = [], []
    for f in resposta["features"]:
        p = f.get("properties") or {}
        linhas.append({
            "camada": nome, "gid": p.get("gid"), "classe": p.get("classname"), "view_date": p.get("view_date"),
            "publish_month": p.get("publish_month"), "uf": p.get("uf"), "municipio_fonte": p.get("municipality"),
            "mun_geocod": p.get("mun_geocod"), "area_fonte": p.get("areamunkm"),
            "satelite": p.get("satellite"), "sensor": p.get("sensor"),
            **{f"tem_{k}": k in p for k in PROPRIEDADES_OBRIGATORIAS},
        })
        geometrias.append(json.dumps(f["geometry"]) if f.get("geometry") else None)
    tabela = pd.DataFrame(linhas)
    if tabela.empty:
        return tabela
    geom = pd.Series(geometrias, dtype=object)
    lidas = pd.Series(shapely.from_geojson(geom.fillna("null").to_numpy(), on_invalid="ignore"), dtype=object)
    ok = lidas.notna() & geom.notna()
    lim = config.LIMITES_BRASIL
    tabela["geom_ausente"] = ~ok
    tabela["geom_fora_brasil"] = False
    tabela["geom_invalida"] = False
    tabela["geometria_wkt"] = None
    if ok.any():
        arr = lidas[ok].to_numpy()
        b = shapely.bounds(arr)
        fora = ~((b[:, 1] >= lim["lat_min"]) & (b[:, 3] <= lim["lat_max"]) & (b[:, 0] >= lim["lon_min"]) & (b[:, 2] <= lim["lon_max"]))
        tabela.loc[ok, "geom_fora_brasil"] = fora
        tabela.loc[ok, "geom_invalida"] = ~shapely.is_valid(arr)
        tabela.loc[ok, "geometria_wkt"] = shapely.to_wkt(arr, rounding_precision=6, trim=True)
    return tabela


def tabela_arquivo(caminho, nome: str, resultado: ResultadoFonte) -> pd.DataFrame:
    """Shapefile do DETER (área de download) na forma de `resposta_para_tabela`. A classe é traduzida para a do WFS
    (config.DETER_ARQUIVOS); a UF vem do contorno do IBGE, e o município fica sem código (o arquivo não traz)."""
    from pipeline import territorio

    info = config.DETER_ARQUIVOS[nome]
    registros, geoms, prj, _ = vetor.ler_shapefile_zip(caminho, info["base_shapefile"])
    vetor.validar_crs_sirgas(f"DETER_{nome.upper()}", prj, resultado)
    df = pd.DataFrame(registros)
    classe = df["CLASS_NAME"].astype("string").str.strip()
    traduzida = classe.str.lower().map(info["classes"])
    resultado.validar(f"DETER_{nome.upper()}_CLASSE_TRADUZIDA", "Classe de supressão do arquivo traduzida para a do "
                      f"WFS ({'; '.join(f'{k} = {v}' for k, v in info['classes'].items())})", "correcao",
                      "vale a classe do WFS", traduzida.notna(), len(df))
    presentes = pd.Series([g is not None and not g.is_empty for g in geoms])
    ufs = pd.Series([None] * len(df), dtype=object)
    if presentes.any():
        ufs[presentes.to_numpy()] = territorio.uf_por_contorno(geoms[presentes.to_numpy()])
    lim = config.LIMITES_BRASIL
    b = shapely.bounds(geoms.astype(object))
    tabela = pd.DataFrame({
        "camada": nome, "gid": df["UUID"].astype("string"), "classe": traduzida.fillna(classe),
        "view_date": [v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else None for v in df["VIEW_DATE"]],
        "publish_month": None, "uf": ufs, "municipio_fonte": None, "mun_geocod": None, "area_fonte": df["AREA_KM"],
        "satelite": df["SATELLITE"], "sensor": df["SENSOR"],
        **{f"tem_{k}": k != "municipality" for k in PROPRIEDADES_OBRIGATORIAS},
        "geom_ausente": ~presentes,
        "geom_fora_brasil": presentes & ~((b[:, 1] >= lim["lat_min"]) & (b[:, 3] <= lim["lat_max"])
                                          & (b[:, 0] >= lim["lon_min"]) & (b[:, 2] <= lim["lon_max"])),
        "geom_invalida": presentes & ~shapely.is_valid(geoms.astype(object)),
        "geometria_wkt": [shapely.to_wkt(g, rounding_precision=6, trim=True) if ok else None
                          for g, ok in zip(geoms, presentes)]})
    resultado.entrada.setdefault("camadas", {})[nome] = {"arquivo": str(caminho.relative_to(config.RAIZ))
                                                         if caminho.is_relative_to(config.RAIZ) else str(caminho),
                                                         "recebidos": len(tabela)}
    resultado.transformar(f"DETER {nome}: shapefile da área de download; UF pelo contorno do IBGE")
    return tabela


def consolidar(fluxo, esperados: dict, resultado: ResultadoFonte) -> pd.DataFrame:
    """Lê as respostas uma a uma (camada, nome da partição, JSON), valida estrutura e completude e junta as tabelas."""
    problemas, incompletas, crs_inesperado, recebidos, lidas, tabelas = [], [], [], {}, {}, []
    for nome, particao, resposta in fluxo:
        lidas[nome] = lidas.get(nome, 0) + 1
        problema = validar_estrutura(resposta, f"{nome}/{particao}")
        if problema:
            problemas.append(problema)
            continue
        if lidas[nome] == 1 and config.CRS_ESPERADO_DETER not in json.dumps(resposta.get("crs", {})):
            crs_inesperado.append(nome)
        anunciados = resposta.get("numberMatched")
        if isinstance(anunciados, int) and len(resposta["features"]) < anunciados:
            incompletas.append(f"{nome}/{particao}")
        recebidos[nome] = recebidos.get(nome, 0) + len(resposta["features"])
        tabela = resposta_para_tabela(resposta, nome)
        if not tabela.empty:
            tabelas.append(tabela)

    total = sum(lidas.values())
    resultado.validar("DETER_ESTRUTURA_RESPOSTA", "Resposta é FeatureCollection com lista de features"
                      + (f" ({problemas[0]})" if problemas else ""), "erro", "interrompe a fonte", len(problemas), total)
    resultado.validar("DETER_PARTICAO_INCOMPLETA", "Resposta com menos features do que o próprio serviço anunciou"
                      + (f" ({incompletas[0]})" if incompletas else ""), "erro", "interrompe a fonte",
                      len(incompletas), total)
    resultado.validar("DETER_CRS_INESPERADO", f"Sistema de coordenadas diferente de {config.CRS_ESPERADO_DETER} (SIRGAS 2000)",
                      "erro", "interrompe a fonte", len(crs_inesperado), len(lidas))
    for nome in lidas:
        resultado.entrada.setdefault("camadas", {})[nome] = {"anunciados": esperados[nome],
                                                             "recebidos": recebidos.get(nome, 0), "particoes": lidas[nome]}
        resultado.validar(f"DETER_CONTAGEM_DIVERGENTE_{nome.upper()}",
                          f"Alertas recebidos ({recebidos.get(nome, 0)}) diferentes do total anunciado no início da coleta ({esperados[nome]})",
                          "alerta", "segue com o que foi recebido; indica mudança na base durante a coleta",
                          int(recebidos.get(nome, 0) != esperados[nome]), 1)
    resultado.entrada["registros_recebidos"] = sum(recebidos.values())
    resultado.transformar("Conversão de cada feature GeoJSON em linha: propriedades selecionadas e geometria em WKT (6 casas decimais)")
    return pd.concat(tabelas, ignore_index=True) if tabelas else pd.DataFrame()


def transformar(respostas: dict, esperados: dict, ref_municipios: pd.DataFrame, desde: str, hoje: pd.Timestamp,
                resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`respostas`: {camada: [resposta_json, ...]}; `esperados`: {camada: total anunciado}."""
    fluxo = ((nome, f"parte {i}", resp) for nome, lista in respostas.items() for i, resp in enumerate(lista, start=1))
    return transformar_tabela(consolidar(fluxo, esperados, resultado), ref_municipios, desde, hoje, resultado)


def transformar_tabela(df: pd.DataFrame, ref_municipios: pd.DataFrame, desde: str, hoje: pd.Timestamp,
                       resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(df)
    # As propriedades obrigatórias são as do WFS; o shapefile do Pantanal não traz município (a UF vem do contorno).
    wfs_df = df[~df["camada"].isin(config.DETER_ARQUIVOS)] if n else df
    for k in PROPRIEDADES_OBRIGATORIAS:
        resultado.validar(f"DETER_PROPRIEDADE_{k.upper()}_AUSENTE", f"Propriedade '{k}' ausente em todas as features",
                          "erro", "interrompe a fonte", int(len(wfs_df) > 0 and not wfs_df[f"tem_{k}"].any()), 1)

    descartes = []

    def descartar(codigo, descricao, mascara):
        nonlocal df
        resultado.validar(codigo, descricao, "descarte", "registro vai para descartados", mascara, len(df))
        descartes.append(df[mascara].assign(motivo=codigo))
        df = df[~mascara].copy()

    descartar("DETER_GID_AUSENTE", "Feature sem identificador gid", df["gid"].isna())
    descartar("DETER_GEOM_AUSENTE", "Feature sem geometria legível", df["geom_ausente"])

    chave_municipio = df["municipio_fonte"].map(normalizar_nome) + "|" + df["uf"].fillna("").astype(str).str.upper()
    conteudo = df["gid"].astype(str) + "|" + df["view_date"].astype(str) + "|" + chave_municipio + "|" + df["geometria_wkt"]
    df["id_alerta"] = df["camada"] + ":" + df["gid"].astype(str) + ":" + conteudo.map(
        lambda t: hashlib.sha1(t.encode()).hexdigest()[:12])
    grupos = df.groupby(["camada", "gid"])
    varios = grupos["gid"].transform("size") > 1
    mesma_data = grupos["view_date"].transform("nunique") == 1
    divididos = df.loc[varios & mesma_data, ["camada", "gid"]].drop_duplicates()
    reutilizados = df.loc[varios & ~mesma_data, ["camada", "gid"]].drop_duplicates()
    resultado.transformar(
        "Identificador id_alerta = camada + gid + hash de (gid, data, município, geometria), porque o gid não é único: "
        f"{len(divididos)} gids são um mesmo alerta dividido entre municípios e {len(reutilizados)} gids são "
        "reutilizados por alertas de datas diferentes")
    descartar("DETER_ALERTA_DUPLICADO", "Mesmo gid, data, município e geometria recebidos mais de uma vez",
              df["id_alerta"].duplicated())
    descartar("DETER_CLASSE_FORA_DO_RECORTE", "Classe diferente de desmatamento",
              ~df["classe"].isin(config.CLASSES_DESMATAMENTO))
    data = pd.to_datetime(df["view_date"], format="%Y-%m-%d", errors="coerce")
    descartar("DETER_DATA_INVALIDA", "Data da imagem ausente ou fora do formato AAAA-MM-DD", data.isna())
    data = pd.to_datetime(df["view_date"], format="%Y-%m-%d")
    descartar("DETER_DATA_FORA_DO_RECORTE", f"Data da imagem antes de {desde} ou depois da execução",
              (data < pd.Timestamp(desde)) | (data > hoje))
    descartar("DETER_GEOM_FORA_BRASIL", "Geometria fora do retângulo do território brasileiro", df["geom_fora_brasil"])

    marcas = Marcas(df.index)
    df["data_imagem"] = pd.to_datetime(df["view_date"], format="%Y-%m-%d")
    df["mes_publicacao"] = pd.to_datetime(df["publish_month"], format="%Y-%m-%d", errors="coerce")
    resultado.transformar("Datas da imagem e do mês de publicação convertidas de texto")

    df["uf"] = df["uf"].astype("string").str.strip().str.upper()
    uf_invalida = ~df["uf"].isin(config.UFS).fillna(False)
    resultado.validar("DETER_UF_INVALIDA", "UF fora das 27 siglas", "alerta", "mantido", uf_invalida, len(df))
    marcas.marcar("UF_INVALIDA", uf_invalida)

    cod_nome, corrigido = resolver_por_nome(df["municipio_fonte"], df["uf"], ref_municipios)
    cod_fonte = df["mun_geocod"].astype("string").str.strip()
    divergente = cod_fonte.notna() & cod_nome.notna() & (cod_fonte != cod_nome)
    df["cod_municipio"] = cod_fonte.fillna(cod_nome)
    nao_identificado = df["cod_municipio"].isna() | ~df["cod_municipio"].isin(ref_municipios["cod_municipio"])
    resultado.validar("DETER_MUNICIPIO_APELIDO", "Nome de município diferente do oficial (tabela de apelidos)",
                      "correcao", "nome substituído pelo oficial antes de buscar o código", corrigido, len(df))
    resultado.validar("DETER_MUNICIPIO_CODIGO_DIVERGENTE", "Código IBGE da fonte diferente do código obtido pelo nome",
                      "alerta", "mantido o código da fonte", divergente, int(cod_fonte.notna().sum()))
    resultado.validar("DETER_MUNICIPIO_NAO_IDENTIFICADO", "Município sem código IBGE válido", "alerta",
                      "código anulado", nao_identificado, len(df))
    marcas.marcar("MUNICIPIO_CODIGO_DIVERGENTE", divergente)
    marcas.marcar("MUNICIPIO_NAO_IDENTIFICADO", nao_identificado)
    df["cod_municipio"] = df["cod_municipio"].mask(nao_identificado)
    df["municipio"] = df["cod_municipio"].map(ref_municipios.set_index("cod_municipio")["municipio"])
    resultado.transformar("Código IBGE do município: o da fonte (Amazônia) ou resolvido por nome + UF (Cerrado, que não traz código)")

    area = pd.to_numeric(df["area_fonte"], errors="coerce")
    area_nao_positiva = area.isna() | (area <= 0)
    resultado.validar("DETER_AREA_NAO_POSITIVA", "Área ausente, zero ou negativa", "alerta", "área anulada",
                      area_nao_positiva, len(df))
    marcas.marcar("AREA_NAO_POSITIVA", area_nao_positiva)
    df["area_km2"] = area.mask(area_nao_positiva)
    resultado.transformar("Área do trecho no município (areamunkm), em km²")

    resultado.validar("DETER_GEOM_INVALIDA", "Polígono topologicamente inválido", "alerta",
                      "geometria mantida sem correção", df["geom_invalida"], len(df))
    marcas.marcar("GEOM_INVALIDA", df["geom_invalida"])
    repetida = df.duplicated(subset=["camada", "classe", "data_imagem", "geometria_wkt"], keep=False)
    resultado.validar("DETER_GEOMETRIA_REPETIDA", "Mesma classe, data e geometria em gids diferentes", "alerta",
                      "mantido", repetida, len(df))
    marcas.marcar("GEOMETRIA_REPETIDA", repetida)

    df["alertas"] = marcas.coluna()
    saida = df[COLUNAS_SAIDA].reset_index(drop=True)
    colunas_desc = ["id_alerta", "camada", "gid", "classe", "view_date", "uf", "municipio_fonte", "motivo"]
    descartados = (pd.concat(descartes) if descartes else pd.DataFrame()).reindex(columns=colunas_desc).reset_index(drop=True)
    return saida, descartados


def executar(ref_municipios: pd.DataFrame, hoje: pd.Timestamp, desde: str = config.DETER_DESDE_PADRAO,
             atualizar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("inpe_deter", "API (WFS/GeoJSON)")
    resultado.entrada = {"servico": config.URL_WFS_INPE.format(workspace="{camada}"),
                         "filtro": f"view_date>='{desde}' AND {filtro_classes()}", "manifestos": {}}
    esperados, pastas = {}, {}
    for nome in config.CAMADAS_DETER:
        manifesto = baixar_camada(nome, desde, hoje, atualizar)
        pastas[nome] = (config.DADOS_BRUTOS / "inpe_deter" / nome / f"desde_{desde}", manifesto)
        resultado.entrada["manifestos"][nome] = str((pastas[nome][0] / "manifesto.json").relative_to(config.RAIZ))
        esperados[nome] = manifesto["total_anunciado"]
    resultado.transformar("Requisição ao WFS em partições mensais (uma requisição completa por mês, sem paginação), "
                          "com cada resposta gravada compactada em data/raw/inpe_deter/")

    def fluxo():
        for nome, (pasta, manifesto) in pastas.items():
            for particao in manifesto["particoes"]:
                yield nome, particao["inicio"][:7], json.loads(gzip.decompress((pasta / particao["arquivo"]).read_bytes()))

    tabela = consolidar(fluxo(), esperados, resultado)
    for nome, info in config.DETER_ARQUIVOS.items():
        meta = download.baixar(info["url"], config.DADOS_BRUTOS / "inpe_deter" / nome / info["arquivo"], atualizar)
        resultado.entrada.setdefault("arquivos", {})[nome] = {k: meta.get(k) for k in ("url", "baixado_em_utc",
                                                                                         "sha256", "tamanho_bytes")}
        tabela = pd.concat([tabela, tabela_arquivo(config.RAIZ / meta["arquivo"], nome, resultado)], ignore_index=True)
    saida, descartados = transformar_tabela(tabela, ref_municipios, desde, hoje, resultado)
    lago.gravar("ref.alerta_deter", saida, resultado)
    lago.gravar_descartes(descartados, resultado, ["id_alerta"])
    resultado.saida.update({
        "arquivo": _relativo(lago.pasta("ref.alerta_deter")),
        "registros_produzidos": len(saida),
        "registros_com_alerta": int((saida["alertas"] != "").sum()),
        "por_camada": saida["camada"].value_counts().to_dict(),
        "colunas": list(saida.columns),
        "tabela_descartados": "meta.descarte",
        "registros_descartados": len(descartados),
    })
    resultado.status = "ok"
    return resultado


def periodos_prodes(desde: str, ate: str) -> list[tuple[str, str]]:
    """Intervalos [início, fim) cortados em 01/08, o início do ano PRODES, de `desde` até `ate` (exclusivo)."""
    inicio, limite = pd.Timestamp(desde), pd.Timestamp(ate)
    intervalos = []
    while inicio < limite:
        corte = pd.Timestamp(year=inicio.year + (inicio.month >= 8), month=8, day=1)
        fim = min(corte, limite)
        intervalos.append((inicio.strftime("%Y-%m-%d"), fim.strftime("%Y-%m-%d")))
        inicio = fim
    return intervalos


def consultar_recorte(nome: str, uf: str, desde: str, ate: str, ref_municipios: pd.DataFrame, hoje: pd.Timestamp,
                      atualizar: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, ResultadoFonte]:
    """Consulta sob demanda: alertas de desmatamento de uma camada e UF, um ano PRODES por requisição.

    Serve para comparar com o PRODES, que é organizado por ano PRODES (01/08 a 31/07). Cada resposta fica em
    data/raw/inpe_deter/sob_demanda/ com .meta.json, e o tratamento e as validações são os mesmos do lote.
    """
    camada = config.CAMADAS_DETER[nome]
    resultado = ResultadoFonte("inpe_deter", "API (WFS/GeoJSON), sob demanda")
    pasta = config.DADOS_BRUTOS / "inpe_deter" / "sob_demanda" / f"{nome}_{uf.lower()}"
    respostas, metas = [], []
    for inicio, fim in periodos_prodes(desde, ate):
        cql = f"uf='{uf}' AND view_date>='{inicio}' AND view_date<'{fim}' AND {filtro_classes()}"
        resposta, meta = wfs.consultar_geojson(_url(camada), camada["tipo"], cql, pasta / f"{inicio}_{fim}.json.gz",
                                               atualizar=atualizar, limite=config.DETER_LIMITE_POR_REQUISICAO)
        respostas.append(resposta)
        metas.append({"periodo": f"{inicio} a {fim}", "anunciado": resposta.get("numberMatched"),
                      "recebido": len(resposta.get("features") or []), "sha256": meta["sha256"],
                      "consultado_em_utc": meta["consultado_em_utc"]})
    resultado.entrada = {"servico": _url(camada), "camada": camada["tipo"], "uf": uf, "desde": desde, "ate": ate,
                         "requisicoes": metas}
    resultado.transformar("Requisição ao WFS por ano PRODES (01/08 a 31/07), com cada resposta gravada compactada "
                          "em data/raw/inpe_deter/sob_demanda/")
    esperados = {nome: sum(r.get("numberMatched") or 0 for r in respostas)}
    saida, descartados = transformar({nome: respostas}, esperados, ref_municipios, desde, hoje, resultado)
    resultado.saida = {"registros_produzidos": len(saida), "registros_descartados": len(descartados)}
    resultado.status = "ok"
    return saida, descartados, resultado
