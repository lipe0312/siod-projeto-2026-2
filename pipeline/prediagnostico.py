"""Pré-diagnóstico de pendências de um imóvel rural: python -m pipeline.prediagnostico --car CÓDIGO [--documento CPF]

Do ponto de vista do produtor (o cruzamento.py parte do embargo ou do alerta). Para um CAR:
- CAR: status e condição no SICAR (consulta sob demanda);
- embargo IBAMA: polígono ou coordenada do embargo dentro do CAR, e embargo em nome do documento informado;
- desmatamento após 31/12/2020: alertas DETER dentro do CAR, confirmados ou não pelo PRODES, e polígonos PRODES
  (da partição da UF no lote; a UF entra no lote na primeira vez que um imóvel dela é consultado). Em bioma sem DETER,
  o período depois da última imagem PRODES aparece como aviso de "sem cobertura";
- Lista Suja: documento informado (pseudonimizado com a chave do pipeline, nunca gravado em claro);
- terras indígenas (FUNAI), territórios quilombolas (INCRA, pelo CMR/FUNAI, e IBGE 2022) e unidades de conservação (CNUC): sobreposição com o CAR;
- demais critérios do AB+S (1, 2 e 8): "não verificado", nunca "conforme".

Situação de cada critério: pendência (impede crédito ou venda sob a EUDR), indício (precisa de conferência),
sem ocorrência (nada encontrado nas fontes verificadas), não verificado (sem fonte aberta) ou inconclusivo (falta
entrada, como o CAR não localizado, ou a fonte não respondeu). Dado incompleto nunca vira "sem ocorrência" (ADR 0013). O resultado é um pré-diagnóstico com a evidência de cada pendência, não um
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
import requests
import shapely
from shapely.strtree import STRtree

from pipeline import config, cruzamento, relatorio, territorio, vetor
from pipeline.documentos import carregar_chave, pseudonimizar, somente_digitos
from pipeline.fontes import (ab_s, funai_terras_indigenas, incra_quilombolas, inpe_prodes, mma_unidades_conservacao,
                             sicar)
from pipeline.validacao import ErroDeValidacao

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
    "terra_indigena": "Sobreposição com terra indígena impede a qualificação no AgroBrasil+Sustentável. Conferir o "
                      "limite do CAR com o da terra indígena (FUNAI) e retificar o CAR se a sobreposição for erro de "
                      "desenho.",
    "terra_indigena_estudo": "Terra indígena ainda em estudo: conferir na FUNAI a situação do processo e o limite.",
    "quilombola": "Sobreposição com território quilombola delimitado impede a qualificação no AgroBrasil+Sustentável. "
                  "Conferir o limite com o INCRA (a base aberta é a do IBGE de 31/07/2022).",
    "quilombola_estudo": "Território quilombola em estudo técnico, com título anulado ou sem fase informada: conferir no "
                         "INCRA a situação e o limite.",
    "unidade_conservacao": "Unidade de conservação de proteção integral ou de domínio público: a atividade produtiva "
                           "dentro dela depende do órgão gestor. Conferir o limite e o plano de manejo.",
    "unidade_conservacao_indicio": "A categoria admite propriedade privada (APA, ARIE, RPPN) ou o limite é "
                                   "esquemático: conferir o plano de manejo e o limite com o órgão gestor.",
    "fonte_ausente": "Rodar o pipeline da fonte e repetir o pré-diagnóstico.",
    "fonte_falhou": "Repetir o pré-diagnóstico quando o serviço voltar.",
    "sem_documento": "Informar o CPF ou CNPJ de cada proprietário para verificar.",
}


def _data(valor) -> str | None:
    return None if pd.isna(valor) else pd.Timestamp(valor).strftime("%Y-%m-%d")


def _criterio(chave, nome, n_ab_s, situacao, evidencia, encaminhamento, fonte, aviso=None) -> dict:
    return {"chave": chave, "criterio": nome, "criterio_ab_s": n_ab_s, "situacao": situacao, "evidencia": evidencia,
            "encaminhamento": encaminhamento, "fonte": fonte, "aviso": aviso}


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
               "geometria_wkt", "situacao", "data_desembargo"]
    embargos = embargos.reindex(columns=list(dict.fromkeys([*embargos.columns, "situacao", "data_desembargo"])))
    embargos["situacao"] = embargos["situacao"].fillna("ativo")
    candidatos = embargos[embargos["uf"] == car["uf"].iloc[0]]
    com_geom = candidatos[candidatos["geometria_wkt"].notna()].reset_index(drop=True)
    geoms = vetor.tornar_validas(shapely.from_wkt(com_geom["geometria_wkt"].to_numpy()))
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
    geoms = vetor.tornar_validas(shapely.from_wkt(candidatos["geometria_wkt"].to_numpy()))
    pares = _dentro_do_car(geoms, car_geom, car)
    saida = candidatos.loc[pares.index, ["id_alerta", "classe", "data_imagem", "area_km2", "satelite",
                                         "geometria_wkt"]].rename(columns={"classe": "classe_deter"}).join(pares)
    saida = saida.reset_index(drop=True)
    if saida.empty:
        return saida.assign(situacao_prodes=pd.Series(dtype="string"), anos_prodes=pd.Series(dtype="string"))
    if ultimo_ano is None:  # o PRODES não respondeu: não há como confirmar
        return saida.assign(situacao_prodes="PRODES indisponível", anos_prodes="")
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
    no_imovel = emb[emb["classe"].isin(CLASSES_DENTRO + ("coordenada", "documento"))]
    na_divisa = len(emb) - len(no_imovel)
    levantado = no_imovel[no_imovel.get("situacao", pd.Series("ativo", index=no_imovel.index)) == "desembargado"]
    dentro = no_imovel.drop(levantado.index)
    nota = f"; {na_divisa} na divisa, não atribuído(s) ao imóvel" if na_divisa else ""
    if len(levantado):
        nota += "; " + ", ".join(f"TAD {_tad(r)} desembargado em {_br(_data(r.data_desembargo))}"
                                 for r in levantado.itertuples()) + " (histórico, não conta)"
    if len(dentro):
        tads = ", ".join(f"TAD {_tad(r)} ({r.como})" for r in dentro.itertuples())
        return _criterio("embargo", "Embargo IBAMA", 7, "pendência", f"{len(dentro)} embargo(s): {tads}{nota}",
                         ENCAMINHAMENTO["embargo"], "IBAMA")
    return _criterio("embargo", "Embargo IBAMA", 7, "sem ocorrência", "Nenhum embargo dentro do imóvel" + nota,
                     "—", "IBAMA")


def aviso_cobertura(biomas: list[str], ultima_imagem: dict) -> str | None:
    """Biomas do imóvel sem DETER: depois da última imagem PRODES, nenhuma fonte cobre o imóvel (ADR 0009, regra 4)."""
    sem_deter = [b for b in biomas if b not in config.BIOMAS_COM_DETER]
    if not sem_deter:
        return None
    partes = [f"{NOME_BIOMA.get(b, b)} sem DETER: sem cobertura de {_br(ultima_imagem.get(b))} até hoje"
              for b in sem_deter]
    return ("; ".join(partes) + " (o próximo PRODES cobre esse período). Para esse intervalo, conferir uma imagem de "
            "satélite recente do imóvel (ex.: Sentinel-2 no Copernicus Browser ou Planet/NICFI no MapBiomas Alerta)")


def _br(data: str | None) -> str:
    return pd.Timestamp(data).strftime("%d/%m/%Y") if data else "data desconhecida"


NOME_BIOMA = {"amazonia": "Amazônia", "caatinga": "Caatinga", "cerrado": "Cerrado", "mata_atlantica": "Mata Atlântica",
              "pampa": "Pampa", "pantanal": "Pantanal"}


def _criterio_desmatamento(alt: pd.DataFrame, prd: pd.DataFrame, falha: str | None = None,
                           aviso: str | None = None) -> dict:
    nome, fonte = "Desmatamento após 31/12/2020 (EUDR)", "INPE DETER e PRODES"
    if falha:
        n = int(alt["classe"].isin(CLASSES_DENTRO).sum()) if len(alt) else 0
        return _criterio("desmatamento", nome, None, "inconclusivo",
                         f"{falha}; {n} alerta(s) DETER dentro do imóvel sem como confirmar", ENCAMINHAMENTO[
                             "fonte_falhou"], fonte, aviso)
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
        return _criterio("desmatamento", nome, None, "pendência", texto, ENCAMINHAMENTO["desmatamento"], fonte, aviso)
    if len(a) or len(p):
        # Alerta sem confirmação, ou PRODES 2021 (o ano PRODES 2021 começa em 01/08/2020, antes da data de corte).
        return _criterio("desmatamento", nome, None, "indício", texto, ENCAMINHAMENTO["desmatamento_indicio"], fonte,
                         aviso)
    return _criterio("desmatamento", nome, None, "sem ocorrência", texto, "—", fonte, aviso)


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


# ---------------------------------------------------------------------------------------------------------------
# Sobreposição com áreas protegidas (critérios 5, 6 e 9 do AB+S; ADR 0014)
# ---------------------------------------------------------------------------------------------------------------

LIMIAR_SOBREPOSICAO_CAR = 0.05  # fração do CAR; abaixo disso, com faixa estreita, é contato de borda
CAMADAS_PROTEGIDAS = {
    # chave: (módulo da fonte, nome do critério, número no AB+S, fonte, argumento de --fontes)
    "terra_indigena": (funai_terras_indigenas, "Sobreposição: terras indígenas", 5, "FUNAI", "terras_indigenas"),
    "quilombola": (incra_quilombolas, "Sobreposição: território quilombola", 6, "INCRA (via CMR/FUNAI) e IBGE 2022",
                   "quilombolas"),
    "unidade_conservacao": (mma_unidades_conservacao, "Sobreposição: unidade de conservação", 9, "MMA (CNUC)",
                            "unidades_conservacao"),
}


@functools.cache
def _camada_protegida(chave: str) -> tuple[pd.DataFrame, STRtree] | None:
    arquivo = CAMADAS_PROTEGIDAS[chave][0].ARQ_SAIDA
    if not arquivo.exists():
        return None
    df = pd.read_parquet(arquivo)
    return df, STRtree(shapely.from_wkt(df["geometria_wkt"].to_numpy()))


def sobreposicoes(car: pd.DataFrame, car_geom, camada: pd.DataFrame, arvore: STRtree | None = None) -> pd.DataFrame:
    """Áreas protegidas que tocam o CAR, com a área e a fração do CAR atingida.

    A área protegida é muito maior que o imóvel, então a classe vem da fração do CAR (não da fração do objeto, como
    no embargo): "sobreposição" se atinge ao menos LIMIAR_SOBREPOSICAO_CAR do CAR ou a faixa comum é mais larga que
    cruzamento.LIMIAR_LARGURA_M; "tangente" se não (contato de borda, diferença de desenho). Ponto (UC sem limite no
    CNUC) dentro do CAR conta como "ponto dentro".
    """
    geoms = shapely.from_wkt(camada["geometria_wkt"].to_numpy())
    idx = np.sort(arvore.query(car_geom, predicate="intersects")) if arvore is not None else \
        np.flatnonzero(shapely.intersects(geoms, car_geom))
    linhas = {}
    for i in idx:
        g = geoms[i]
        if g.geom_type in ("Point", "MultiPoint"):
            linhas[i] = {"inter_ha": 0.0, "fracao_car": None, "largura_m": None, "classe": "ponto dentro"}
            continue
        par = cruzamento.pares_objeto_car(vetor.tornar_valida(g), car).iloc[0]
        tangente = par["fracao_car"] < LIMIAR_SOBREPOSICAO_CAR and par["largura_m"] < cruzamento.LIMIAR_LARGURA_M
        linhas[i] = {"inter_ha": par["inter_ha"], "fracao_car": par["fracao_car"], "largura_m": par["largura_m"],
                     "classe": "tangente" if tangente else "sobreposição"}
    pares = pd.DataFrame.from_dict(linhas, orient="index",
                                   columns=["inter_ha", "fracao_car", "largura_m", "classe"])
    return camada.loc[pares.index].join(pares).reset_index(drop=True)


def _situacao_protegida(chave: str, linha) -> tuple[str, str]:
    """(situação, encaminhamento) de uma área protegida que se sobrepõe ao CAR."""
    if chave == "terra_indigena":
        return ("indício", "terra_indigena_estudo") if linha.fase == "Em Estudo" else ("pendência", "terra_indigena")
    if chave == "quilombola":
        return (("indício", "quilombola_estudo") if linha.situacao in config.QUILOMBOLAS_INDICIO
                else ("pendência", "quilombola"))
    fraca = (linha.categoria in config.UC_CATEGORIAS_INDICIO or linha.so_ponto
             or linha.qualidade_poligono == config.UC_POLIGONO_ESQUEMATICO)
    return ("indício", "unidade_conservacao_indicio") if fraca else ("pendência", "unidade_conservacao")


def _descricao_protegida(chave: str, r) -> str:
    onde = (f"{r.inter_ha:.1f} ha, {r.fracao_car:.0%} do imóvel" if r.classe == "sobreposição"
            else "ponto de localização dentro do imóvel")
    if chave == "terra_indigena":
        return f"TI {r.nome} ({r.fase}; {onde})"
    if chave == "quilombola":
        return f"Território {r.nome} ({r.situacao.lower()}, base {r.base}; {onde})"
    return f"{r.nome} ({r.categoria}, {r.grupo.lower()}; {onde})"


def criterio_protegido(chave: str, achados: pd.DataFrame | None) -> dict:
    modulo, nome, n_ab_s, fonte, argumento = CAMADAS_PROTEGIDAS[chave]
    if achados is None:
        return _criterio(chave, nome, n_ab_s, "inconclusivo", f"Fonte não carregada ({modulo.ARQ_SAIDA.name}); rodar "
                         f"python -m pipeline --fontes {argumento}", ENCAMINHAMENTO["fonte_ausente"], fonte)
    dentro = achados[achados["classe"] != "tangente"]
    n_tangente = len(achados) - len(dentro)
    nota = f"; {n_tangente} só na borda, não contada(s)" if n_tangente else ""
    base = " Bases: INCRA (republicada pelo CMR/FUNAI) e IBGE de 31/07/2022." if chave == "quilombola" else ""
    if dentro.empty:
        return _criterio(chave, nome, n_ab_s, "sem ocorrência", f"Nenhuma sobreposição{nota}.{base}".replace("..", "."),
                         "—", fonte)
    situacoes = [_situacao_protegida(chave, r) for r in dentro.itertuples()]
    pior = next((s for s in situacoes if s[0] == "pendência"), situacoes[0])
    texto = f"{len(dentro)} sobreposição(ões): " + "; ".join(_descricao_protegida(chave, r)
                                                            for r in dentro.itertuples()) + nota + "." + base
    return _criterio(chave, nome, n_ab_s, pior[0], texto, ENCAMINHAMENTO[pior[1]], fonte)


def _nao_verificados() -> list[dict]:
    cobertos = {3, 4, 5, 6, 7, 9}
    return [_criterio(f"ab_s_{r.n}", r.criterio_ab_s, r.n, "não verificado", r.observacao or "Sem fonte aberta "
                      "integrada", ENCAMINHAMENTO["nao_verificado"], r.fonte_ab_s)
            for r in ab_s.CRITERIOS.itertuples() if r.n not in cobertos]


def resultado_geral(criterios: list[dict]) -> dict:
    """Pendência > inconclusivo > indício > sem pendência: uma pendência confirmada aparece mesmo com outro critério
    inconclusivo, e um critério inconclusivo impede "sem pendência" (ADR 0013)."""
    contagem = {s: sum(c["situacao"] == s for c in criterios) for s in SITUACOES}
    if contagem["pendência"]:
        situacao, texto = "com pendência", f"{contagem['pendência']} pendência(s) com causa e fonte identificadas"
        if contagem["inconclusivo"]:
            texto += f"; {contagem['inconclusivo']} critério(s) inconclusivo(s)"
    elif contagem["inconclusivo"]:
        texto = "Inconclusivo: falta uma entrada ou uma fonte não respondeu"
        situacao = "inconclusivo"
    elif contagem["indício"]:
        situacao, texto = "com indício", f"{contagem['indício']} indício(s) a conferir; nenhuma pendência confirmada"
    else:
        situacao, texto = "sem pendência nas fontes verificadas", "Nada encontrado nas fontes verificadas"
    return {"situacao": situacao, "resumo": texto, "contagem": contagem}


def diagnosticar(car: pd.DataFrame, embargos: pd.DataFrame, alertas: pd.DataFrame, lista_suja: pd.DataFrame,
                 prodes: pd.DataFrame, documento_hash: str | None = None,
                 ultimo_ano_prodes: int | None = None, protegidas: dict | None = None,
                 falha_prodes: str | None = None, aviso_desmatamento: str | None = None) -> dict:
    """Ficha do imóvel `car` (DataFrame tratado do SICAR com uma linha). As fontes entram já tratadas.

    `ultimo_ano_prodes`: último ano PRODES publicado; separa alerta "não confirmado" de "aguardando consolidação".
    `protegidas`: {chave de CAMADAS_PROTEGIDAS: (camada, árvore) ou None se a fonte não foi carregada}; sem o
    argumento, as três ficam vazias (sem ocorrência).
    `falha_prodes`: motivo, se o PRODES não pôde ser obtido (o critério de desmatamento fica inconclusivo).
    `aviso_desmatamento`: período sem cobertura em bioma sem DETER (ver aviso_cobertura).
    """
    linha = car.iloc[0]
    car_geom = vetor.tornar_valida(shapely.from_wkt(linha["geometria_wkt"]))
    imovel = {c: (None if pd.isna(linha[c]) else getattr(linha[c], "item", lambda: linha[c])()) for c in
              ["cod_imovel", "uf", "cod_municipio", "municipio", "tipo_imovel", "status_imovel", "condicao",
               "area_geom_ha", "m_fiscal", "fracao_coberta_por_outros"]}
    imovel["data_atualizacao"] = _data(linha["data_atualizacao"])
    imovel["status_texto"] = STATUS_CAR.get(imovel["status_imovel"], imovel["status_imovel"])

    emb = embargos_do_imovel(car, car_geom, embargos, documento_hash)
    alt = alertas_do_imovel(car, car_geom, alertas, prodes, ultimo_ano_prodes)
    prd = prodes_do_imovel(car, car_geom, prodes)
    crit_ls, ls = _criterio_lista_suja(lista_suja, documento_hash)
    evidencias = {"embargos": emb, "alertas": alt, "prodes": prd,
                  "lista_suja": ls[["id_registro", "uf", "cnae", "data_inclusao", "data_decisao"]]}
    crit_protegidas = []
    for chave, (modulo, *_resto) in CAMADAS_PROTEGIDAS.items():
        fonte = (protegidas or {}).get(chave, (pd.DataFrame(columns=modulo.COLUNAS_SAIDA), None))
        achados = None if fonte is None else sobreposicoes(car, car_geom, fonte[0], fonte[1])
        evidencias[chave] = achados if achados is not None else pd.DataFrame(columns=modulo.COLUNAS_SAIDA)
        crit_protegidas.append(criterio_protegido(chave, achados))
    criterios = [_criterio_car(imovel), _criterio_embargo(emb),
                 _criterio_desmatamento(alt, prd, falha_prodes, aviso_desmatamento), crit_ls, *crit_protegidas,
                 *_nao_verificados()]
    return {"imovel": imovel, "resultado": resultado_geral(criterios), "criterios": criterios,
            "evidencias": evidencias, "geometria_car": linha["geometria_wkt"]}


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
             "mte_lista_suja": "MTE, Cadastro de Empregadores (PDF)",
             "funai_terras_indigenas": "FUNAI, terras indígenas (WFS, em lote)",
             "mma_unidades_conservacao": "MMA, CNUC (shapefile, em lote)",
             "ibge_territorios_quilombolas": "IBGE, territórios quilombolas 2022 (shapefile, em lote)",
             "incra_quilombolas": "INCRA, áreas quilombolas (WFS do CMR/FUNAI, em lote)"}
    saida = []
    for fonte, nome in nomes.items():
        if fonte in fontes:
            e, s = fontes[fonte]["entrada"], fontes[fonte]["saida"]
            saida.append({"fonte": nome, "como": "lote", "url": e.get("url") or e.get("servico"),
                          "data": (e.get("baixado_em_utc") or e.get("consultado_em_utc")
                                   or fontes[fonte]["executado_em"])[:10],
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
def _prodes_uf(uf: str, sha256: str) -> tuple[pd.DataFrame, STRtree]:
    """Partição da UF (o sha256 entra na chave do cache: partição regravada é lida de novo)."""
    df = inpe_prodes.ler_uf(uf)
    return df, STRtree(shapely.from_wkt(df["geometria_wkt"].to_numpy()))


def ultimo_ano_do_imovel(biomas: list[str], ultimo_por_bioma: dict[str, int]) -> int:
    """Último ano publicado nos biomas do imóvel (o menor, se forem dois): no Cerrado o ano pode já ter saído e na
    Mata Atlântica não. Sem bioma conhecido, vale o menor de todos."""
    validos = [b for b in biomas if ultimo_por_bioma.get(b)] or [b for b, a in ultimo_por_bioma.items() if a]
    return min(ultimo_por_bioma[b] for b in validos)


class UFForaDoLote(RuntimeError):
    """A UF do imóvel ainda não está no lote do PRODES e a consulta não pode baixá-la."""


def obter_prodes(uf: str, limites: tuple, baixar: bool = True) -> tuple[pd.DataFrame, dict, list[dict]]:
    """PRODES em volta do imóvel (retângulo `limites`), da partição da UF no lote. A UF que ainda não está no lote
    entra agora (inpe_prodes.garantir_uf); com `baixar=False`, não vai à rede e a UF fora do lote gera UFForaDoLote.
    Devolve (polígonos, situação da publicação, procedência)."""
    publicacao = inpe_prodes.ler_publicacao()
    if not (publicacao and uf in publicacao["particoes"]):
        if not baixar:
            raise UFForaDoLote(f"UF {uf} ainda não carregada no lote do PRODES")
        publicacao = inpe_prodes.garantir_uf(uf)
    particao = publicacao["particoes"][uf]
    df, arvore = _prodes_uf(uf, particao["sha256"])
    recorte = df.iloc[np.sort(arvore.query(shapely.box(*limites)))].reset_index(drop=True)
    situacao = {"origem": "lote", "uf": uf, "ultimo_ano_publicado": publicacao["ultimo_ano_publicado"],
                "ultima_imagem": (publicacao.get("ultima_imagem_uf") or {}).get(uf) or publicacao["ultima_imagem"],
                "verificado_em": publicacao["verificado_em_utc"][:10],
                "proxima_verificacao": publicacao["proxima_verificacao"]}
    procedencia = [{"fonte": f"INPE PRODES (lote, partição {uf})", "como": "lote, verificação mensal",
                    "url": config.URL_WFS_INPE.format(workspace="prodes-*"),
                    "data": f"verificado em {situacao['verificado_em']}", "sha256": particao["sha256"],
                    "arquivo": particao["arquivo"]}]
    return recorte, situacao, procedencia


def executar(cod_imovel: str | None = None, lat: float | None = None, lon: float | None = None,
             documento: str | None = None, atualizar: bool = False, baixar_prodes: bool = True) -> dict:
    """Consulta o SICAR e o PRODES, lê os parquets do lote e devolve a ficha (com a procedência)."""
    gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    consulta = {"cod_imovel": cod_imovel, "lat": lat, "lon": lon, "documento_informado": bool(documento),
                "gerado_em": gerado_em}
    if cod_imovel:
        cars, r_car = sicar.consultar_codigo(cod_imovel, atualizar)
    else:
        uf_ponto = territorio.uf_do_ponto(lat, lon)
        if not uf_ponto:
            return {"consulta": consulta, **ficha_inconclusiva("Coordenada fora do território brasileiro (contorno "
                                                               "das UFs do IBGE)"), "procedencia": []}
        cars, r_car = sicar.consultar_ponto(lat, lon, uf=uf_ponto, atualizar=atualizar)
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

    car_geom = shapely.from_wkt(car.at[0, "geometria_wkt"])
    biomas = territorio.biomas_da_geometria(car_geom)
    falha = None
    try:
        prodes, publicacao, proc_prodes = obter_prodes(car.at[0, "uf"], car_geom.bounds, baixar_prodes)
        ultimo = ultimo_ano_do_imovel(biomas, publicacao["ultimo_ano_publicado"])
        aviso = aviso_cobertura(biomas, publicacao["ultima_imagem"])  # já é a da UF do imóvel (obter_prodes)
    except (requests.RequestException, ErroDeValidacao, RuntimeError) as e:
        log.error("PRODES indisponível para %s: %s", car.at[0, "uf"], e)
        falha = (str(e) if isinstance(e, UFForaDoLote) else
                 f"PRODES indisponível em {gerado_em[:10]} ({type(e).__name__})")
        prodes = pd.DataFrame(columns=inpe_prodes.COLUNAS_LOTE)
        publicacao, proc_prodes, ultimo, aviso = {"origem": "falhou", "motivo": str(e)[:300]}, [], None, None
    consulta["prodes"] = {**publicacao, "ultimo_ano_do_imovel": ultimo}
    consulta["biomas"] = biomas
    ler = lambda nome: pd.read_parquet(config.DADOS_PROCESSADOS / f"{nome}.parquet")
    protegidas = {chave: _camada_protegida(chave) for chave in CAMADAS_PROTEGIDAS}
    ficha = diagnosticar(car, ler("ibama_embargos"), ler("inpe_deter_alertas"), ler("mte_lista_suja"), prodes,
                         documento_hash, ultimo, protegidas, falha, aviso)
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


def demonstracao(atualizar: bool = False, baixar_prodes: bool = True) -> Path:
    """Fichas dos CARs de demonstração (config.CARS_DEMONSTRACAO) e uma página índice, que compara o resultado de
    cada critério com o esperado para o caso."""
    from pipeline import ficha_html

    fichas = []
    for cod, caso in config.CARS_DEMONSTRACAO.items():
        ficha = executar(cod, documento=DOCUMENTO_DEMONSTRACAO, atualizar=atualizar, baixar_prodes=baixar_prodes)
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
    parser.add_argument("--atualizar", action="store_true", help="consulta de novo o SICAR")
    parser.add_argument("--sem-baixar-prodes", action="store_true",
                        help="não inclui UF nova no lote do PRODES (o desmatamento de imóvel fora do lote fica "
                             "inconclusivo); para quando o TerraBrasilis está fora do ar")
    args = parser.parse_args(argv)
    relatorio.configurar_log(config.LOGS / f"prediagnostico_{datetime.now():%Y%m%d_%H%M%S}.log")

    if args.demo:
        log.info("Demonstração: %s", demonstracao(args.atualizar, not args.sem_baixar_prodes))
        return 0
    lat, lon = args.ponto or (None, None)
    ficha = executar(args.car, lat, lon, args.documento, args.atualizar, not args.sem_baixar_prodes)
    caminhos = escrever(ficha)
    log.info("Resultado: %s. Ficha: %s", ficha["resultado"]["situacao"], caminhos["html"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
