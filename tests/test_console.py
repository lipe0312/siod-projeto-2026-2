"""Console local (ADR 0027): telas, entrada conferida, cruzamento com etapas, inconclusivo com motivo e o documento
fora de URL, log e arquivo. Sem rede: o pré-diagnóstico é injetado (falso)."""

import json
import logging
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
import requests
from fastapi.testclient import TestClient

from conftest import CPF_VALIDO, CPF_VALIDO_2
from console import consulta
from console import __main__ as console_main
from console.servidor import criar_app
from pipeline import config, prediagnostico
from pipeline.armazenamento import lago
from pipeline.documentos import carregar_chave, pseudonimizar
from test_prediagnostico import alertas, car, embargos, hash_doc, lista_suja, prodes

DADOS = Path(__file__).parent / "dados" / "area_producao"
COD = "MG-3148103-" + "A" * 32
DIGITOS = CPF_VALIDO.replace(".", "").replace("-", "")


class Falso:
    """executar falso: a ficha sai do diagnosticar de verdade, com o documento pseudonimizado como o pipeline faz."""

    def __init__(self, erro: Exception | None = None, ficha: dict | None = None, espera: threading.Event | None = None):
        self.erro, self.ficha, self.espera, self.chamadas = erro, ficha, espera, []

    def __call__(self, cod_imovel=None, lat=None, lon=None, documento=None, atualizar=False, baixar_prodes=True,
                 area_producao=None):
        self.chamadas.append({"cod_imovel": cod_imovel, "lat": lat, "lon": lon, "documento": documento,
                              "area_producao": area_producao})
        if self.espera:
            self.espera.wait(5)
        if self.erro:
            raise self.erro
        consulta_ = {"cod_imovel": cod_imovel, "lat": lat, "lon": lon, "documento_informado": bool(documento),
                     "gerado_em": "2026-11-23 10:00:00", "prodes": {"ultimo_ano_do_imovel": 2025, "origem": "lote", "verificado_em": "2026-11-20"}}
        if self.ficha:
            return {"consulta": consulta_, **self.ficha, "procedencia": []}
        ficha = prediagnostico.diagnosticar(car(), embargos(), alertas(), lista_suja(CPF_VALIDO_2), prodes(),
                                            hash_doc(documento) if documento else None, ultimo_ano_prodes=2025)
        return {"consulta": consulta_, **ficha, "procedencia": []}


def cliente(executar=None) -> TestClient:
    return TestClient(criar_app(executar or Falso(), hosts=["testserver"]))


def cruzar(c: TestClient, dados: dict) -> dict:
    r = c.post("/api/consultas", json=dados)
    assert r.status_code == 202, r.text
    ident = r.json()["id"]
    limite = time.monotonic() + 10
    while time.monotonic() < limite:
        estado = c.get(f"/api/consultas/{ident}").json()
        if estado["estado"] != "rodando":
            return estado
        time.sleep(0.02)
    raise AssertionError("consulta não terminou")


def test_telas_abas_e_busca():
    c = cliente()
    pagina = c.get("/consulta")
    assert pagina.status_code == 200
    for texto in ("Nova consulta", "Carteira", "Fontes", "Cruzar agora", "Completar a consulta", "Ctrl K",
                  "Vira um código irreversível", 'accept=".kml,.geojson,.json"'):
        assert texto in pagina.text
    assert 'aria-current="page"' in pagina.text and 'method="post"' in pagina.text
    assert pagina.headers["cache-control"] == "no-store"
    for tela in ("/carteira", "/fontes"):
        r = c.get(tela)
        assert r.status_code == 200 and "Fazer uma nova consulta" in r.text
    assert c.get("/", follow_redirects=False).headers["location"] == "/consulta"
    assert c.get("/estatico/base.css").status_code == 200 and c.get("/estatico/console.js").status_code == 200


def test_so_aceita_host_local():
    app = criar_app(Falso())
    assert TestClient(app, base_url="http://127.0.0.1").get("/consulta").status_code == 200
    assert TestClient(app, base_url="http://exemplo.com").get("/consulta").status_code == 400


def test_main_sobe_so_em_127_0_0_1_com_porta(monkeypatch):
    chamadas = []
    monkeypatch.setattr(console_main.uvicorn, "run", lambda app, **kw: chamadas.append(kw))
    monkeypatch.setattr(console_main.relatorio, "configurar_log", lambda arquivo: None)
    assert console_main.main(["--porta", "9001"]) == 0
    assert chamadas == [{"host": "127.0.0.1", "port": 9001, "log_level": "warning"}]


@pytest.mark.parametrize("dados, trecho", [
    ({"car": "MG-3148103-XYZ"}, "fora do formato"),
    ({"car": "MG-314810-" + "A" * 32}, "fora do formato"),
    ({}, "informe o código do CAR"),
    ({"lat": "-18,9", "lon": "10"}, "longitude fora"),
    ({"car": COD, "commodity": "soja"}, "commodity"),
])
def test_entrada_conferida_no_servidor(dados, trecho):
    falso = Falso()
    r = cliente(falso).post("/api/consultas", json=dados)
    assert r.status_code == 422 and trecho in r.json()["erro"]
    assert falso.chamadas == []


def test_pedido_que_nao_e_json_e_recusado():
    c = cliente()
    assert c.post("/api/consultas", content="car=" + COD,
                  headers={"content-type": "application/x-www-form-urlencoded"}).status_code == 415
    assert c.post("/api/consultas", content="{", headers={"content-type": "application/json"}).status_code == 400


def test_consulta_mostra_as_seis_etapas_grava_ficha_e_execucao_avulsa():
    falso = Falso()
    c = cliente(falso)
    estado = cruzar(c, {"car": COD.lower(), "commodity": "café"})
    assert estado["estado"] == "pronto"
    assert falso.chamadas[0]["cod_imovel"] == COD and falso.chamadas[0]["documento"] is None
    assert [e["nome"] for e in estado["etapas"]] == list(consulta.ETAPAS)
    sicar = estado["etapas"][0]
    assert sicar["estado"] == "ok" and "imóvel localizado: 115,0 ha" in sicar["texto"]
    assert estado["situacao"] != "inconclusivo" and estado["motivo"] is None
    assert isinstance(estado["tempo_s"], float)

    pasta = config.SAIDAS / "console"
    assert (pasta / f"{COD}.html").is_file() and (pasta / f"{COD}.json").is_file()
    assert json.loads((pasta / f"{COD}.json").read_text())["consulta"]["commodity"] == "café"
    assert c.get(f"/fichas/{estado['ficha']}").status_code == 200

    execucao = lago.ler("diag.execucao")
    assert execucao[["tipo", "comando", "organizacao_id"]].values.tolist() == [["avulsa", "console", "demonstracao"]]
    assert lago.ler("diag.resultado_imovel")["cod_imovel"].tolist() == [COD]


def test_documento_nao_aparece_em_url_log_saida_nem_arquivo(caplog, tmp_path):
    caplog.set_level(logging.DEBUG)
    falso = Falso()
    c = cliente(falso)
    r = c.post("/api/consultas", json={"car": COD, "documento": CPF_VALIDO})
    ident = r.json()["id"]
    while (estado := c.get(f"/api/consultas/{ident}")).json()["estado"] == "rodando":
        time.sleep(0.02)
    assert falso.chamadas[0]["documento"] == DIGITOS  # chega ao pipeline, que pseudonimiza
    corpo = estado.json()
    assert corpo["documento_curto"] == pseudonimizar(pd.Series([DIGITOS]), carregar_chave()).iloc[0][:12]
    lista = next(e for e in corpo["etapas"] if e["nome"] == "Lista Suja")
    assert lista["estado"] == "ok"
    invalido = c.post("/api/consultas", json={"car": COD, "documento": "111.444.777-36"})
    assert invalido.status_code == 422

    textos = [r.text, estado.text, invalido.text, caplog.text, json.dumps(c.app.state.consultas.estados, default=str)]
    textos += [c.get(f"/fichas/{corpo['ficha']}").text, c.get(f"/fichas/{corpo['ficha_json']}").text]
    for texto in textos:
        assert DIGITOS not in texto and CPF_VALIDO not in texto and "11144477736" not in texto
    for arquivo in tmp_path.rglob("*"):
        if arquivo.is_file():
            dado = arquivo.read_bytes()
            assert DIGITOS.encode() not in dado and CPF_VALIDO.encode() not in dado, arquivo


def test_sicar_fora_do_ar_vira_inconclusivo_com_motivo_e_nunca_sem_ocorrencia():
    c = cliente(Falso(erro=requests.ConnectionError("sem rota")))
    estado = cruzar(c, {"car": COD})
    assert estado["estado"] == "pronto" and estado["situacao"] == "inconclusivo"
    assert "SICAR fora do ar" in estado["motivo"] and "Tente de novo" in estado["motivo"]
    assert estado["etapas"][0]["estado"] == "inco"
    assert {e["estado"] for e in estado["etapas"][1:]} == {"nao"}
    assert not any("sem ocorrência" in e["texto"] or "nenhum" in e["texto"] for e in estado["etapas"])
    assert (config.SAIDAS / "console" / estado["ficha"]).is_file()
    assert lago.ler("diag.resultado_imovel")["situacao"].tolist() == ["inconclusivo"]


def test_car_nao_localizado_vira_inconclusivo_com_motivo():
    ficha = prediagnostico.ficha_inconclusiva("CAR não localizado no SICAR")
    estado = cruzar(cliente(Falso(ficha=ficha)), {"car": COD})
    assert estado["situacao"] == "inconclusivo" and estado["motivo"] == "CAR não localizado no SICAR"


def test_area_de_producao_vai_como_texto_e_e_lida_pelo_leitor_da_carteira():
    falso = Falso()
    c = cliente(falso)
    kml = (DADOS / "talhao.kml").read_text(encoding="utf-8")
    assert cruzar(c, {"car": COD, "area": {"nome": "talhao.kml", "texto": kml}})["estado"] == "pronto"
    area = falso.chamadas[0]["area_producao"]
    assert area["motivo"] is None and area["geometria"].geom_type == "MultiPolygon" and area["arquivo"] == "talhao.kml"

    cruzar(c, {"car": COD, "area": {"nome": "quebrado.kml", "texto": "<kml><Document><Polygon>"}})
    assert falso.chamadas[1]["area_producao"]["motivo"]  # ilegível vira motivo na ficha, não derruba a consulta

    grande = {"car": COD, "area": {"nome": "a.geojson", "texto": "x" * (consulta.TAMANHO_MAXIMO_AREA + 1)}}
    assert c.post("/api/consultas", json=grande).status_code in (413, 422)
    assert c.post("/api/consultas", json={"car": COD, "area": {"nome": "a.shp", "texto": "x"}}).status_code == 422


def test_uma_consulta_por_vez():
    espera = threading.Event()
    c = cliente(Falso(espera=espera))
    assert c.post("/api/consultas", json={"car": COD}).status_code == 202
    assert c.post("/api/consultas", json={"car": COD}).status_code == 409
    espera.set()


@pytest.mark.parametrize("arquivo", ["..%2F..%2Fetc%2Fpasswd", "x.py", "nao_existe.html"])
def test_ficha_fora_da_pasta_nao_e_servida(arquivo):
    assert cliente().get(f"/fichas/{arquivo}").status_code == 404


def test_consulta_desconhecida():
    assert cliente().get("/api/consultas/" + "0" * 32).status_code == 404
