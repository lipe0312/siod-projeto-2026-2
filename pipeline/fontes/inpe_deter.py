"""Fonte: alertas de desmatamento DETER do INPE. O lote vem do shapefile de cada bioma na área de download do
TerraBrasilis (config.DETER_ARQUIVOS: Amazônia, Cerrado e Pantanal; o WFS não tem o Pantanal). O WFS em partições
mensais (config.CAMADAS_DETER) é a queda quando o arquivo da Amazônia ou do Cerrado falha, e continua na consulta sob
demanda. O arquivo não traz o gid do WFS: `reconciliar` mantém o id_alerta do alerta que já está no lago."""

import gzip
import hashlib
import json
import logging
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import shapefile
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
            "camada": nome, "origem": "wfs", "gid": p.get("gid"), "classe": p.get("classname"),
            "view_date": p.get("view_date"),
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


def _versao_remota(url: str) -> str | None:
    """Versão do arquivo no servidor: o nome em `Content-Disposition`, que leva a data (deter-amz-public-2026nov04.zip).
    O servidor não manda Last-Modified, Content-Length nem ETag. Devolve None se a consulta falhar."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=(30, 60), headers={"User-Agent": config.USER_AGENT})
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("[inpe_deter] não consegui consultar a versão de %s (%s)", url, type(e).__name__)
        return None
    achado = re.search(r'filename="?([^";]+)"?', r.headers.get("Content-Disposition") or "")
    return achado.group(1) if achado else None


def baixar_arquivo(nome: str, atualizar: bool = False) -> dict:
    """Baixa o shapefile do bioma só quando muda: a versão no cabeçalho (HEAD) é a gravada no `.meta.json` ao lado do
    zip e, se vier diferente, baixa e compara o SHA-256 com o anterior (`mudou`). Sem versão no cabeçalho (HEAD falhou),
    baixa. Falha do download propaga: quem chama decide a queda (Amazônia e Cerrado voltam ao WFS)."""
    info = config.DETER_ARQUIVOS[nome]
    destino = config.DADOS_BRUTOS / "inpe_deter" / nome / info["arquivo"]
    meta_arq = destino.with_suffix(".meta.json")
    anterior = json.loads(meta_arq.read_text()) if meta_arq.exists() else {}
    versao = _versao_remota(info["url"])
    inicio = time.perf_counter()
    if not atualizar and destino.exists() and versao and anterior.get("versao") == versao:
        log.info("[inpe_deter] %s: arquivo já está na versão do servidor (%s), sem novo download", nome, versao)
        meta = download.baixar(info["url"], destino, False)
        meta.update(baixado_agora=False, mudou=False)
    else:
        meta = download.baixar(info["url"], destino, True)
        meta.update(baixado_agora=True, mudou=anterior.get("sha256") != meta["sha256"])
        log.info("[inpe_deter] %s: baixado %.1f MB em %.1f s (%s)", nome, meta["tamanho_bytes"] / 1e6,
                 time.perf_counter() - inicio, "conteúdo novo" if meta["mudou"] else "mesmo conteúdo da versão anterior")
    meta["versao"] = versao
    meta["segundos"] = round(time.perf_counter() - inicio, 1)
    meta_arq.write_text(json.dumps({k: v for k, v in meta.items() if k not in ("arquivo", "baixado_agora", "mudou",
                                                                                "segundos")}, indent=2, ensure_ascii=False))
    return meta


def _ler_arquivo(caminho, info: dict, nome: str, desde: str | None, resultado: ResultadoFonte):
    """Registros (só as colunas usadas), geometrias 2D e .prj do shapefile do zip. Lê o DBF inteiro, mas só monta a
    geometria do que fica: a classe ignorada (`so_desmatamento`) e a data antes de `desde` são contadas e saem aqui."""
    z = zipfile.ZipFile(caminho)
    nomes = {n.rsplit(".", 1)[-1].lower(): n for n in z.namelist() if n.rsplit(".", 1)[0].endswith(info["base_shapefile"])}
    faltam = [e for e in ("shp", "shx", "dbf") if e not in nomes]
    if faltam:
        raise ValueError(f"{Path(caminho).name}: falta o arquivo .{', .'.join(faltam)} no zip")
    campos = info["campos"]
    colunas = list(dict.fromkeys([*campos.values(), "VIEW_DATE", "SENSOR", "SATELLITE"]))
    with tempfile.TemporaryDirectory() as tmp:
        for ext in ("shp", "shx", "dbf"):
            with z.open(nomes[ext]) as origem, open(Path(tmp) / f"a.{ext}", "wb") as destino:
                shutil.copyfileobj(origem, destino)
        with shapefile.Reader(str(Path(tmp) / "a"), encoding="utf-8", encodingErrors="replace") as leitor:
            resultado.validar(f"DETER_{nome.upper()}_ARQUIVO_INCOMPLETO", "Registros do DBF diferentes das formas do SHX",
                              "erro", "interrompe a fonte", int(leitor.numRecords != leitor.numShapes), 1)
            df = pd.DataFrame([r.as_dict() for r in leitor.iterRecords(fields=colunas)])
            classe = df[campos["classe"]].astype("string").str.strip()
            traduzida = classe.str.lower().map(info["classes"])
            resultado.validar(f"DETER_{nome.upper()}_CLASSE_TRADUZIDA", "Classe de supressão do arquivo traduzida para a "
                              f"do WFS ({'; '.join(f'{k} = {v}' for k, v in info['classes'].items())})", "correcao",
                              "vale a classe do WFS", traduzida.notna(), len(df))
            datas = pd.to_datetime(df["VIEW_DATE"], errors="coerce")
            fora_classe = traduzida.isna() if info.get("so_desmatamento") else pd.Series(False, index=df.index)
            antes = (datas < pd.Timestamp(desde)) & ~fora_classe if desde else pd.Series(False, index=df.index)
            ficam = np.flatnonzero(~(fora_classe | antes).to_numpy())
            df, classe, traduzida = df.iloc[ficam].reset_index(drop=True), classe.iloc[ficam].reset_index(drop=True), \
                traduzida.iloc[ficam].reset_index(drop=True)
            formas = [leitor.shape(int(i)) for i in ficam]
            geoms = np.array([shapely.force_2d(shapely.geometry.shape(f.__geo_interface__)) if f.shapeType else None
                              for f in formas], dtype=object)
        prj = z.read(nomes["prj"]).decode("utf-8", "replace") if "prj" in nomes else ""
    ilegivel = df[campos["municipio"]].astype("string").str.contains("�", na=False) if "municipio" in campos else 0
    if "municipio" in campos:
        resultado.validar(f"DETER_{nome.upper()}_TEXTO_ILEGIVEL", "Nome de município com caractere ilegível (codificação "
                          "do DBF)", "alerta", "mantido", ilegivel, len(df))
    contagem = {"no_arquivo": int(leitor.numRecords), "classes_ignoradas": int(fora_classe.sum()),
                "antes_de_desde": int(antes.sum()), "recebidos": len(df)}
    return df, classe, traduzida, geoms, prj, contagem


def tabela_arquivo(caminho, nome: str, resultado: ResultadoFonte, desde: str | None = None) -> pd.DataFrame:
    """Shapefile do DETER (área de download) na forma de `resposta_para_tabela`. A classe é traduzida para a do WFS
    (config.DETER_ARQUIVOS). Amazônia e Cerrado trazem UF, município e código IBGE; o Pantanal não (a UF vem do contorno
    do IBGE e o município fica sem código). O arquivo não traz `publish_month`. Com `desde`, não lê o que é anterior."""
    from pipeline import territorio

    info = config.DETER_ARQUIVOS[nome]
    campos = info["campos"]
    df, classe, traduzida, geoms, prj, contagem = _ler_arquivo(caminho, info, nome, desde, resultado)
    vetor.validar_crs_sirgas(f"DETER_{nome.upper()}", prj, resultado)
    presentes = pd.Series([g is not None and not g.is_empty for g in geoms], dtype=bool)
    if "uf" in campos:
        ufs = df[campos["uf"]].astype("string").str.strip().str.upper()
    else:
        ufs = pd.Series([None] * len(df), dtype=object)
        if presentes.any():
            ufs[presentes.to_numpy()] = territorio.uf_por_contorno(geoms[presentes.to_numpy()])
    lim = config.LIMITES_BRASIL
    b = shapely.bounds(geoms.astype(object))
    nulo = pd.Series([None] * len(df), dtype=object)
    tabela = pd.DataFrame({
        "camada": nome, "origem": "arquivo", "gid": info.get("prefixo_gid", "") + df[campos["id"]].astype("string"),
        "classe": traduzida.fillna(classe),
        "view_date": [v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else None for v in df["VIEW_DATE"]],
        "publish_month": None, "uf": ufs,
        "municipio_fonte": df[campos["municipio"]] if "municipio" in campos else nulo,
        "mun_geocod": df[campos["cod_municipio"]] if "cod_municipio" in campos else nulo,
        "area_fonte": df[campos["area"]], "satelite": df["SATELLITE"], "sensor": df["SENSOR"],
        **{f"tem_{k}": k != "municipality" or "municipio" in campos for k in PROPRIEDADES_OBRIGATORIAS},
        "geom_ausente": ~presentes,
        "geom_fora_brasil": presentes & ~((b[:, 1] >= lim["lat_min"]) & (b[:, 3] <= lim["lat_max"])
                                          & (b[:, 0] >= lim["lon_min"]) & (b[:, 2] <= lim["lon_max"])),
        "geom_invalida": presentes & ~shapely.is_valid(geoms.astype(object)),
        "geometria_wkt": [shapely.to_wkt(g, rounding_precision=6, trim=True) if ok else None
                          for g, ok in zip(geoms, presentes)]})
    resultado.entrada.setdefault("camadas", {})[nome] = {"arquivo": _relativo(Path(caminho)), **contagem}
    resultado.transformar(f"DETER {nome}: shapefile da área de download; UF "
                          + ("e município do próprio arquivo" if "uf" in campos else "pelo contorno do IBGE")
                          + (f"; só as classes de desmatamento e a partir de {desde}" if info.get("so_desmatamento")
                             else ""))
    return tabela


def _area_chave(area: pd.Series) -> pd.Series:
    """Área em km² arredondada a config.DETER_AREA_CASAS casas (1 m²); ausente ou não positiva vira -1."""
    a = pd.to_numeric(area, errors="coerce").where(lambda x: x > 0)
    return a.round(config.DETER_AREA_CASAS).fillna(-1).map(lambda v: f"{v:.{config.DETER_AREA_CASAS}f}")


def _centroides(wkt: pd.Series) -> np.ndarray:
    pontos = shapely.centroid(shapely.from_wkt(wkt.fillna("GEOMETRYCOLLECTION EMPTY").to_numpy(), on_invalid="ignore"))
    return np.column_stack([shapely.get_x(pontos), shapely.get_y(pontos)])


def _parear(alvo: pd.DataFrame, lago_df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Pares (linha do alvo, linha do lago) com a mesma data da imagem, UF e área (até 1e-6 km²). Chave de um para um
    vira par direto. Chave com mais de uma linha em um dos lados (ambígua) é resolvida um para um, em ordem: mesmo
    município (código IBGE ou nome), menor distância entre os centroides, menor gid do alvo, menor id_alerta do lago.
    Devolve os pares (colunas i, j, municipio_diferente), as linhas do alvo em chave ambígua e quantas resolveram."""
    r = pd.DataFrame({
        "i": alvo.index, "gid_r": alvo["gid"].astype(str).to_numpy(),
        "chave": (alvo["view_date"].astype(str) + "|" + alvo["uf"].astype("string").str.strip().str.upper().fillna("")
                  + "|" + _area_chave(alvo["area_fonte"])).to_numpy(),
        "cod_r": alvo["mun_geocod"].astype("string").to_numpy(),
        "nome_r": alvo["municipio_fonte"].map(normalizar_nome).to_numpy()})
    lg = pd.DataFrame({
        "j": lago_df.index, "id_l": lago_df["id_alerta"].to_numpy(),
        "chave": (lago_df["data_imagem"].dt.strftime("%Y-%m-%d") + "|" + lago_df["uf"].astype("string").fillna("")
                  + "|" + _area_chave(lago_df["area_km2"])).to_numpy(),
        "cod_l": lago_df["cod_municipio"].astype("string").to_numpy(),
        "nome_l": lago_df["municipio"].map(normalizar_nome).to_numpy()})
    pares = r.merge(lg, on="chave")
    n_r, n_l = r.groupby("chave").size(), lg.groupby("chave").size()
    pares["ambigua"] = (pares["chave"].map(n_r) > 1) | (pares["chave"].map(n_l) > 1)
    mesmo_cod = pares["cod_r"].notna() & (pares["cod_r"] == pares["cod_l"])
    mesmo_nome = (pares["nome_r"] != "") & (pares["nome_r"] == pares["nome_l"])
    pares["municipio_diferente"] = ~(mesmo_cod | mesmo_nome)
    amb_linhas = int(r["chave"].isin(pares.loc[pares["ambigua"], "chave"]).sum())
    escolhidos = pares[~pares["ambigua"]]
    resolvidas = 0
    amb = pares[pares["ambigua"]].copy()
    if len(amb):
        cr, cl = _centroides(alvo["geometria_wkt"]), _centroides(lago_df["geometria_wkt"])
        pos_r, pos_l = pd.Series(range(len(alvo)), index=alvo.index), pd.Series(range(len(lago_df)), index=lago_df.index)
        d = cr[pos_r[amb["i"]].to_numpy()] - cl[pos_l[amb["j"]].to_numpy()]
        amb["distancia"] = np.nan_to_num(np.hypot(d[:, 0], d[:, 1]), nan=np.inf)
        usados_i, usados_j, linhas = set(), set(), []
        for t in amb.sort_values(["municipio_diferente", "distancia", "gid_r", "id_l"], kind="stable").itertuples():
            if t.i not in usados_i and t.j not in usados_j:
                usados_i.add(t.i), usados_j.add(t.j), linhas.append(t.Index)
        resolvidas = len(linhas)
        escolhidos = pd.concat([escolhidos, amb.loc[linhas]])
    return escolhidos[["i", "j", "municipio_diferente"]], amb_linhas, resolvidas


def reconciliar(df: pd.DataFrame, vigente: pd.DataFrame | None, resultado: ResultadoFonte) -> pd.DataFrame:
    """O arquivo do DETER não traz o gid do WFS (o FID é outra numeração). Para os biomas com `reconciliar` em
    config.DETER_ARQUIVOS, o alerta que casa com um vigente de ref.alerta_deter (mesma data, UF e área até 1e-6 km²;
    ambiguidade em `_parear`) mantém o id_alerta, o gid e o mês de publicação do lago. O sem par segue com o id da
    fórmula (ADR 0004) sobre gid = prefixo + FID do arquivo, estável porque, na execução seguinte, ele casa com o lago.
    As linhas do WFS (queda) só casam com alerta do lago que nasceu do arquivo (gid com o prefixo), para não duplicar.
    Registra casados, novos, ambíguos, sem par no lago e a contagem arquivo x lago no período."""
    df = df.copy()
    origem = df["origem"] if "origem" in df else pd.Series("wfs", index=df.index)
    for nome, info in config.DETER_ARQUIVOS.items():
        if not info.get("reconciliar"):
            continue
        for de in ("arquivo", "wfs"):
            alvo = df[(df["camada"] == nome) & (origem == de)]
            if alvo.empty:
                continue
            rot = f"DETER_{nome.upper()}" + ("" if de == "arquivo" else "_WFS")
            candidatos = pd.DataFrame() if vigente is None else vigente[vigente["camada"] == nome]
            if de == "wfs" and len(candidatos):
                candidatos = candidatos[candidatos["gid"].astype(str).str.startswith(info["prefixo_gid"])]
            if len(candidatos):
                pares, amb_linhas, resolvidas = _parear(alvo, candidatos)
                lago_ix = candidatos.loc[pares["j"]]
                df.loc[pares["i"].to_numpy(), "id_alerta"] = lago_ix["id_alerta"].to_numpy()
                df.loc[pares["i"].to_numpy(), "gid"] = lago_ix["gid"].to_numpy()
                mes = lago_ix["mes_publicacao"].dt.strftime("%Y-%m-%d").to_numpy()
                df.loc[pares["i"].to_numpy(), "publish_month"] = mes
            else:
                pares, amb_linhas, resolvidas = pd.DataFrame(columns=["i", "j", "municipio_diferente"]), 0, 0
            n = len(alvo)
            casados = len(pares)
            resultado.validar(f"{rot}_RECONCILIADO", "Alerta com par em ref.alerta_deter (mesma data, UF e área até 1e-6 "
                              "km²)", "correcao", "mantém id_alerta, gid e mês de publicação do lago", casados, n)
            resultado.validar(f"{rot}_AMBIGUO", "Alerta cuja data, UF e área batem com mais de um candidato (em um ou nos "
                              "dois lados)", "alerta", "um para um: mesmo município, depois menor distância entre "
                              "centroides, depois menor gid e id_alerta", amb_linhas, n)
            resultado.validar(f"{rot}_AMBIGUO_SEM_PAR", "Linha de chave ambígua que ficou sem par depois do desempate",
                              "alerta", "segue como alerta novo", amb_linhas - resolvidas, amb_linhas)
            resultado.validar(f"{rot}_MUNICIPIO_DIFERENTE_NO_PAR", "Par com município (código ou nome) diferente do do "
                              "lago", "alerta", "par mantido pela data, UF e área", int(pares["municipio_diferente"].sum()),
                              casados)
            resumo = {"linhas": n, "reconciliados": casados, "ambiguos": amb_linhas, "ambiguos_resolvidos": resolvidas}
            if de == "arquivo":
                novos = n - casados
                ate = pd.to_datetime(alvo["view_date"]).max()
                no_periodo = candidatos[candidatos["data_imagem"] <= ate] if len(candidatos) else candidatos
                sem_par = len(no_periodo) - casados
                resultado.validar(f"{rot}_NOVO", f"Alerta do arquivo sem par no lago: id próprio (gid = "
                                  f"{info['prefixo_gid']}<FID>)", "correcao", "entra como alerta novo", novos, n)
                resultado.validar(f"{rot}_SO_NO_LAGO", "Alerta do lago no período do arquivo sem par nele (mudou ou saiu "
                                  "da fonte)", "alerta", "continua no lago (acréscimo)", max(sem_par, 0), len(no_periodo))
                resultado.validar(f"{rot}_ARQUIVO_X_LAGO", "Contagem do arquivo diferente da do lago no mesmo período "
                                  f"(até {ate:%Y-%m-%d})", "alerta", "registra a diferença", abs(n - len(no_periodo)),
                                  len(no_periodo))
                resumo.update(novos=novos, so_no_lago=max(sem_par, 0), no_lago_no_periodo=len(no_periodo),
                              periodo_ate=f"{ate:%Y-%m-%d}")
            resultado.entrada.setdefault("reconciliacao", {})[f"{nome}_{de}"] = resumo
            resultado.transformar(f"DETER {nome} ({de}): {casados} de {n} alertas casados com o lago por data, UF e área "
                                  f"(1e-6 km²); {amb_linhas} em chave ambígua")
    resultado.validar("DETER_RECONCILIACAO_ID_DUPLICADO", "id_alerta repetido depois da reconciliação", "erro",
                      "interrompe a fonte", int(df["id_alerta"].duplicated().sum()), len(df))
    return df


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
                       resultado: ResultadoFonte, vigente: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`vigente`: ref.alerta_deter vigente, para a reconciliação do arquivo com o lago (`reconciliar`)."""
    n = len(df)
    # As propriedades obrigatórias são as do WFS; o arquivo é validado em tabela_arquivo.
    wfs_df = df[df["origem"] != "arquivo"] if n else df
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
    if any(df["camada"].eq(n).any() and i.get("reconciliar") for n, i in config.DETER_ARQUIVOS.items()):
        df = reconciliar(df, vigente, resultado)

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


def contagem_wfs(nome: str, desde: str, ate: str) -> int:
    """Alertas de desmatamento do WFS entre `desde` e `ate` (inclusive): uma requisição de contagem (resultType=hits)."""
    return wfs.contar(_url(config.CAMADAS_DETER[nome]), config.CAMADAS_DETER[nome]["tipo"],
                      f"view_date>='{desde}' AND view_date<='{ate}' AND {filtro_classes()}", tentativas=2)


def _comparar_com_wfs(nome: str, tabela: pd.DataFrame, desde: str, resultado: ResultadoFonte) -> None:
    """Contagem do arquivo x contagem do WFS no mesmo período. WFS fora do ar não derruba a fonte: a comparação fica
    registrada como inconclusiva, com o motivo."""
    ate = pd.to_datetime(tabela["view_date"]).max()
    n_arquivo = int(tabela["classe"].isin(config.CLASSES_DESMATAMENTO).sum())
    resumo = resultado.entrada["camadas"][nome]
    resumo.update(periodo=[desde, f"{ate:%Y-%m-%d}"], desmatamento_no_arquivo=n_arquivo)
    try:
        n_wfs = contagem_wfs(nome, desde, f"{ate:%Y-%m-%d}")
    except Exception as e:  # rede, serviço fora do ar, resposta sem contagem
        resumo["wfs"] = f"inconclusiva: {type(e).__name__}: {e}"
        resultado.validar(f"DETER_{nome.upper()}_ARQUIVO_X_WFS_INCONCLUSIVA", "Contagem do WFS indisponível; a comparação "
                          f"com o arquivo não foi feita ({type(e).__name__})", "alerta", "segue sem a comparação", 1, 1)
        return
    resumo.update(desmatamento_no_wfs=n_wfs, diferenca_arquivo_menos_wfs=n_arquivo - n_wfs)
    resultado.validar(f"DETER_{nome.upper()}_ARQUIVO_X_WFS", f"Alertas de desmatamento do arquivo ({n_arquivo}) diferentes "
                      f"dos do WFS ({n_wfs}) de {desde} a {ate:%Y-%m-%d}", "alerta", "registra a diferença; o WFS é "
                      "atualizado em outro ritmo que o arquivo", abs(n_arquivo - n_wfs), max(n_wfs, 1))


def _do_arquivo(nome: str, desde: str, atualizar: bool, resultado: ResultadoFonte) -> pd.DataFrame:
    meta = baixar_arquivo(nome, atualizar)
    resultado.entrada.setdefault("arquivos", {})[nome] = {k: meta.get(k) for k in (
        "url", "versao", "baixado_agora", "mudou", "baixado_em_utc", "sha256", "tamanho_bytes", "segundos")}
    tabela = tabela_arquivo(config.RAIZ / meta["arquivo"], nome, resultado, desde)
    if nome in config.CAMADAS_DETER and not tabela.empty:
        _comparar_com_wfs(nome, tabela, desde, resultado)
    return tabela


def executar(ref_municipios: pd.DataFrame, hoje: pd.Timestamp, desde: str = config.DETER_DESDE_PADRAO,
             atualizar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("inpe_deter", "arquivo (shapefile) e API (WFS) na queda")
    resultado.entrada = {"servico_wfs": config.URL_WFS_INPE.format(workspace="{camada}"),
                         "filtro": f"view_date>='{desde}' AND {filtro_classes()}", "manifestos": {}, "arquivos": {},
                         "quedas_para_wfs": {}}
    tabelas, no_arquivo = [], set()
    for nome in config.DETER_ARQUIVOS:
        antes = (len(resultado.validacoes), len(resultado.transformacoes), dict(resultado.entrada.get("camadas", {})))
        try:
            tabelas.append(_do_arquivo(nome, desde, atualizar, resultado))
            no_arquivo.add(nome)
        except Exception as e:
            if nome not in config.CAMADAS_DETER:  # o Pantanal não tem WFS: não há para onde cair
                raise
            motivo = f"{type(e).__name__}: {e}"
            del resultado.validacoes[antes[0]:], resultado.transformacoes[antes[1]:]
            resultado.entrada["camadas"] = antes[2]
            resultado.entrada["arquivos"].pop(nome, None)
            resultado.entrada["quedas_para_wfs"][nome] = motivo
            log.warning("[inpe_deter] %s: arquivo falhou (%s); usando o WFS", nome, motivo)
            resultado.validar(f"DETER_{nome.upper()}_ARQUIVO_FALHOU", f"Arquivo do bioma indisponível ou ilegível: {motivo}",
                              "alerta", "o bioma vem do WFS nesta execução (nunca sem ocorrência por falta de dado)", 1, 1)
    por_wfs = [n for n in config.CAMADAS_DETER if n not in no_arquivo]
    if por_wfs:
        esperados, pastas = {}, {}
        for nome in por_wfs:
            manifesto = baixar_camada(nome, desde, hoje, atualizar)
            pastas[nome] = (config.DADOS_BRUTOS / "inpe_deter" / nome / f"desde_{desde}", manifesto)
            resultado.entrada["manifestos"][nome] = _relativo(pastas[nome][0] / "manifesto.json")
            esperados[nome] = manifesto["total_anunciado"]
        resultado.transformar("Requisição ao WFS em partições mensais (uma requisição completa por mês, sem paginação), "
                              "com cada resposta gravada compactada em data/raw/inpe_deter/")

        def fluxo():
            for nome, (pasta, manifesto) in pastas.items():
                for particao in manifesto["particoes"]:
                    yield nome, particao["inicio"][:7], json.loads(gzip.decompress((pasta / particao["arquivo"]).read_bytes()))

        tabelas.insert(0, consolidar(fluxo(), esperados, resultado))
    tabelas = [t for t in tabelas if not t.empty]
    tabela = pd.concat(tabelas, ignore_index=True) if tabelas else pd.DataFrame()
    resultado.entrada["registros_recebidos"] = len(tabela)
    vigente = lago.ler_ou_none("ref.alerta_deter")
    saida, descartados = transformar_tabela(tabela, ref_municipios, desde, hoje, resultado, vigente)
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
