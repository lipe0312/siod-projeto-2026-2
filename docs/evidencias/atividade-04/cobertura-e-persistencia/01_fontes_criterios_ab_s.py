"""Testa as fontes abertas candidatas aos critérios do AB+S que o pré-diagnóstico ainda não verifica (1, 2, 5, 6, 8 e 9).

Roda da raiz: .venv/bin/python docs/evidencias/atividade-04/cobertura-e-persistencia/01_fontes_criterios_ab_s.py

Cada resposta fica em fontes/ com o .meta.json (URL, data UTC, status, SHA-256). O resumo vai para
01_fontes_criterios_ab_s.json. Nenhuma resposta guardada traz dado pessoal: a FUNAI e o CNUC publicam áreas, e do
SNCR só se guarda a página do formulário (sem consulta).
"""

import json
import re
import socket
import ssl
import sys
from collections import Counter
from pathlib import Path

import certifi
import requests
from requests.adapters import HTTPAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipeline import config, download  # noqa: E402

PASTA = Path(__file__).resolve().parent
FONTES = PASTA / "fontes"

FUNAI_WFS = "https://geoserver.funai.gov.br/geoserver/Funai/ows"
CNUC_CKAN = "https://dados.mma.gov.br/api/3/action/package_show"
SNCR_FORM = "https://sncr.serpro.gov.br/sncr-web/consultaPublica.jsf"
TERRABRASILIS_CAPS = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
HOSTS_INCRA = ("certificacao.incra.gov.br", "acervofundiario.incra.gov.br", "sigef.incra.gov.br")
# O servidor da FUNAI não envia o certificado intermediário. Ele é buscado no endereço AIA do próprio certificado
# (Sectigo) e acrescentado à cadeia do certifi; a verificação continua ligada e a raiz continua sendo a do certifi.
INTERMEDIARIO_FUNAI = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt"


class AdaptadorCadeiaCompleta(HTTPAdapter):
    def __init__(self, intermediario_pem: str, **kwargs):
        self.intermediario_pem = intermediario_pem
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        contexto = ssl.create_default_context(cafile=certifi.where())
        contexto.load_verify_locations(cadata=self.intermediario_pem)
        kwargs["ssl_context"] = contexto
        return super().init_poolmanager(*args, **kwargs)


def sessao_funai() -> requests.Session:
    der = requests.get(INTERMEDIARIO_FUNAI, timeout=60, headers={"User-Agent": config.USER_AGENT}).content
    sessao = requests.Session()
    sessao.mount("https://geoserver.funai.gov.br", AdaptadorCadeiaCompleta(ssl.DER_cert_to_PEM_cert(der)))
    return sessao


def funai() -> dict:
    """Terras indígenas (critério 5): todas as feições, só atributos, para contar fases e datas de atualização.
    O serviço responde 403 a GetFeature sem `count` e a `resultType=hits` (bloqueio na frente do GeoServer)."""
    sessao = sessao_funai()
    conteudo, meta = download.consultar(FUNAI_WFS, FONTES / "funai_tis_poligonais_atributos.json.gz", {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeName": "Funai:tis_poligonais",
        "outputFormat": "application/json", "propertyName": "terrai_codigo,uf_sigla,fase_ti,data_atualizacao",
        "count": "5000"},
        sessao=sessao)
    dados = json.loads(conteudo)
    props = [f["properties"] for f in dados["features"]]
    anos = Counter((p.get("data_atualizacao") or "")[-4:] for p in props)
    _, meta_geo = download.consultar(FUNAI_WFS, FONTES / "funai_tis_poligonais_1_feicao.json", {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeName": "Funai:tis_poligonais",
        "outputFormat": "application/json", "count": "1"}, sessao=sessao)
    return {"status_http": meta["status_http"], "anunciado": dados.get("numberMatched"), "recebido": len(props),
            "crs": (dados.get("crs") or {}).get("properties", {}).get("name"),
            "fases": dict(Counter(p.get("fase_ti") for p in props)),
            "ufs": len({p.get("uf_sigla") for p in props}),
            "ano_da_atualizacao_mais_recente": max(a for a in anos if a), "por_ano_de_atualizacao": dict(sorted(anos.items())),
            "geometria_status_http": meta_geo["status_http"]}


def cnuc() -> dict:
    """Unidades de conservação (critério 9): recursos do conjunto no portal de dados abertos do MMA."""
    # A resposta do CKAN traz links pessoais de servidores (SharePoint): fica em data/raw/, fora do repositório.
    conteudo, meta = download.consultar(CNUC_CKAN, config.DADOS_BRUTOS / "cnuc" / "package_show.json",
                                        {"id": "unidadesdeconservacao"})
    recursos = json.loads(conteudo)["result"]["resources"]
    shp = [r for r in recursos if "shp" in (r.get("format") or "").lower()]
    return {"status_http": meta["status_http"], "recursos": len(recursos),
            "shapefiles": [{"nome": r["name"], "data": (r.get("created") or "")[:10],
                            "url_estavel": r["url"].startswith("https://dados.mma.gov.br/")} for r in shp]}


def sncr() -> dict:
    """Dados cadastrais (critério 1): o formulário da consulta pública, sem enviar consulta."""
    conteudo, meta = download.consultar(SNCR_FORM, FONTES / "sncr_consulta_publica.html")
    texto = conteudo.decode("utf-8", "replace")
    geracao = re.search(r"Gera[çc][ãa]o:\s*([0-9/]+)", texto)
    return {"status_http": meta["status_http"], "tem_hcaptcha": "hcaptcha" in texto.lower(),
            "data_ultima_geracao": geracao.group(1) if geracao else None,
            "campos_do_formulario": sorted(set(re.findall(r'<select id="([^"]+)"', texto)))}


def terrabrasilis() -> dict:
    """Camadas do TerraBrasilis úteis à cobertura nacional (PRODES de todos os biomas, TI, UC e limites)."""
    conteudo, meta = download.consultar(TERRABRASILIS_CAPS, FONTES / "terrabrasilis_capabilities.xml.gz", {
        "service": "WFS", "version": "2.0.0", "request": "GetCapabilities"})
    nomes = sorted(set(re.findall(r"<Name>([^<]+)</Name>", conteudo.decode("utf-8", "replace"))))
    filtro = lambda chave: [n for n in nomes if chave in n]
    return {"status_http": meta["status_http"], "prodes_anual": filtro("yearly_deforestation"),
            "terras_indigenas": filtro("indigenous_area"), "unidades_conservacao": filtro("conservation_units"),
            "limites_uf": filtro("states_")}


def incra() -> dict:
    """SIGEF e áreas quilombolas (critérios 2, 6 e 8): o INCRA publica por download; aqui só se testa se o nome
    resolve a partir desta máquina."""
    saida = {}
    for host in HOSTS_INCRA:
        try:
            saida[host] = sorted({e[4][0] for e in socket.getaddrinfo(host, 443)})
        except socket.gaierror as e:
            saida[host] = f"não resolve: {e}"
    return saida


def main() -> None:
    resumo = {}
    for nome, teste in [("funai", funai), ("cnuc", cnuc), ("sncr", sncr), ("terrabrasilis", terrabrasilis),
                        ("incra_dns", incra)]:
        try:
            resumo[nome] = teste()
        except Exception as e:  # registra a falha da fonte e segue para a próxima
            resumo[nome] = {"erro": f"{type(e).__name__}: {e}"}
    (PASTA / "01_fontes_criterios_ab_s.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(json.dumps(resumo, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
