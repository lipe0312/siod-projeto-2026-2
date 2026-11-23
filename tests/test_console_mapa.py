"""Mapa de satélite da ficha (issue #35): o GeoJSON das camadas (#31) vai embutido e escapado na página, sem ele a
tela fica no SVG, camadas não verificadas aparecem listadas, a CSP só libera a imagem da EOX e o Leaflet é servido
pelo próprio console. Offline: nenhum tile é pedido (o teste só lê o HTML)."""

import json
import re

from fastapi.testclient import TestClient

from conftest import CPF_VALIDO
from console.servidor import ESTATICO, criar_app
from console.telas import ficha as tela
from pipeline import config
from test_console_ficha import DIGITOS, ficha_com_pendencia, gravar

QUADRADO = {"type": "Polygon", "coordinates": [[[-44, -18], [-43.99, -18], [-43.99, -17.99], [-44, -18]]]}


def camadas(fonte_alerta: str = "INPE DETER") -> dict:
    feicao = lambda camada, rotulo, fonte, data=None: {  # noqa: E731
        "type": "Feature", "geometry": QUADRADO,
        "properties": {"camada": camada, "rotulo": rotulo, "situacao": "principal", "data_imagem": data,
                       "fonte": fonte, "ha": 3.7}}
    return {"type": "FeatureCollection", "name": "camadas_da_ficha",
            "camadas_nao_verificadas": [{"camada": "quilombola", "motivo": "camada ausente da ficha: fonte não "
                                                                          "carregada ou sem geometria"}],
            "features": [feicao("car", "CAR", "SICAR"), feicao("alerta_deter", "A1", fonte_alerta, "2025-08-28"),
                         feicao("embargo", "E1", "IBAMA")]}


def gravar_camadas(nome: str, dados) -> None:
    texto = dados if isinstance(dados, str) else json.dumps(dados, ensure_ascii=False)
    (config.SAIDAS / "console" / f"{nome}.camadas.geojson").write_text(texto, encoding="utf-8")


def cliente() -> TestClient:
    return TestClient(criar_app(lambda **_: {}, hosts=["testserver"]))


def embutido(texto: str) -> dict:
    m = re.search(r'<script type="application/json" id="camadas-dados">(.*?)</script>', texto, re.DOTALL)
    assert m, "GeoJSON não embutido"
    return json.loads(m[1])


def test_camadas_embutidas_escapadas_e_sem_documento():
    gravar("m1", ficha_com_pendencia())
    gravar_camadas("m1", camadas(f"</script><script>alert(1)</script> {CPF_VALIDO}"))
    r = cliente().get("/ficha/m1")
    assert r.status_code == 200
    assert "<script>alert(1)" not in r.text and CPF_VALIDO not in r.text and DIGITOS not in r.text
    dados = embutido(r.text)
    assert [f["properties"]["rotulo"] for f in dados["features"]] == ["CAR", "A1", "E1"]
    assert dados["features"][1]["properties"]["fonte"].startswith("</script>")  # volta íntegro no navegador
    # bloco de satélite: antes 2020 e depois o mosaico recente, atribuição EOX, camadas com rótulo, Leaflet local
    assert 'data-antes="2020"' in r.text and f'data-depois="{tela.ANO_DEPOIS}"' in r.text
    assert "Sentinel-2 cloudless</a> by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2020)" in r.text
    assert 'data-camada="alerta_deter"' in r.text and '<span class=mono>A1</span>' in r.text
    assert '/estatico/leaflet/leaflet.js' in r.text and '/estatico/mapa.js' in r.text
    assert not re.search(r"<script[^>]+src=\"https?:|<link[^>]+href=\"https?:", r.text)  # nenhuma CDN
    # o SVG continua na página (impressão e sem rede) e o "ver no mapa" sabe as letras da evidência
    assert '<svg class="mapa"' in r.text and 'data-rot="E"' in r.text
    # camada não verificada listada, nunca "sem ocorrência"
    assert "Fora do mapa (não verificado)" in r.text and "Território quilombola" in r.text


def test_sem_geojson_ou_geojson_invalido_fica_no_svg():
    gravar("m2", ficha_com_pendencia())
    for conteudo in (None, "{não é json", json.dumps({"type": "FeatureCollection", "features": []}),
                     json.dumps({"type": "Feature"})):
        if conteudo is not None:
            gravar_camadas("m2", conteudo)
        texto = cliente().get("/ficha/m2").text
        assert 'id="camadas-dados"' not in texto and "data-sat" not in texto and "leaflet.js" not in texto
        assert '<svg class="mapa"' in texto


def test_ficha_sem_car_nao_monta_satelite_mesmo_com_geojson():
    f = ficha_com_pendencia()
    f["geometria_car"] = None
    gravar("m3", f)
    gravar_camadas("m3", camadas())
    assert "data-sat" not in cliente().get("/ficha/m3").text


def test_csp_libera_so_a_imagem_da_eox_e_leaflet_e_servido_localmente():
    c = cliente()
    gravar("m4", ficha_com_pendencia())
    csp = c.get("/ficha/m4").headers["content-security-policy"]
    assert "img-src 'self' data: https://tiles.maps.eox.at;" in csp
    assert "default-src 'self'" in csp and "unsafe-eval" not in csp and "script-src" not in csp
    for arquivo in ("leaflet/leaflet.js", "leaflet/leaflet.css", "leaflet/LICENSE", "mapa.js"):
        assert c.get(f"/estatico/{arquivo}").status_code == 200, arquivo
    assert "Leaflet 1.9.4" in (ESTATICO / "leaflet" / "leaflet.js").read_text(encoding="utf-8")[:200]
    js = (ESTATICO / "mapa.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "s2cloudless-{ano}_3857" in js
