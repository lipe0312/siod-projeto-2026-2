"""Pré-diagnóstico de pendências de um imóvel rural: python -m pipeline.prediagnostico --car CÓDIGO [--documento CPF]

Do ponto de vista do produtor (o cruzamento.py parte do embargo ou do alerta). Para um CAR:
- CAR: status e condição no SICAR (consulta sob demanda);
- embargo IBAMA: polígono ou coordenada do embargo dentro do CAR, e embargo em nome do documento informado;
- desmatamento após 31/12/2020: alertas DETER dentro do CAR, confirmados ou não pelo PRODES, e polígonos PRODES
  (do parquet do lote quando a UF está no recorte; senão, consulta sob demanda);
- Lista Suja: documento informado (pseudonimizado com a chave do pipeline, nunca gravado em claro);
- demais critérios do AB+S: "não verificado", nunca "conforme".

Situação de cada critério: pendência (impede crédito ou venda sob a EUDR), indício (precisa de conferência),
sem ocorrência (nada encontrado nas fontes verificadas), não verificado (sem fonte aberta) ou inconclusivo (falta
entrada, como o CAR não localizado). O resultado é um pré-diagnóstico com a evidência de cada pendência, não um
atestado de conformidade.
"""

import argparse
import functools
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.strtree import STRtree

from pipeline import config, cruzamento, relatorio
from pipeline.documentos import carregar_chave, pseudonimizar, somente_digitos
from pipeline.fontes import ab_s, inpe_prodes, sicar

log = logging.getLogger("pipeline")

SITUACOES = ("pendência", "indício", "sem ocorrência", "não verificado", "inconclusivo")
STATUS_CAR = {"AT": "Ativo", "PE": "Pendente", "SU": "Suspenso", "CA": "Cancelado"}
CLASSES_DENTRO = ("principal", "parcial")

ENCAMINHAMENTO = {
    "car_irregular": "Regularizar o CAR no órgão ambiental estadual. O crédito rural é vedado com CAR cancelado ou "
                     "suspenso (MCR, Seção 2-9).",
    "car_pendente": "Acessar a central do proprietário no SICAR e responder às notificações pendentes.",
    "embargo": "Consultar o termo de embargo no IBAMA (número e série do TAD) e o processo. O crédito rural é vedado "
               "com embargo ativo (MCR, Seção 2-9); o desembargo depende da regularização da área.",
    "desmatamento": "Verificar se a supressão teve autorização (ASV). Mesmo autorizada, área desmatada após "
                    "31/12/2020 não atende à EUDR para a produção que sai dela.",
    "desmatamento_indicio": "Conferir em imagem de satélite e com o produtor; o alerta ainda não foi confirmado pelo "
                            "PRODES.",
    "lista_suja": "O crédito rural é vedado enquanto o empregador constar no Cadastro (MCR, Seção 2-9). Conferir a "
                  "situação no MTE.",
    "nao_verificado": "Conferir no relatório do AgroBrasil+Sustentável do produtor.",
    "sem_documento": "Informar o CPF ou CNPJ de cada proprietário para verificar.",
}


def _data(valor) -> str | None:
    return None if pd.isna(valor) else pd.Timestamp(valor).strftime("%Y-%m-%d")


def _criterio(chave, nome, n_ab_s, situacao, evidencia, encaminhamento, fonte) -> dict:
    return {"chave": chave, "criterio": nome, "criterio_ab_s": n_ab_s, "situacao": situacao, "evidencia": evidencia,
            "encaminhamento": encaminhamento, "fonte": fonte}


def _dentro_do_car(geoms, car_geom, car: pd.DataFrame) -> pd.DataFrame:
    """Frações e classe (principal, parcial, tangente) de cada polígono que toca o CAR; índice = posição em `geoms`."""
    linhas = {}
    for i in np.flatnonzero(shapely.intersects(geoms, car_geom)):
        par = cruzamento.pares_objeto_car(geoms[i], car)
        if len(par):
            linhas[i] = par.iloc[0][["inter_ha", "fracao_objeto", "largura_m", "classe"]]
    return pd.DataFrame.from_dict(linhas, orient="index", columns=["inter_ha", "fracao_objeto", "largura_m", "classe"])


def embargos_do_imovel(car: pd.DataFrame, car_geom, embargos: pd.DataFrame, documento_hash: str | None) -> pd.DataFrame:
    """Embargos com polígono que toca o CAR, com coordenada dentro dele, ou em nome do documento."""
    colunas = ["id_embargo", "num_tad", "ser_tad", "data_embargo", "area_ha", "descricao_infracao", "municipio", "uf",
               "geometria_wkt"]
    candidatos = embargos[embargos["uf"] == car["uf"].iloc[0]]
    com_geom = candidatos[candidatos["geometria_wkt"].notna()].reset_index(drop=True)
    geoms = shapely.make_valid(shapely.from_wkt(com_geom["geometria_wkt"].to_numpy()))
    pares = _dentro_do_car(geoms, car_geom, car)
    por_poligono = com_geom.loc[pares.index, colunas].join(pares).assign(como="polígono")

    so_ponto = candidatos[candidatos["geometria_wkt"].isna() & candidatos["latitude"].notna()]
    pontos = shapely.points(so_ponto["longitude"].to_numpy(dtype=float), so_ponto["latitude"].to_numpy(dtype=float))
    por_ponto = so_ponto[shapely.contains(car_geom, pontos)][colunas].assign(classe="coordenada", como="coordenada")

    partes = [por_poligono, por_ponto]
    if documento_hash:
        doc = embargos[embargos["documento_hash"] == documento_hash][colunas].assign(classe="documento",
                                                                                     como="documento")
        partes.append(doc)
    tudo = pd.concat([p for p in partes if len(p)], ignore_index=True) if any(len(p) for p in partes) else (
        pd.DataFrame(columns=colunas + ["inter_ha", "fracao_objeto", "largura_m", "classe", "como"]))
    # O mesmo embargo pode aparecer pelo polígono e pelo documento: fica uma linha, com as duas formas.
    como = tudo.groupby("id_embargo")["como"].agg(lambda s: " e ".join(dict.fromkeys(s)))
    tudo = tudo.drop_duplicates("id_embargo").set_index("id_embargo")
    tudo["como"] = como
    return tudo.reset_index()


def alertas_do_imovel(car: pd.DataFrame, car_geom, alertas: pd.DataFrame, prodes: pd.DataFrame,
                      ultimo_ano: int) -> pd.DataFrame:
    """Alertas DETER que tocam o CAR, com a situação diante do PRODES (só os principais e parciais são avaliados)."""
    candidatos = alertas[(alertas["uf"] == car["uf"].iloc[0]) & alertas["geometria_wkt"].notna()].reset_index(drop=True)
    geoms = shapely.make_valid(shapely.from_wkt(candidatos["geometria_wkt"].to_numpy()))
    pares = _dentro_do_car(geoms, car_geom, car)
    saida = candidatos.loc[pares.index, ["id_alerta", "classe", "data_imagem", "area_km2", "satelite",
                                         "geometria_wkt"]].rename(columns={"classe": "classe_deter"}).join(pares)
    saida = saida.reset_index(drop=True)
    if saida.empty:
        return saida.assign(situacao_prodes=pd.Series(dtype="string"), anos_prodes=pd.Series(dtype="string"))
    confirmados = inpe_prodes.confirmar_alertas(saida[["data_imagem", "geometria_wkt"]], prodes,
                                                ultimo_ano=ultimo_ano)
    saida["situacao_prodes"] = confirmados["situacao"].where(saida["classe"].isin(CLASSES_DENTRO), "não avaliado")
    saida["anos_prodes"] = confirmados["anos_prodes"]
    return saida


def prodes_do_imovel(car: pd.DataFrame, car_geom, prodes: pd.DataFrame) -> pd.DataFrame:
    """Polígonos PRODES de anos após a data de corte que tocam o CAR."""
    depois = prodes[prodes["ano_prodes"] > int(config.DATA_CORTE_EUDR[:4])].reset_index(drop=True)
    geoms = shapely.from_wkt(depois["geometria_wkt"].to_numpy())
    pares = _dentro_do_car(geoms, car_geom, car)
    return depois.loc[pares.index, ["uuid", "bioma", "ano_prodes", "data_imagem", "area_km2",
                                    "geometria_wkt"]].join(pares).reset_index(drop=True)


def _criterio_car(imovel: dict) -> dict:
    status, condicao = imovel["status_imovel"], imovel["condicao"]
    texto = f"{STATUS_CAR.get(status, status)} · {condicao}"
    if (imovel["fracao_coberta_por_outros"] or 0) >= sicar.LIMIAR_SOBREPOSTO:
        texto += f" · {imovel['fracao_coberta_por_outros']:.0%} da área coberta por outros CARs"
    if status in ("CA", "SU"):
        return _criterio("car", "CAR", 3, "pendência", texto, ENCAMINHAMENTO["car_irregular"], "SICAR")
    if status == "PE" or "notifica" in condicao.lower():
        return _criterio("car", "CAR", 3, "indício", texto, ENCAMINHAMENTO["car_pendente"], "SICAR")
    return _criterio("car", "CAR", 3, "sem ocorrência", texto, "—", "SICAR")


def _tad(r) -> str:
    return f"{r.num_tad}-{r.ser_tad}" if pd.notna(r.ser_tad) else str(r.num_tad)


def _criterio_embargo(emb: pd.DataFrame) -> dict:
    dentro = emb[emb["classe"].isin(CLASSES_DENTRO + ("coordenada", "documento"))]
    na_divisa = len(emb) - len(dentro)
    nota = f"; {na_divisa} na divisa, não atribuído(s) ao imóvel" if na_divisa else ""
    if len(dentro):
        tads = ", ".join(f"TAD {_tad(r)} ({r.como})" for r in dentro.itertuples())
        return _criterio("embargo", "Embargo IBAMA", 7, "pendência", f"{len(dentro)} embargo(s): {tads}{nota}",
                         ENCAMINHAMENTO["embargo"], "IBAMA")
    return _criterio("embargo", "Embargo IBAMA", 7, "sem ocorrência", "Nenhum embargo dentro do imóvel" + nota,
                     "—", "IBAMA")


def _criterio_desmatamento(alt: pd.DataFrame, prd: pd.DataFrame) -> dict:
    a = alt[alt["classe"].isin(CLASSES_DENTRO)] if len(alt) else alt
    p = prd[prd["classe"].isin(CLASSES_DENTRO)] if len(prd) else prd
    situacoes = a["situacao_prodes"].value_counts() if len(a) else pd.Series(dtype=int)
    confirmados = int(situacoes.get("confirmado", 0))
    prodes_certo = p[p["ano_prodes"] > int(config.DATA_CORTE_EUDR[:4]) + 1] if len(p) else p
    partes = []
    if len(a):
        partes.append(f"{len(a)} alerta(s) DETER ({a['inter_ha'].sum():.1f} ha no imóvel): "
                      + ", ".join(f"{n} {s}" for s, n in situacoes.items()))
    if len(p):
        partes.append(f"{len(p)} polígono(s) PRODES após 2020 ({p['inter_ha'].sum():.1f} ha no imóvel)")
    texto = "; ".join(partes) or "Nenhum alerta DETER nem polígono PRODES após 2020 dentro do imóvel"
    if confirmados or len(prodes_certo):
        return _criterio("desmatamento", "Desmatamento após 31/12/2020 (EUDR)", None, "pendência", texto,
                         ENCAMINHAMENTO["desmatamento"], "INPE DETER e PRODES")
    if len(a) or len(p):
        # Alerta sem confirmação, ou PRODES 2021 (o ano PRODES 2021 começa em 01/08/2020, antes da data de corte).
        return _criterio("desmatamento", "Desmatamento após 31/12/2020 (EUDR)", None, "indício", texto,
                         ENCAMINHAMENTO["desmatamento_indicio"], "INPE DETER e PRODES")
    return _criterio("desmatamento", "Desmatamento após 31/12/2020 (EUDR)", None, "sem ocorrência", texto, "—",
                     "INPE DETER e PRODES")


def _criterio_lista_suja(lista_suja: pd.DataFrame, documento_hash: str | None) -> tuple[dict, pd.DataFrame]:
    if not documento_hash:
        return _criterio("lista_suja", "Lista Suja (trabalho escravo)", 4, "não verificado",
                         "Documento do proprietário não informado", ENCAMINHAMENTO["sem_documento"], "MTE"), \
            lista_suja.iloc[0:0]
    achados = lista_suja[lista_suja["documento_hash"] == documento_hash]
    if len(achados):
        return _criterio("lista_suja", "Lista Suja (trabalho escravo)", 4, "pendência",
                         f"Documento consta em {len(achados)} registro(s), incluído em "
                         f"{_data(achados['data_inclusao'].min())}", ENCAMINHAMENTO["lista_suja"], "MTE"), achados
    return _criterio("lista_suja", "Lista Suja (trabalho escravo)", 4, "sem ocorrência",
                     "Documento não consta no Cadastro de Empregadores", "—", "MTE"), achados


def _nao_verificados() -> list[dict]:
    cobertos = {3, 4, 7}
    return [_criterio(f"ab_s_{r.n}", r.criterio_ab_s, r.n, "não verificado", r.observacao or "Sem fonte aberta "
                      "integrada", ENCAMINHAMENTO["nao_verificado"], r.fonte_ab_s)
            for r in ab_s.CRITERIOS.itertuples() if r.n not in cobertos]


def resultado_geral(criterios: list[dict]) -> dict:
    contagem = {s: sum(c["situacao"] == s for c in criterios) for s in SITUACOES}
    if contagem["inconclusivo"]:
        texto = "Inconclusivo: falta uma entrada para verificar o imóvel"
        situacao = "inconclusivo"
    elif contagem["pendência"]:
        situacao, texto = "com pendência", f"{contagem['pendência']} pendência(s) com causa e fonte identificadas"
    elif contagem["indício"]:
        situacao, texto = "com indício", f"{contagem['indício']} indício(s) a conferir; nenhuma pendência confirmada"
    else:
        situacao, texto = "sem pendência nas fontes verificadas", "Nada encontrado nas fontes verificadas"
    return {"situacao": situacao, "resumo": texto, "contagem": contagem}


def diagnosticar(car: pd.DataFrame, embargos: pd.DataFrame, alertas: pd.DataFrame, lista_suja: pd.DataFrame,
                 prodes: pd.DataFrame, documento_hash: str | None = None,
                 ultimo_ano_prodes: int | None = None) -> dict:
    """Ficha do imóvel `car` (DataFrame tratado do SICAR com uma linha). As fontes entram já tratadas.

    `ultimo_ano_prodes`: último ano PRODES publicado; separa alerta "não confirmado" de "aguardando consolidação".
    """
    linha = car.iloc[0]
    car_geom = shapely.make_valid(shapely.from_wkt(linha["geometria_wkt"]))
    imovel = {c: (None if pd.isna(linha[c]) else getattr(linha[c], "item", lambda: linha[c])()) for c in
              ["cod_imovel", "uf", "cod_municipio", "municipio", "tipo_imovel", "status_imovel", "condicao",
               "area_geom_ha", "m_fiscal", "fracao_coberta_por_outros"]}
    imovel["data_atualizacao"] = _data(linha["data_atualizacao"])
    imovel["status_texto"] = STATUS_CAR.get(imovel["status_imovel"], imovel["status_imovel"])

    emb = embargos_do_imovel(car, car_geom, embargos, documento_hash)
    alt = alertas_do_imovel(car, car_geom, alertas, prodes, ultimo_ano_prodes)
    prd = prodes_do_imovel(car, car_geom, prodes)
    crit_ls, ls = _criterio_lista_suja(lista_suja, documento_hash)
    criterios = [_criterio_car(imovel), _criterio_embargo(emb), _criterio_desmatamento(alt, prd), crit_ls,
                 *_nao_verificados()]
    return {"imovel": imovel, "resultado": resultado_geral(criterios), "criterios": criterios,
            "evidencias": {"embargos": emb, "alertas": alt, "prodes": prd,
                           "lista_suja": ls[["id_registro", "uf", "cnae", "data_inclusao", "data_decisao"]]},
            "geometria_car": linha["geometria_wkt"]}


def ficha_inconclusiva(motivo: str, candidatos: list[str] | None = None) -> dict:
    criterios = [_criterio("car", "CAR", 3, "inconclusivo", motivo, "Informar o código do CAR do imóvel (recibo "
                           "de inscrição) ou a coordenada da sede.", "SICAR"),
                 *_nao_verificados()]
    return {"imovel": {"candidatos": candidatos or []}, "resultado": resultado_geral(criterios),
            "criterios": criterios, "evidencias": {}, "geometria_car": None}


# ---------------------------------------------------------------------------------------------------------------
# Entrada e saída
# ---------------------------------------------------------------------------------------------------------------

def _procedencia_lote() -> list[dict]:
    """Última execução bem-sucedida de cada fonte em lote (procedencia_fontes.json, gravado por python -m pipeline;
    o relatório da última execução completa cobre o que ainda não estiver lá)."""
    fontes = {}
    relatorio_exec = config.DADOS_PROCESSADOS / "relatorio_execucao.json"
    if relatorio_exec.exists():
        execucao = json.loads(relatorio_exec.read_text())
        fontes = {f["fonte"]: {"executado_em": execucao.get("inicio", ""), **f} for f in execucao["fontes"]
                  if f["status"] == "ok"}
    procedencia = config.DADOS_PROCESSADOS / "procedencia_fontes.json"
    if procedencia.exists():
        fontes.update(json.loads(procedencia.read_text()))
    nomes = {"ibama_embargos": "IBAMA, áreas embargadas (CSV)", "inpe_deter": "INPE DETER (WFS, em lote)",
             "mte_lista_suja": "MTE, Cadastro de Empregadores (PDF)"}
    saida = []
    for fonte, nome in nomes.items():
        if fonte in fontes:
            e, s = fontes[fonte]["entrada"], fontes[fonte]["saida"]
            saida.append({"fonte": nome, "como": "lote", "url": e.get("url") or e.get("servico"),
                          "data": (e.get("baixado_em_utc") or fontes[fonte]["executado_em"])[:10],
                          "sha256": e.get("sha256", "por partição, no relatório de execução"),
                          "arquivo": s.get("arquivo")})
    return saida


def _procedencia_consulta(nome: str, resultado) -> list[dict]:
    """Uma linha por consulta; várias requisições (o PRODES faz uma por ano) viram uma linha com a contagem."""
    reqs = resultado.entrada.get("requisicoes", [])
    if len(reqs) == 1:
        r = reqs[0]
        return [{"fonte": nome, "como": "sob demanda", "url": resultado.entrada.get("servico"),
                 "data": r["consultado_em_utc"][:10], "sha256": r["sha256"], "arquivo": r["arquivo"]}]
    datas = sorted(r["consultado_em_utc"][:10] for r in reqs)
    return [{"fonte": nome, "como": f"sob demanda, {len(reqs)} requisições", "url": resultado.entrada.get("servico"),
             "data": datas[0] if datas[0] == datas[-1] else f"{datas[0]} a {datas[-1]}",
             "sha256": f"{len(reqs)} respostas, cada uma no seu .meta.json",
             "arquivo": str(Path(reqs[0]["arquivo"]).parent)}] if reqs else []


@functools.cache
def _prodes_lote() -> tuple[pd.DataFrame, STRtree]:
    df = pd.read_parquet(inpe_prodes.ARQ_SAIDA)
    return df, STRtree(shapely.from_wkt(df["geometria_wkt"].to_numpy()))


def ultimo_ano_do_imovel(prodes: pd.DataFrame, ultimo_por_bioma: dict[str, int]) -> int:
    """Último ano publicado nos biomas com PRODES em volta do imóvel (o menor, se forem dois): no Cerrado o ano
    pode já ter saído e na Mata Atlântica não. Sem polígono em volta, vale o menor de todos."""
    biomas = set(prodes["bioma"]) & set(ultimo_por_bioma) or set(ultimo_por_bioma)
    return min(ultimo_por_bioma[b] for b in biomas)


def obter_prodes(uf: str, limites: tuple, atualizar: bool = False) -> tuple[pd.DataFrame, dict, list[dict]]:
    """PRODES em volta do imóvel (retângulo `limites`): do parquet do lote se a UF está no recorte; senão, consulta
    sob demanda. Devolve (polígonos, situação da publicação, procedência)."""
    publicacao = inpe_prodes.ler_publicacao()
    if publicacao and uf in publicacao["ufs"] and not atualizar:
        df, arvore = _prodes_lote()
        recorte = df.iloc[np.sort(arvore.query(shapely.box(*limites)))].reset_index(drop=True)
        situacao = {"origem": "lote", "ultimo_ano_publicado": publicacao["ultimo_ano_publicado"],
                    "verificado_em": publicacao["verificado_em_utc"][:10],
                    "proxima_verificacao": publicacao["proxima_verificacao"]}
        procedencia = [{"fonte": "INPE PRODES (parquet do lote)", "como": "lote, verificação mensal",
                        "url": config.URL_WFS_INPE.format(workspace="prodes-*"),
                        "data": f"verificado em {situacao['verificado_em']}", "sha256": publicacao["sha256"],
                        "arquivo": publicacao["arquivo"]}]
        return recorte, situacao, procedencia
    tabelas, procedencia, ultimos = [], [], {}
    for bioma in config.CAMADAS_PRODES:
        ultimos[bioma] = inpe_prodes.ultimo_ano(inpe_prodes.contagem_por_ano(bioma, pd.Timestamp.today().year + 1))
        df, r = inpe_prodes.consultar(bioma, limites=limites, desde=config.PRODES_DESDE, ate=ultimos[bioma],
                                      atualizar=atualizar)
        tabelas.append(df)
        procedencia += _procedencia_consulta(f"INPE PRODES {r.entrada['camada'].split(':')[0]} (WFS)", r)
    situacao = {"origem": "sob demanda", "ultimo_ano_publicado": ultimos,
                "verificado_em": pd.Timestamp.today().strftime("%Y-%m-%d"), "proxima_verificacao": None}
    return pd.concat(tabelas, ignore_index=True), situacao, procedencia


def executar(cod_imovel: str | None = None, lat: float | None = None, lon: float | None = None,
             documento: str | None = None, atualizar: bool = False) -> dict:
    """Consulta o SICAR e o PRODES, lê os parquets do lote e devolve a ficha (com a procedência)."""
    gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if cod_imovel:
        cars, r_car = sicar.consultar_codigo(cod_imovel, atualizar)
    else:
        cars, r_car = sicar.consultar_ponto(lat, lon, atualizar=atualizar)
    consulta = {"cod_imovel": cod_imovel, "lat": lat, "lon": lon, "documento_informado": bool(documento),
                "gerado_em": gerado_em}
    procedencia = _procedencia_consulta("SICAR (WFS)", r_car)
    ativos = cars[cars["status_imovel"] != "CA"] if len(cars) > 1 else cars
    if len(ativos) != 1:
        motivo = ("CAR não localizado no SICAR" if cars.empty else
                  f"{len(ativos)} CARs contêm o ponto informado; informe o código do imóvel")
        return {"consulta": consulta, **ficha_inconclusiva(motivo, cars["cod_imovel"].tolist()),
                "procedencia": procedencia}
    car = ativos.reset_index(drop=True)

    documento_hash = None
    if documento:
        numeros = somente_digitos(pd.Series([documento]))
        documento_hash = pseudonimizar(numeros, carregar_chave()).iloc[0]

    limites = shapely.from_wkt(car.at[0, "geometria_wkt"]).bounds
    prodes, publicacao, proc_prodes = obter_prodes(car.at[0, "uf"], limites, atualizar)
    ultimo = ultimo_ano_do_imovel(prodes, publicacao["ultimo_ano_publicado"])
    consulta["prodes"] = {**publicacao, "ultimo_ano_do_imovel": ultimo}
    ler = lambda nome: pd.read_parquet(config.DADOS_PROCESSADOS / f"{nome}.parquet")
    ficha = diagnosticar(car, ler("ibama_embargos"), ler("inpe_deter_alertas"), ler("mte_lista_suja"), prodes,
                         documento_hash, ultimo)
    return {"consulta": consulta, **ficha, "procedencia": _procedencia_lote() + proc_prodes + procedencia}


def _registros(df: pd.DataFrame) -> list[dict]:
    df = df.drop(columns=[c for c in ("geometria_wkt",) if c in df])
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def para_json(ficha: dict) -> dict:
    """Ficha serializável: evidências como listas de registros, sem as geometrias dos objetos."""
    return {**ficha, "evidencias": {k: _registros(v) for k, v in ficha["evidencias"].items()}}


def para_markdown(ficha: dict) -> str:
    im, res = ficha["imovel"], ficha["resultado"]
    titulo = im.get("cod_imovel") or ficha["consulta"].get("cod_imovel") or "imóvel não localizado"
    md = [f"# Pré-diagnóstico — {titulo}", "",
          f"Gerado em {ficha['consulta']['gerado_em']}. Pré-diagnóstico com a evidência de cada pendência; "
          "não é atestado de conformidade.", ""]
    if im.get("municipio"):
        md += [f"**Imóvel:** {im['municipio']}/{im['uf']} · {im['area_geom_ha']:.1f} ha · CAR "
               f"{im['status_texto']} ({im['condicao']})", ""]
    md += [f"**Resultado: {res['situacao']}.** {res['resumo']}.", "",
           "| Critério | AB+S | Situação | Evidência | Encaminhamento |", "|---|---|---|---|---|"]
    for c in ficha["criterios"]:
        md.append(f"| {c['criterio']} | {c['criterio_ab_s'] or '—'} | **{c['situacao']}** | {c['evidencia']} | "
                  f"{c['encaminhamento']} |")
    md += ["", "## Procedência", "", "| Fonte | Como | Data | SHA-256 |", "|---|---|---|---|"]
    md += [f"| {p['fonte']} | {p['como']} | {p['data']} | `{str(p['sha256'])[:16]}…` |" for p in ficha["procedencia"]]
    return "\n".join(md) + "\n"


def escrever(ficha: dict, pasta: Path = config.PREDIAGNOSTICO) -> dict[str, Path]:
    from pipeline import ficha_html

    pasta.mkdir(parents=True, exist_ok=True)
    nome = ficha["imovel"].get("cod_imovel") or f"inconclusivo_{ficha['consulta']['gerado_em'][:10]}"
    caminhos = {ext: pasta / f"{nome}.{ext}" for ext in ("json", "md", "html")}
    caminhos["json"].write_text(json.dumps(para_json(ficha), indent=2, ensure_ascii=False, default=str),
                                encoding="utf-8")
    caminhos["md"].write_text(para_markdown(ficha), encoding="utf-8")
    caminhos["html"].write_text(ficha_html.renderizar(ficha), encoding="utf-8")
    return caminhos


def demonstracao(atualizar: bool = False) -> Path:
    """Fichas dos CARs de demonstração (config.CARS_DEMONSTRACAO) e uma página índice, que compara o resultado de
    cada critério com o esperado para o caso."""
    from pipeline import ficha_html

    fichas = []
    for cod, caso in config.CARS_DEMONSTRACAO.items():
        ficha = executar(cod, documento=DOCUMENTO_DEMONSTRACAO, atualizar=atualizar)
        caminhos = escrever(ficha)
        fichas.append((ficha, caso, caminhos["html"].name))
    indice = config.PREDIAGNOSTICO / "index.html"
    indice.write_text(ficha_html.indice(fichas, inpe_prodes.ler_publicacao()), encoding="utf-8")
    return indice


# CPF fictício com dígito verificador válido (o mesmo dos testes): mostra a Lista Suja verificada, sem dado real.
DOCUMENTO_DEMONSTRACAO = "111.444.777-35"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pré-diagnóstico de pendências de um imóvel rural.")
    alvo = parser.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--car", help="código do imóvel no CAR (UF-IBGE-32 hexadecimais)")
    alvo.add_argument("--ponto", nargs=2, type=float, metavar=("LAT", "LON"), help="coordenada da sede")
    alvo.add_argument("--demo", action="store_true", help="gera as fichas dos CARs de demonstração")
    parser.add_argument("--documento", help="CPF ou CNPJ do proprietário (pseudonimizado, nunca gravado)")
    parser.add_argument("--atualizar", action="store_true",
                        help="consulta de novo o SICAR e o PRODES (este sob demanda, mesmo com o lote)")
    args = parser.parse_args(argv)
    relatorio.configurar_log(config.LOGS / f"prediagnostico_{datetime.now():%Y%m%d_%H%M%S}.log")

    if args.demo:
        log.info("Demonstração: %s", demonstracao(args.atualizar))
        return 0
    lat, lon = args.ponto or (None, None)
    ficha = executar(args.car, lat, lon, args.documento, args.atualizar)
    caminhos = escrever(ficha)
    log.info("Resultado: %s. Ficha: %s", ficha["resultado"]["situacao"], caminhos["html"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
