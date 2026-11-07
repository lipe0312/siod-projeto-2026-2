"""Dossiê EUDR do imóvel para o comprador: python -m pipeline.prediagnostico --car CÓDIGO --dossie-eudr

A partir da ficha do pré-diagnóstico, escreve uma pasta com três arquivos:
- `dossie.geojson`: o polígono da área de produção (ou, dito explicitamente, do imóvel inteiro quando a área não foi
  informada), em WGS 84 com 7 casas decimais, um polígono por parcela, sempre "declarado pelo produtor";
- `dossie.json`: os mesmos dados, para outro sistema ler;
- `dossie.md`: o texto para o comprador, com o desmatamento depois de 31/12/2020 (na área declarada e no resto do
  imóvel), a data da imagem e o SHA-256 do arquivo de origem de cada evidência, embargos, sobreposições, os prazos e
  "o que não foi verificado".

O dossiê é um pré-diagnóstico com fonte e data, não um atestado: nenhuma frase afirma ausência de desmatamento sem a
fonte e a data ao lado (ADR 0013, ADR 0018). Não há CPF nem CNPJ aqui; a ficha só carrega o código do CAR.
Sem rede: as origens (SHA-256 dos arquivos) vêm de meta.carga e dos manifestos que o pipeline já gravou no lago.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import shapely
from shapely.geometry.polygon import orient

from pipeline import config, vetor
from pipeline.armazenamento import lago
from pipeline.fontes import sicar

log = logging.getLogger("pipeline")

CASAS_DECIMAIS = 7  # a EUDR pede ao menos 6
LIMITE_PONTO_HA = 4.0  # até 4 ha a EUDR aceita um ponto no lugar do polígono
CLASSES_DENTRO = ("principal", "parcial")
DECLARACAO = "declarado pelo produtor; não comprovado"
DOCUMENTO_SUPLEMENTAR = "docs/eudr-area-de-producao.md"

FONTE_FORMATO = {
    "nome": "Comissão Europeia, FAQ da EUDR, 5ª versão (30/04/2026), perguntas 1.1, 1.7, 1.8, 1.14 e 1.16",
    "url": "https://environment.ec.europa.eu/document/download/744919a7-8650-4850-89ad-a597268cd69e_en?filename="
           "FAQ-UPDATE-5th-Iteration+FINAL.pdf",
    "consultada_em": "05/11/2026",
    "registrada_em": DOCUMENTO_SUPLEMENTAR,
}
REGRAS_FORMATO = ["WGS 84 (EPSG:4326), latitude e longitude com pelo menos 6 casas decimais",
                  "um polígono por parcela, contígua ou não; sem ponto com raio",
                  f"parcela de até {LIMITE_PONTO_HA:g} ha aceita um ponto; acima disso, polígono",
                  "a declaração inteira enviada ao sistema de informação da UE tem no máximo 25 MB"]
ESPECIFICACAO_GEOJSON = ("Especificação GeoJSON do sistema de informação da EUDR: confira a especificação vigente. "
                         f"O link e a data da consulta não constam em {DOCUMENTO_SUPLEMENTAR}; este arquivo segue as "
                         "regras do FAQ acima e o GeoJSON da RFC 7946 (anel externo no sentido anti-horário).")
FONTE_PRAZOS = {"nome": "Regulamento (UE) 2023/1115, com os prazos após a revisão de 2025 (README do projeto)",
                "url": "https://eur-lex.europa.eu/eli/reg/2023/1115/oj",
                "nota": "confira o texto consolidado vigente antes de usar os prazos em contrato"}
PRAZOS = [{"para": "empresas grandes e médias", "data": "30/12/2026"},
          {"para": "micro e pequenas empresas", "data": "30/06/2027"}]
GADO = re.compile(r"\b(gado|bovin\w*|boi\w*|carne|pecu\w*)\b", re.I)


# ---------------------------------------------------------------------------------------------------------------
# Geolocalização
# ---------------------------------------------------------------------------------------------------------------

def _n(v: float) -> str:
    """Marcador de um número com casas fixas: o json.dumps não preserva zeros à direita, então o número entra como
    texto e _com_casas() tira as aspas depois."""
    return f"@@{v:.{CASAS_DECIMAIS}f}@@"


def _com_casas(texto: str) -> str:
    return re.sub(r'"@@(-?\d+\.\d+)@@"', r"\1", texto)


def _area_ha(geom) -> float:
    return float(shapely.area(sicar.projetar(geom)) / 1e4)


def parcelas(ficha: dict) -> tuple[str | None, list]:
    """(escopo, polígonos): "area_de_producao" se a ficha usou a área do produtor, "imovel_inteiro" se não, ou
    (None, []) se o imóvel não foi localizado. Um polígono por parte do MultiPolygon, anel externo anti-horário."""
    wkt, escopo = ficha.get("geometria_area_producao"), "area_de_producao"
    if not wkt:
        wkt, escopo = ficha.get("geometria_car"), "imovel_inteiro"
    if not wkt:
        return None, []
    geom = vetor.tornar_valida(shapely.from_wkt(wkt))
    partes = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    return escopo, [orient(p, 1.0) for p in partes if p.geom_type == "Polygon" and not p.is_empty]


def _texto_escopo(escopo: str) -> str:
    if escopo == "area_de_producao":
        return "área de produção informada pelo produtor"
    return ("imóvel inteiro (perímetro do CAR): a área de produção não foi informada, então este polígono pode "
            "incluir terra sem a commodity; declare só onde ela foi produzida")


def _anel(coords) -> list:
    return [[_n(x), _n(y)] for x, y in coords]


def geojson(ficha: dict, commodity: str | None = None) -> str | None:
    """Texto do dossie.geojson (FeatureCollection); None se o imóvel não foi localizado."""
    escopo, poligonos = parcelas(ficha)
    if not poligonos:
        return None
    cod = (ficha.get("imovel") or {}).get("cod_imovel")
    features = []
    for n, poligono in enumerate(poligonos, 1):
        ha = _area_ha(poligono)
        props = {"parcela": n, "escopo": escopo, "descricao_do_escopo": _texto_escopo(escopo),
                 "declaracao": DECLARACAO, "area_ha": round(ha, 2), "commodity": commodity,
                 "cod_car": cod, "forma": "polígono"}
        if ha <= LIMITE_PONTO_HA:
            p = poligono.representative_point()
            props["ponto_aceito"] = f"parcela de até {LIMITE_PONTO_HA:g} ha: a EUDR aceita um ponto"
            props["ponto"] = [_n(p.x), _n(p.y)]
        features.append({"type": "Feature", "properties": props,
                         "geometry": {"type": "Polygon", "coordinates": [_anel(poligono.exterior.coords),
                                                                         *[_anel(i.coords) for i in poligono.interiors]]}})
    colecao = {"type": "FeatureCollection", "name": "dossie_eudr", "datum": "WGS 84 (EPSG:4326)",
               "declaracao": DECLARACAO, "escopo": escopo, "descricao_do_escopo": _texto_escopo(escopo),
               "features": features}
    return _com_casas(json.dumps(colecao, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------------------------------------------
# Origem dos dados (SHA-256 dos arquivos)
# ---------------------------------------------------------------------------------------------------------------

def _br(valor) -> str:
    if valor is None or (not isinstance(valor, (list, dict)) and pd.isna(valor)):
        return "data desconhecida"
    return pd.Timestamp(valor).strftime("%d/%m/%Y")


def _entrada(cargas: pd.DataFrame | None, carga_id) -> tuple[dict, str | None]:
    """(entrada_json da carga, data da carga). Carga desconhecida: ({}, None)."""
    if cargas is None or cargas.empty or not isinstance(carga_id, str):
        return {}, None
    linha = cargas[cargas["carga_id"] == carga_id]
    if linha.empty:
        return {}, None
    r = linha.iloc[0]
    return json.loads(r["entrada_json"] or "{}"), _br(r["iniciada_em"])


def _ultima_carga(cargas: pd.DataFrame | None, fonte: str) -> str | None:
    if cargas is None or cargas.empty:
        return None
    ok = cargas[(cargas["fonte"] == fonte) & (cargas["status"] == "ok")]
    return None if ok.empty else ok.sort_values("iniciada_em").iloc[-1]["carga_id"]


def _manifesto(entrada: dict, camada: str, raiz: Path) -> dict | None:
    caminho = (entrada.get("manifestos") or {}).get(camada)
    if not caminho:
        return None
    try:
        return json.loads((Path(raiz) / caminho).read_text(encoding="utf-8")) | {"_arquivo": caminho}
    except (OSError, ValueError):
        return None


def origem_deter(camada, data_imagem, carga_id, cargas, raiz: Path) -> dict:
    """Arquivo de origem de um alerta DETER: a partição mensal do manifesto (Amazônia e Cerrado) ou o arquivo do
    TerraBrasilis (Pantanal), com o SHA-256 gravado na carga. `sha256` None se a carga não o registra."""
    entrada, carga_em = _entrada(cargas, carga_id)
    base = {"fonte": "INPE DETER", "camada": camada if isinstance(camada, str) else None, "carga_id": carga_id,
            "carga_em": carga_em, "url": None, "arquivo": None, "sha256": None}
    if not base["camada"]:
        return base
    arquivo = (entrada.get("arquivos") or {}).get(camada)
    if arquivo:
        return {**base, "url": arquivo.get("url"), "arquivo": Path(arquivo.get("url") or "").name or None,
                "sha256": arquivo.get("sha256"), "baixado_em": (arquivo.get("baixado_em_utc") or "")[:10]}
    manifesto = _manifesto(entrada, camada, raiz)
    if manifesto and pd.notna(data_imagem):
        dia = pd.Timestamp(data_imagem).strftime("%Y-%m-%d")
        for p in manifesto.get("particoes", []):
            if p["inicio"] <= dia < p["fim"]:
                return {**base, "url": manifesto.get("url"), "arquivo": f"{manifesto['_arquivo'].rsplit('/', 1)[0]}/"
                        f"{p['arquivo']}", "sha256": p["sha256"], "baixado_em": (manifesto.get("iniciado_em_utc") or "")[:10]}
    return base


def origem_prodes(bioma, carga_id, cargas) -> dict:
    """Arquivo de origem de um polígono PRODES: o zip do bioma no TerraBrasilis (versão, URL e SHA-256 da carga)."""
    entrada, carga_em = _entrada(cargas, carga_id)
    base = {"fonte": "INPE PRODES", "bioma": bioma if isinstance(bioma, str) else None, "carga_id": carga_id,
            "carga_em": carga_em, "url": None, "versao": None, "sha256": None}
    arquivo = (entrada.get("arquivos") or {}).get(bioma) if isinstance(bioma, str) else None
    if arquivo:
        return {**base, "url": arquivo.get("url"), "versao": arquivo.get("versao"), "sha256": arquivo.get("sha256")}
    return base


def bases_consultadas(ficha: dict, cargas, raiz: Path, ultima_imagem_deter: dict | None) -> list[dict]:
    """O que foi consultado, com data e SHA-256, mesmo quando nada foi encontrado (a frase "sem alerta" precisa de
    fonte e data ao lado). `ultima_imagem_deter`: {bioma: data da última imagem DETER daquele bioma}. Falta de carga,
    de data ou de SHA-256 vira a lista `faltando` da base (ADR 0013: sem fonte e data, o resultado é inconclusivo)."""
    ultima_imagem_deter = ultima_imagem_deter or {}
    biomas = (ficha.get("consulta") or {}).get("biomas") or []
    saida = []
    carga = _ultima_carga(cargas, "inpe_deter")
    entrada, carga_em = _entrada(cargas, carga)
    for b in sorted(biomas):
        if b not in config.BIOMAS_COM_DETER:
            saida.append({"fonte": "INPE DETER", "bioma": b, "situacao": "sem DETER neste bioma", "carga_em": None,
                          "sha256": None, "arquivo": None})
            continue
        arq = (entrada.get("arquivos") or {}).get(b)
        manifesto = _manifesto(entrada, b, raiz)
        ultima = ultima_imagem_deter.get(b)
        faltando = []
        if not carga_em:
            faltando.append("carga do DETER não registrada em meta.carga (sem data da base)")
        if ultima is None or pd.isna(ultima):
            faltando.append(f"última imagem DETER do bioma {b} desconhecida")
        if not (arq or {}).get("sha256") and not (manifesto or {}).get("particoes"):
            faltando.append("SHA-256 do arquivo de origem do DETER não localizado")
        saida.append({"fonte": "INPE DETER", "bioma": b, "carga_id": carga, "carga_em": carga_em, "faltando": faltando,
                      "ultima_imagem_na_base": None if ultima is None or pd.isna(ultima) else _br(ultima),
                      "url": (arq or {}).get("url") or (manifesto or {}).get("url"),
                      "sha256": (arq or {}).get("sha256"),
                      "arquivo": ((arq["url"].rsplit("/", 1)[-1] if arq else None)
                                  or (manifesto or {}).get("_arquivo")),
                      "nota": None if arq or not manifesto else
                      f"{len(manifesto.get('particoes', []))} partições mensais; o SHA-256 de cada uma consta no "
                      "manifesto e em cada alerta listado"})
    carga = _ultima_carga(cargas, "inpe_prodes")
    entrada, carga_em = _entrada(cargas, carga)
    pr = (ficha.get("consulta") or {}).get("prodes") or {}
    for b in sorted(biomas):
        arq = (entrada.get("arquivos") or {}).get(b) or {}
        faltando = []
        if not carga_em:
            faltando.append("carga do PRODES não registrada em meta.carga (sem data da base)")
        if not arq.get("sha256"):
            faltando.append(f"SHA-256 do arquivo do PRODES do bioma {b} não localizado")
        if not pr.get("ultimo_ano_do_imovel"):
            faltando.append("último ano PRODES publicado desconhecido")
        saida.append({"fonte": "INPE PRODES", "bioma": b, "carga_id": carga, "carga_em": carga_em, "faltando": faltando,
                      "publicado_ate": pr.get("ultimo_ano_do_imovel"), "verificado_em": pr.get("verificado_em"),
                      "url": arq.get("url"), "versao": arq.get("versao"), "sha256": arq.get("sha256")})
    return saida


def _ultima_imagem_deter() -> dict:
    """{bioma (camada): data da última imagem DETER dele}; um bioma sem alerta na base não aparece."""
    df = lago.ler_ou_none("ref.alerta_deter", colunas=["camada", "data_imagem"])
    if df is None or df.empty:
        return {}
    return {k: v for k, v in df.groupby("camada")["data_imagem"].max().items() if pd.notna(v)}


def _lacunas(bases: list[dict], escopo: str | None) -> list[str]:
    """Motivos pelos quais o resultado de desmatamento não tem fonte, data ou SHA-256 completos."""
    if not escopo:
        return []
    if not bases:
        return ["bioma do imóvel não identificado: nenhuma base DETER ou PRODES pôde ser ligada ao imóvel"]
    return [f"{b['fonte']} ({b['bioma']}): {m}" for b in bases for m in b.get("faltando", [])]


# ---------------------------------------------------------------------------------------------------------------
# Conteúdo
# ---------------------------------------------------------------------------------------------------------------

def _num(v, casas=2):
    return None if v is None or pd.isna(v) else round(float(v), casas)


def _alertas(df, cargas, raiz) -> list[dict]:
    if df is None or df.empty:
        return []
    saida = []
    for r in df.itertuples():
        saida.append({"id_alerta": r.id_alerta, "data_da_imagem": _br(r.data_imagem), "classe_deter": r.classe_deter,
                      "ha": _num(r.inter_ha), "posicao": r.classe, "conta_no_criterio": r.classe in CLASSES_DENTRO,
                      "situacao_prodes": r.situacao_prodes,
                      "anos_prodes": r.anos_prodes or None,
                      "origem": origem_deter(getattr(r, "camada", None), r.data_imagem, getattr(r, "carga_id", None),
                                             cargas, raiz)})
    return saida


def _poligonos_prodes(df, cargas) -> list[dict]:
    if df is None or df.empty:
        return []
    return [{"uuid": r.uuid, "ano_prodes": int(r.ano_prodes), "data_da_imagem": _br(r.data_imagem), "bioma": r.bioma,
             "ha": _num(r.inter_ha), "posicao": r.classe, "conta_no_criterio": r.classe in CLASSES_DENTRO,
             "origem": origem_prodes(r.bioma, getattr(r, "carga_id", None), cargas)} for r in df.itertuples()]


def _bloco_desmatamento(escopo: str, decide: bool, crit: dict, alt, prd, cargas, raiz) -> dict:
    return {"escopo": escopo, "decide_a_eudr": decide, "situacao": crit["situacao"], "evidencia": crit["evidencia"],
            "aviso": crit.get("aviso"), "fonte": crit["fonte"],
            "alertas_deter": _alertas(alt, cargas, raiz), "poligonos_prodes": _poligonos_prodes(prd, cargas)}


def _registros(df, colunas) -> list[dict]:
    if df is None or df.empty:
        return []
    df = df.reindex(columns=colunas)
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def _embargos(ev) -> list[dict]:
    df = ev.get("embargos")
    if df is None or df.empty:
        return []
    saida = []
    for r in df.itertuples():
        tad = f"{r.num_tad}-{r.ser_tad}" if pd.notna(r.ser_tad) else str(r.num_tad)
        saida.append({"tad": tad, "data_do_embargo": _br(r.data_embargo), "encontrado_por": r.como, "posicao": r.classe,
                      "infracao": None if pd.isna(r.descricao_infracao) else r.descricao_infracao,
                      "desembargado_em": _br(r.data_desembargo) if pd.notna(getattr(r, "data_desembargo", None))
                      else None})
    return saida


def _sobreposicoes(ev) -> dict:
    saida = {}
    for chave, nome in (("terra_indigena", "terras indígenas (FUNAI)"),
                        ("quilombola", "territórios quilombolas (INCRA e IBGE 2022)"),
                        ("unidade_conservacao", "unidades de conservação (CNUC/MMA)")):
        df = ev.get(chave)
        saida[nome] = [] if df is None or df.empty else [
            {"nome": r.nome, "posicao": r.classe, "ha": _num(getattr(r, "inter_ha", None)),
             "fracao_do_imovel": _num(getattr(r, "fracao_car", None), 4)} for r in df.itertuples()]
    return saida


def nao_verificado(ficha: dict, escopo: str | None, commodity: str | None, bases: list[dict], blocos: dict) -> list[str]:
    """Sempre presente. Tudo o que o dossiê não cobre ou que ficou sem fonte, com o motivo."""
    itens = []
    if escopo is None:
        itens.append("Imóvel não localizado: nenhum polígono, desmatamento, embargo ou sobreposição foi verificado "
                     f"({ficha['criterios'][0]['evidencia']}).")
    if escopo == "imovel_inteiro":
        itens.append("Área de produção não informada: o desmatamento foi cruzado com o imóvel inteiro (CAR), que pode "
                     "incluir terra sem a commodity. A EUDR avalia a parcela onde a commodity foi produzida.")
    if not commodity:
        itens.append("Commodity não informada: o dossiê não diz qual produto sai da área.")
    elif GADO.search(commodity):
        itens.append("Gado: a EUDR pede um ponto por estabelecimento onde o animal esteve, sem polígono, e a cadeia "
                     "de GTA; este dossiê só trata de polígono de lavoura.")
    itens.append("O polígono é declaração do produtor: nenhum documento certifica a área de produção. Conferir com "
                 "imagem de satélite da cultura na área e com o volume vendido, plausível para a área e a "
                 "produtividade da região (nada disso foi feito aqui).")
    itens.append("Legalidade além das bases consultadas: CCIR, SIGEF, licenças, autorização de supressão (ASV) e "
                 "documentos fundiários não foram conferidos.")
    itens.append("Desmatamento menor que a resolução do DETER e do PRODES, ou posterior à última imagem de cada base, "
                 "não aparece nelas.")
    for c in ficha["criterios"]:
        if c["situacao"] == "não verificado":
            itens.append(f"Critério {c['criterio_ab_s']} do AB+S ({c['criterio']}): {c['evidencia']}")
        elif c["situacao"] == "inconclusivo":
            itens.append(f"{c['criterio']}: inconclusivo. {c['evidencia']}")
        if c.get("aviso"):
            itens.append(f"Aviso em {c['criterio']}: {c['aviso']}")
    for b in bases:
        if b.get("situacao") == "sem DETER neste bioma":
            itens.append(f"Bioma {b['bioma']} sem DETER: depois da última imagem do PRODES nenhuma fonte cobre o imóvel.")
    for motivo in _lacunas(bases, escopo):
        itens.append(f"Fonte sem registro completo, desmatamento inconclusivo: {motivo}.")
    sem_sha = sum(1 for bloco in blocos.values() for x in (*bloco["alertas_deter"], *bloco["poligonos_prodes"])
                  if x["conta_no_criterio"] and x["origem"]["sha256"] is None)
    if sem_sha:
        itens.append(f"SHA-256 do arquivo de origem não localizado em {sem_sha} evidência(s) de desmatamento "
                     "(a carga não o registra); repetir a carga da fonte.")
    aguardando = sum(1 for bloco in blocos.values() for a in bloco["alertas_deter"]
                     if a["conta_no_criterio"] and a["situacao_prodes"] != "confirmado")
    if aguardando:
        itens.append(f"{aguardando} alerta(s) DETER ainda sem confirmação do PRODES: indício, a conferir em imagem.")
    if any(p["ano_prodes"] == 2021 for bloco in blocos.values() for p in bloco["poligonos_prodes"]):
        itens.append("PRODES 2021 vai de 01/08/2020 a 31/07/2021 e começa antes da data de corte (31/12/2020): "
                     "sozinho, conta como indício.")
    a = ficha.get("area_producao")
    if a and a.get("usada") and "desmatamento_resto" not in blocos:
        itens.append(f"A área declarada cobre o imóvel (sobra de {a.get('resto_ha')} ha): não há resto a cruzar.")
    return itens


def montar(ficha: dict, commodity: str | None = None, cargas: pd.DataFrame | None = None, raiz: Path | None = None,
           ultima_imagem_deter=None, agora: datetime | None = None) -> dict:
    """O conteúdo do dossiê (serializável). `cargas`: meta.carga (padrão: a do lago); `raiz`: onde estão os manifestos
    (padrão: a raiz do projeto)."""
    raiz = Path(raiz or config.RAIZ)
    commodity = vetor.nome_sem_documento(commodity.strip()) if commodity and commodity.strip() else None
    ev = ficha.get("evidencias") or {}
    por_chave = {c["chave"]: c for c in ficha["criterios"]}
    escopo, poligonos = parcelas(ficha)
    area = ficha.get("area_producao") or {}
    im = ficha.get("imovel") or {}
    blocos = {}
    if "desmatamento" in por_chave:
        com_area = escopo == "area_de_producao"
        blocos["desmatamento"] = _bloco_desmatamento(
            "na área declarada (decide o critério da EUDR)" if com_area else
            "no imóvel inteiro (área de produção não informada)", True, por_chave["desmatamento"],
            ev.get("alertas"), ev.get("prodes"), cargas, raiz)
    if "desmatamento_resto" in por_chave:
        blocos["desmatamento_resto"] = _bloco_desmatamento(
            "no resto do imóvel, fora da área declarada (risco de legalidade e de mistura)", False,
            por_chave["desmatamento_resto"], ev.get("alertas_resto"), ev.get("prodes_resto"), cargas, raiz)
    bases = bases_consultadas(ficha, cargas, raiz, ultima_imagem_deter) if escopo else []
    lacunas = _lacunas(bases, escopo)
    for bloco in blocos.values():
        bloco["lacunas_de_fonte"] = lacunas
        if lacunas and bloco["situacao"] == "sem ocorrência":  # ADR 0013: sem fonte e data, nunca "sem ocorrência"
            bloco["situacao_da_ficha"], bloco["situacao"] = bloco["situacao"], "inconclusivo"
    return {
        "dossie": "EUDR", "gerado_em": (agora or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "ficha_gerada_em": (ficha.get("consulta") or {}).get("gerado_em"),
        "aviso": "Pré-diagnóstico com fonte e data, não atestado. Não afirma ausência de desmatamento nem legalidade.",
        "imovel": {"cod_car": im.get("cod_imovel"), "municipio": im.get("municipio"), "uf": im.get("uf"),
                   "area_do_imovel_ha": _num(im.get("area_geom_ha"), 1),
                   "biomas": (ficha.get("consulta") or {}).get("biomas")},
        "commodity": commodity,
        "geolocalizacao": {
            "arquivo": "dossie.geojson" if escopo else None, "escopo": escopo, "descricao_do_escopo":
            _texto_escopo(escopo) if escopo else "imóvel não localizado", "declaracao": DECLARACAO,
            "area_ha": _num(sum(_area_ha(p) for p in poligonos)) if poligonos else None,
            "arquivo_da_area": area.get("arquivo") if escopo == "area_de_producao" else None,
            "fracao_da_area_fora_do_car": area.get("fracao_fora_do_car") if escopo == "area_de_producao" else None,
            "resto_do_imovel_ha": area.get("resto_ha") if escopo == "area_de_producao" else None,
            "parcelas": [{"parcela": n, "area_ha": _num(_area_ha(p)), "forma": "polígono",
                          "aceita_ponto": _area_ha(p) <= LIMITE_PONTO_HA} for n, p in enumerate(poligonos, 1)],
            "formato": {"sistema": "WGS 84 (EPSG:4326)", "casas_decimais": CASAS_DECIMAIS, "regras": REGRAS_FORMATO,
                        "fonte": FONTE_FORMATO, "especificacao_geojson": ESPECIFICACAO_GEOJSON},
            "nota_datum": "As coordenadas de origem estão em SIRGAS 2000 (SICAR e arquivo do produtor) e foram "
                          "gravadas como WGS 84 sem transformação; a diferença entre os dois é da ordem de 1 m ou menos "
                          "no Brasil."},
        "desmatamento_apos_31_12_2020": {
            "data_de_corte": "31/12/2020", "blocos": blocos, "bases_consultadas": bases,
            "ultima_imagem_deter_por_bioma": {k: _br(v) for k, v in (ultima_imagem_deter or {}).items()}},
        "embargos": {"situacao": por_chave.get("embargo", {}).get("situacao"),
                     "evidencia": por_chave.get("embargo", {}).get("evidencia"), "registros": _embargos(ev)},
        "sobreposicoes": {"criterios": {c["criterio"]: {"situacao": c["situacao"], "evidencia": c["evidencia"]}
                                        for k, c in por_chave.items()
                                        if k in ("terra_indigena", "quilombola", "unidade_conservacao")},
                          "registros": _sobreposicoes(ev)},
        "lista_suja": {k: por_chave.get("lista_suja", {}).get(k) for k in ("situacao", "evidencia")},
        "nao_verificado": nao_verificado(ficha, escopo, commodity, bases, blocos),
        "prazos": {"datas": PRAZOS, "fonte": FONTE_PRAZOS},
        "procedencia_da_ficha": ficha.get("procedencia", []),
    }


# ---------------------------------------------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------------------------------------------

def _linha_origem(o: dict) -> str:
    sha = f"`{o['sha256']}`" if o.get("sha256") else "SHA-256 não localizado"
    onde = o.get("arquivo") or o.get("versao") or ""
    return f"{onde} · {sha}".strip(" ·")


def _fonte_e_data(bases: list[dict]) -> str:
    """Fonte e data que ficam ao lado de cada resultado de desmatamento (detalhe e SHA-256 em "Bases consultadas")."""
    partes = []
    for b in bases:
        if b.get("situacao"):  # bioma sem DETER
            continue
        data = f"base carregada em {b['carga_em'] or 'data não registrada'}"
        if b.get("ultima_imagem_na_base"):
            data += f", imagens até {b['ultima_imagem_na_base']}"
        if b.get("publicado_ate"):
            data += f", publicado até {b['publicado_ate']}, verificado em {_br(b.get('verificado_em'))}"
        if b.get("faltando"):
            data += "; INCOMPLETO: " + ", ".join(b["faltando"])
        partes.append(f"{b['fonte']} {b['bioma']} ({data})")
    return "Fontes e datas: " + ("; ".join(partes) if partes else "nenhuma base consultada") + "."


def _md_bloco(titulo: str, b: dict, bases: list[dict]) -> list[str]:
    md = [f"### {titulo}", "", f"**Situação nas bases consultadas: {b['situacao']}.** {b['evidencia']}",
          "", _fonte_e_data(bases), ""]
    if b.get("lacunas_de_fonte"):
        md += ["**Sem fonte, data ou SHA-256 completos: o resultado fica inconclusivo, não “sem ocorrência”.** "
               + "; ".join(b["lacunas_de_fonte"]) + ".", ""]
    if b.get("aviso"):
        md += [f"Aviso: {b['aviso']}", ""]
    contados = [a for a in b["alertas_deter"] if a["conta_no_criterio"]]
    if contados:
        md += ["| Alerta DETER | Data da imagem | Classe | ha | PRODES | Origem e SHA-256 |", "|---|---|---|---|---|---|"]
        md += [f"| {a['id_alerta']} | {a['data_da_imagem']} | {a['classe_deter']} | {a['ha']} | "
               f"{a['situacao_prodes']}{' (' + a['anos_prodes'] + ')' if a['anos_prodes'] else ''} | "
               f"{a['origem'].get('camada') or '—'}: {_linha_origem(a['origem'])} |" for a in contados] + [""]
    contados = [p for p in b["poligonos_prodes"] if p["conta_no_criterio"]]
    if contados:
        md += ["| PRODES | Ano | Data da imagem | Bioma | ha | Origem e SHA-256 |", "|---|---|---|---|---|---|"]
        md += [f"| {p['uuid']} | {p['ano_prodes']} | {p['data_da_imagem']} | {p['bioma']} | {p['ha']} | "
               f"{_linha_origem(p['origem'])} |" for p in contados] + [""]
    na_divisa = (sum(not x["conta_no_criterio"] for x in b["alertas_deter"])
                 + sum(not x["conta_no_criterio"] for x in b["poligonos_prodes"]))
    if na_divisa:
        md += [f"{na_divisa} registro(s) tocam só a divisa e não foram atribuídos a este escopo.", ""]
    return md


def para_markdown(d: dict) -> str:
    im, geo = d["imovel"], d["geolocalizacao"]
    des = d["desmatamento_apos_31_12_2020"]
    md = [f"# Dossiê EUDR — {im['cod_car'] or 'imóvel não localizado'}", "",
          f"Gerado em {d['gerado_em']} (horário de Brasília), a partir do pré-diagnóstico de {d['ficha_gerada_em']}.", "",
          f"> {d['aviso']} Cada afirmação traz a fonte e a data ao lado; o que não tem fonte está em "
          "“O que não foi verificado”.", ""]
    if im["municipio"]:
        md += [f"**Imóvel:** {im['municipio']}/{im['uf']} · {im['area_do_imovel_ha']} ha · CAR {im['cod_car']}", ""]
    md += [f"**Commodity:** {d['commodity'] or 'não informada'}", ""]

    md += ["## 1. Geolocalização", ""]
    if geo["escopo"] is None:
        md += ["Imóvel não localizado: sem polígono. Ver “O que não foi verificado”.", ""]
    else:
        md += [f"Arquivo: `dossie.geojson` · {geo['descricao_do_escopo']} · **{geo['declaracao']}**.", "",
               f"Área declarada: **{geo['area_ha']} ha** em {len(geo['parcelas'])} parcela(s)"
               + (f" (arquivo do produtor: {geo['arquivo_da_area']})" if geo["arquivo_da_area"] else "") + ".", "",
               "| Parcela | ha | Forma | Aceita ponto (até 4 ha) |", "|---|---|---|---|"]
        md += [f"| {p['parcela']} | {p['area_ha']} | {p['forma']} | {'sim' if p['aceita_ponto'] else 'não'} |"
               for p in geo["parcelas"]]
        if geo["escopo"] == "area_de_producao":
            md += ["", f"Fora do imóvel do CAR: {geo['fracao_da_area_fora_do_car']:.1%} da área declarada. Resto do "
                   f"imóvel fora da área declarada: {geo['resto_do_imovel_ha']} ha."]
        md += ["", f"Formato: {geo['formato']['sistema']}, {geo['formato']['casas_decimais']} casas decimais. Regras:", ""]
        md += [f"- {r}" for r in geo["formato"]["regras"]]
        f = geo["formato"]["fonte"]
        md += ["", f"Fonte das regras: [{f['nome']}]({f['url']}), consultada em {f['consultada_em']} "
               f"(registrada em `{f['registrada_em']}`).", "", geo["formato"]["especificacao_geojson"], "",
               geo["nota_datum"], ""]

    md += [f"## 2. Desmatamento depois de {des['data_de_corte']}", ""]
    ordem = [("desmatamento", None), ("desmatamento_resto", None)]
    for chave, _ in ordem:
        bloco = des["blocos"].get(chave)
        if bloco:
            md += _md_bloco(bloco["escopo"][0].upper() + bloco["escopo"][1:], bloco, des["bases_consultadas"])
    if "desmatamento_resto" not in des["blocos"] and geo["escopo"] == "area_de_producao":
        md += ["### Resto do imóvel", "", "A área declarada cobre o imóvel: não há resto a cruzar.", ""]
    md += ["### Bases consultadas", ""]
    if des["bases_consultadas"]:
        md += ["| Fonte | Bioma | Data | SHA-256 do arquivo de origem |", "|---|---|---|---|"]
        for b in des["bases_consultadas"]:
            if b.get("situacao"):
                md.append(f"| {b['fonte']} | {b['bioma']} | — | {b['situacao']} |")
                continue
            data = f"base carregada em {b['carga_em'] or 'data não registrada'}"
            if b.get("ultima_imagem_na_base"):
                data += f"; imagens até {b['ultima_imagem_na_base']}"
            if b.get("publicado_ate"):
                data = f"publicado até {b['publicado_ate']}, verificado em {_br(b.get('verificado_em'))}; {data}"
            sha = f"`{b['sha256']}` ({b.get('arquivo') or b.get('versao') or ''})" if b.get("sha256") else (
                b.get("nota") or "SHA-256 não localizado")
            md.append(f"| {b['fonte']} | {b['bioma']} | {data} | {sha} |")
        md.append("")
    else:
        md += ["Nenhuma base foi consultada.", ""]

    md += ["## 3. Embargos, sobreposições e Lista Suja", "",
           f"**Embargo IBAMA: {d['embargos']['situacao']}.** {d['embargos']['evidencia']}", ""]
    if d["embargos"]["registros"]:
        md += ["| TAD | Data | Encontrado por | Posição | Infração |", "|---|---|---|---|---|"]
        md += [f"| {e['tad']} | {e['data_do_embargo']} | {e['encontrado_por']} | {e['posicao']} | "
               f"{e['infracao'] or '—'}{' (desembargado em ' + e['desembargado_em'] + ')' if e['desembargado_em'] else ''} |"
               for e in d["embargos"]["registros"]] + [""]
    for nome, c in d["sobreposicoes"]["criterios"].items():
        md.append(f"- **{nome}: {c['situacao']}.** {c['evidencia']}")
    for nome, regs in d["sobreposicoes"]["registros"].items():
        for r in regs:
            md.append(f"  - {nome}: {r['nome']} · {r['posicao']} · {r['ha']} ha")
    ls = d["lista_suja"]
    md += [f"- **Lista Suja (MTE): {ls['situacao']}.** {ls['evidencia']}", ""]

    md += ["## 4. O que não foi verificado", ""] + [f"- {i}" for i in d["nao_verificado"]] + [""]

    p = d["prazos"]
    md += ["## 5. Prazos da EUDR", ""] + [f"- {x['para']}: {x['data']}" for x in p["datas"]]
    md += ["", f"Fonte: [{p['fonte']['nome']}]({p['fonte']['url']}); {p['fonte']['nota']}.", ""]

    md += ["## 6. Procedência da ficha", "", "| Fonte | Como | Data | SHA-256 |", "|---|---|---|---|"]
    md += [f"| {x['fonte']} | {x['como']} | {x['data']} | `{str(x['sha256'])[:16]}…` |"
           for x in d["procedencia_da_ficha"]]
    return "\n".join(md) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------------------------------------------

def escrever(ficha: dict, pasta: Path, commodity: str | None = None, cargas: pd.DataFrame | None = None,
             raiz: Path | None = None, ultima_imagem_deter=None, agora: datetime | None = None) -> dict[str, Path]:
    """Grava dossie.json e dossie.md em `pasta` (e dossie.geojson, se o imóvel foi localizado). Sem `cargas`, lê
    meta.carga do lago; sem a última imagem do DETER, lê ref.alerta_deter."""
    cargas = lago.ler_ou_none("meta.carga") if cargas is None else cargas
    ultima_imagem_deter = _ultima_imagem_deter() if ultima_imagem_deter is None else ultima_imagem_deter
    dossie = montar(ficha, commodity, cargas, raiz, ultima_imagem_deter, agora)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = {"json": pasta / "dossie.json", "md": pasta / "dossie.md"}
    caminhos["json"].write_text(json.dumps(dossie, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    caminhos["md"].write_text(para_markdown(dossie), encoding="utf-8")
    texto = geojson(ficha, dossie["commodity"])
    if texto:
        caminhos["geojson"] = pasta / "dossie.geojson"
        caminhos["geojson"].write_text(texto + "\n", encoding="utf-8")
    else:
        log.warning("Dossiê EUDR sem polígono: imóvel não localizado")
    return caminhos


# ---------------------------------------------------------------------------------------------------------------
# Lote (carteira)
# ---------------------------------------------------------------------------------------------------------------

COLUNAS_INDICE = ["cod_car", "commodity", "escopo", "desmatamento_area_declarada", "desmatamento_resto_do_imovel",
                  "pasta", "execucao_id", "motivo"]
NAO_SE_APLICA = "não se aplica"


def nome_pasta(cod_imovel, alternativa: str = "imovel") -> str:
    """Nome de pasta do imóvel: o código do CAR sem "/" nem ".." (ou `alternativa` se não sobrar nada)."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(cod_imovel or alternativa)).strip("_") or "imovel"


def linha_indice(cod_car, commodity, pasta: str | None, execucao_id, caminhos: dict[str, Path] | None = None,
                 motivo: str | None = None) -> dict:
    """Uma linha do indice.csv. Com `caminhos` (o retorno de escrever), a situação vem do dossie.json já gravado, que
    é onde a regra da fonte incompleta (ADR 0013) foi aplicada; sem ele, o imóvel não teve dossiê e fica inconclusivo
    com o `motivo`. Sem CPF/CNPJ nem documento_hash: só o CAR e o que a planilha chama de commodity."""
    linha = {"cod_car": cod_car, "commodity": commodity, "escopo": None, "desmatamento_area_declarada": "inconclusivo",
             "desmatamento_resto_do_imovel": "inconclusivo", "pasta": pasta, "execucao_id": execucao_id,
             "motivo": motivo}
    if not caminhos:
        return linha
    d = json.loads(caminhos["json"].read_text(encoding="utf-8"))
    blocos = d["desmatamento_apos_31_12_2020"]["blocos"]
    escopo = d["geolocalizacao"]["escopo"]
    linha["escopo"] = {"area_de_producao": "área de produção", "imovel_inteiro": "imóvel inteiro"}.get(escopo)
    if "desmatamento" in blocos:
        linha["desmatamento_area_declarada"] = blocos["desmatamento"]["situacao"]
    elif not motivo:
        linha["motivo"] = "imóvel não localizado" if not escopo else "critério de desmatamento ausente na ficha"
    linha["desmatamento_resto_do_imovel"] = (blocos["desmatamento_resto"]["situacao"] if "desmatamento_resto" in blocos
                                             else NAO_SE_APLICA)
    return linha


def escrever_indice(linhas: list[dict], pasta: Path) -> Path:
    """Grava `indice.csv` em `pasta` (uma linha por imóvel)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / "indice.csv"
    pd.DataFrame(linhas, columns=COLUNAS_INDICE).to_csv(caminho, index=False)
    return caminho
