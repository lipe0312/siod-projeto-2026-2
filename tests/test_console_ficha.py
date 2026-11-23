"""Tela da ficha no console (issue #33): veredito, plano de ação na ordem, o que falta com "Informar agora",
mapa e linha do tempo, rastreabilidade recolhida, estados de erro e inconclusivo, e nenhum documento em claro.
Sem rede: a ficha é sintética (diagnosticar de verdade sobre o fixture do pré-diagnóstico, ou um dict à mão)."""

import json
import re
from html import unescape

from fastapi.testclient import TestClient

from conftest import CPF_VALIDO
from console.servidor import criar_app
from console.telas import ficha as tela
from pipeline import config, plano_de_acao, prediagnostico
from pipeline.prediagnostico import ENCAMINHAMENTO, _criterio

COD = "MG-3148103-" + "A" * 32
DIGITOS = CPF_VALIDO.replace(".", "").replace("-", "")
CONSULTA = {"cod_imovel": COD, "documento_informado": True, "gerado_em": "2026-11-23 10:00:00",
            "commodity": "soja", "prodes": {"ultimo_ano_do_imovel": 2025, "origem": "lote",
                                             "verificado_em": "2026-11-20"}}
SVG = ('<svg class="mapa" viewBox="0 0 10 10"><rect width="5" height="5"/></svg> <div class="legenda">E1</div>'
       '<svg class="tempo" viewBox="0 0 10 10"><line x1="0" x2="9"/></svg> <div class="legenda">corte</div>')


def ficha_com_pendencia() -> dict:
    criterios = [
        _criterio("car", "CAR", 3, "indício", "Pendente", ENCAMINHAMENTO["car_pendente"], "SICAR"),
        _criterio("terra_indigena", "Sobreposição: terras indígenas", 5, "pendência", "TI X",
                  ENCAMINHAMENTO["terra_indigena"], "FUNAI"),
        _criterio("embargo", "Embargo IBAMA", 7, "pendência", "1 embargo(s) em 2024-05-02",
                  ENCAMINHAMENTO["embargo"], "IBAMA"),
        *prediagnostico._nao_verificados()]
    ficha = {"imovel": {"cod_imovel": COD, "municipio": "Juiz de Fora", "uf": "MG", "area_geom_ha": 120.5},
             "resultado": prediagnostico.resultado_geral(criterios), "criterios": criterios,
             "evidencias": {"embargos": [{"carga_id": "ibama_embargos:2026-11-02"}]},
             "geometria_car": "POLYGON((0 0,1 0,1 1,0 0))"}
    return {"consulta": dict(CONSULTA), **ficha, **plano_de_acao.montar(ficha, "soja"),
            "procedencia": [{"fonte": "SICAR (perímetro do CAR)", "como": "lote", "data": "2026-11-20",
                             "sha256": "ab" * 32, "arquivo": "sicar.gpkg"}]}


def ficha_inconclusiva() -> dict:
    return {"consulta": {"cod_imovel": None, "lat": -18.5, "lon": -44.1, "gerado_em": "2026-11-23 10:00:00",
                         "documento_informado": False},
            "imovel": {}, "geometria_car": None, "evidencias": {}, "procedencia": [],
            "resultado": {"situacao": "inconclusivo", "contagem": {"inconclusivo": 1}, "resumo": "sem CAR"},
            "criterios": [{"chave": "car", "criterio": "Imóvel no CAR", "situacao": "inconclusivo",
                           "evidencia": "nenhum CAR contém o ponto informado"}],
            "plano_de_acao": [], "o_que_falta": [
                {"entrada": "Localização do imóvel (código do CAR)", "destrava": "todos os critérios",
                 "criterios": ["Imóvel no CAR"], "quem": "o produtor", "onde": "recibo do CAR",
                 "situacoes": ["inconclusivo"]}]}


def ficha_sem_pendencia() -> dict:
    return {"consulta": dict(CONSULTA, documento_informado=False), "imovel": {"cod_imovel": COD},
            "geometria_car": {"type": "Polygon"}, "evidencias": {}, "procedencia": [],
            "resultado": {"situacao": "sem pendência nas fontes verificadas", "contagem": {"sem ocorrência": 3}},
            "criterios": [], "plano_de_acao": [], "o_que_falta": []}


def gravar(nome: str, ficha: dict, html: str | None = SVG) -> None:
    pasta = config.SAIDAS / "console"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{nome}.json").write_text(json.dumps(ficha, ensure_ascii=False, default=str), encoding="utf-8")
    if html is not None:
        (pasta / f"{nome}.html").write_text(html, encoding="utf-8")


def tela_de(nome: str) -> tuple[int, str]:
    r = TestClient(criar_app(lambda **_: {}, hosts=["testserver"])).get(f"/ficha/{nome}")
    return r.status_code, r.text


def sem_documento(texto: str) -> None:
    assert CPF_VALIDO not in texto and DIGITOS not in texto


def test_ficha_com_pendencia_mostra_os_blocos_na_ordem_e_sem_documento():
    ficha = ficha_com_pendencia()
    assert ficha["plano_de_acao"], "o fixture precisa gerar ao menos um cartão"
    gravar("f1", ficha)
    status, html = tela_de("f1")
    assert status == 200
    sem_documento(html)
    texto = unescape(html)
    # topo: identificação, veredito numa frase e a ressalva
    assert "MG-3148103-AAAAAAAA…AAAA" in texto and f'data-copiar="{COD}"' in texto
    assert f'<p class="veredito">{tela.veredito(ficha)}</p>' in texto
    assert "não é\n        atestado de conformidade" in texto
    assert "conforme" not in texto.replace("conformidade", "")
    # blocos na ordem da tela
    ordem = ['id="t-ficha"', 'id="plano"', 'id="falta"', 'id="mapa"', 'id="tempo"', 'id="rastreabilidade"']
    posicoes = [texto.index(b) for b in ordem]
    assert posicoes == sorted(posicoes)
    # cartões na ordem do plano_de_acao
    titulos = re.findall(r'<h3 id="acao-\d+-t">(.*?)</h3>', texto)
    assert titulos == [c["criterio"] for c in ficha["plano_de_acao"]]
    # mapa e linha do tempo vêm do HTML ao lado; rastreabilidade recolhida, com comando sem documento
    assert '<svg class="mapa"' in texto and '<svg class="tempo"' in texto
    assert '<details class="bloco rast" id="rastreabilidade">' in texto
    assert '--documento "<CPF ou CNPJ do proprietário>"' in texto
    assert "horário de Brasília" in texto and "+00:00" not in texto and "-03:00" not in texto


def test_o_que_falta_volta_para_a_consulta_com_o_car_preenchido():
    ficha = ficha_com_pendencia()
    ficha["o_que_falta"] = [{"entrada": "Documento do proprietário (CPF ou CNPJ)", "destrava": "Lista Suja",
                             "criterios": ["Lista Suja"], "quem": "o produtor", "onde": "cadastro",
                             "situacoes": ["não verificado"]}]
    gravar("f2", ficha)
    _, html = tela_de("f2")
    assert f'href="/consulta?car={COD}&amp;informar=documento"' in html
    assert "Informar agora" in html and "Não verificado" in html


def test_inconclusivo_mostra_o_motivo_e_nunca_sem_ocorrencia():
    gravar("f3", ficha_inconclusiva(), html=None)
    status, html = tela_de("f3")
    assert status == 200
    texto = unescape(html)
    assert "Por que ficou inconclusivo:" in texto and "nenhum CAR contém o ponto informado" in texto
    assert 'href="/consulta?lat=-18.5&lon=-44.1&informar=car"' in texto
    assert "Sem mapa: o CAR não foi localizado" in texto
    assert tela.veredito(ficha_inconclusiva()).startswith("Inconclusivo:")
    assert "Sem ocorrência" not in texto


def test_sem_pendencia_nao_vira_atestado():
    gravar("f4", ficha_sem_pendencia(), html=None)
    _, html = tela_de("f4")
    texto = unescape(html)
    assert "Sem pendência nas fontes verificadas." in texto
    assert "Isso não é atestado de conformidade" in texto
    assert "Mapa indisponível" in texto


def test_erros_de_ficha_inexistente_ilegivel_e_nome_invalido():
    assert tela_de("nao-existe")[0] == 404
    assert tela_de("..%2Fsegredo")[0] == 404
    pasta = config.SAIDAS / "console"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "quebrada.json").write_text("{nao é json", encoding="utf-8")
    status, html = tela_de("quebrada")
    assert status == 500 and "não é um JSON válido" in html
    (pasta / "outra.json").write_text('{"x": 1}', encoding="utf-8")
    assert tela_de("outra")[0] == 500


def test_documento_em_texto_livre_e_svg_perigoso_nao_passam():
    ficha = ficha_sem_pendencia()
    ficha["consulta"]["nome_area"] = f"Talhão {CPF_VALIDO}"
    gravar("f5", ficha, html='<svg class="mapa"><script>x()</script></svg> <div class="legenda"></div>')
    _, html = tela_de("f5")
    sem_documento(html)
    assert "<script>x()" not in html and "Mapa indisponível" in html
