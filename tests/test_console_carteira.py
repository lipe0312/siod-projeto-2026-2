"""Carteira no console (issue #34): página inicial, faixa de resumo, filtros, ordem da carteira, link da ficha da
pasta da carteira (sem path traversal), faixa "Fontes", "o que mudou", carteira vazia e nenhum documento em claro.
Sem rede: a carteira é gravada à mão no SAIDAS temporário, com as colunas da carteira de demonstração (#32); um teste
extra lê a demonstração real de data/saidas/ quando ela existe (só leitura)."""

import csv
import json
import re
import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import CPF_VALIDO
from console.servidor import criar_app
from console.telas import carteira as tela
from pipeline import config
from test_console_ficha import ficha_com_pendencia

DEMO_REAL = Path(__file__).resolve().parents[1] / "data" / "saidas" / "console" / "demonstracao"
COLUNAS = ["prioridade", "id_produtor", "cod_car", "uf", "municipio", "area_ha", "resultado", "pendencias", "indicios",
           "inconclusivos", "primeiro_encaminhamento", "mudou", "o_que_mudou", "documento_informado", "ficha",
           "problema_na_linha", "nome_area", "commodity"]
NOME_PEND = "MG-3148103-" + "A" * 32
NOME_SEM = "MG-3148103-" + "B" * 32
PROC = [{"fonte": "IBAMA, áreas embargadas (CSV)", "como": "lote", "data": "2026-11-03"},
        {"fonte": "INPE DETER (WFS, em lote)", "como": "lote", "data": "2026-11-03"},
        {"fonte": "INPE PRODES (lote, partição MG)", "como": "lote, verificação mensal", "data": "verificado em 2026-11-02"},
        {"fonte": "MTE, Cadastro de Empregadores (PDF)", "como": "lote", "data": "2026-11-02"},
        {"fonte": "FUNAI, terras indígenas (WFS, em lote)", "como": "lote", "data": "2026-11-02"},
        {"fonte": "SICAR (WFS)", "como": "sob demanda", "data": "2026-10-30"}]


def _linha(**kw) -> dict:
    return {c: "" for c in COLUNAS} | kw


def gravar_carteira(base: Path) -> Path:
    pasta = base / "demonstracao"
    (pasta / "fichas").mkdir(parents=True)
    pend = ficha_com_pendencia() | {"procedencia": PROC}
    sem = ficha_com_pendencia() | {"procedencia": PROC, "plano_de_acao": [],
                                   "resultado": {"situacao": "sem pendência nas fontes verificadas",
                                                 "contagem": {"não verificado": 3}}}
    (pasta / "fichas" / f"{NOME_PEND}.json").write_text(json.dumps(pend), encoding="utf-8")
    (pasta / "fichas" / f"{NOME_SEM}.json").write_text(json.dumps(sem), encoding="utf-8")
    linhas = [  # gravadas fora de ordem: a tela segue a coluna prioridade
        _linha(prioridade="3", id_produtor="CVC-06", resultado="sem pendência nas fontes verificadas",
               mudou="não", ficha=f"fichas/{NOME_SEM}.html", nome_area="Sítio Água Limpa", commodity="café",
               area_ha="89.2", municipio="Patrocínio", uf="MG"),
        _linha(prioridade="1", id_produtor="CVC-05", resultado="com pendência", pendencias="Embargo IBAMA",
               primeiro_encaminhamento=f"Consultar o termo de embargo do titular {CPF_VALIDO}", mudou="sim",
               o_que_mudou="Embargo IBAMA: sem ocorrência → pendência", ficha=f"fichas/{NOME_PEND}.html",
               nome_area="Fazenda Pantanal Alto", commodity="gado de corte", area_ha="274.8"),
        _linha(prioridade="2", id_produtor="CVC-07", resultado="inconclusivo", mudou="sem comparação",
               problema_na_linha="lat/lon fora do Brasil (conferir se não estão trocados)",
               nome_area="Sítio Coordenada Trocada", commodity="café"),
        _linha(prioridade="4", id_produtor="CVC-99", resultado="com indício", ficha="../../segredo.html",
               nome_area="Linha com ficha maliciosa", commodity="café", mudou="não"),
    ]
    with (pasta / "carteira.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        w.writerows(linhas)
    return pasta


def cliente() -> TestClient:
    return TestClient(criar_app(lambda **_: {}), base_url="http://127.0.0.1")


def test_raiz_abre_a_carteira_e_vazia_convida_a_consultar():
    c = cliente()
    assert c.get("/", follow_redirects=False).headers["location"] == "/carteira"
    r = c.get("/carteira")
    assert r.status_code == 200
    assert 'href="/consulta"' in r.text and "Nova consulta" in r.text
    assert "01_cooperativa_demonstracao.py" in r.text and "/estatico/carteira.css" in r.text


def test_carteira_resumo_filtros_ordem_e_link_da_ficha():
    gravar_carteira(config.SAIDAS / "console")
    r = cliente().get("/carteira")
    assert r.status_code == 200
    t = r.text
    # faixa de resumo que filtra, com contagem e área
    for grupo in ("pend", "inco", "indi", "sem"):
        assert f'data-filtro-grupo="{grupo}"' in t
    assert 'data-contar="1"' in t and "274,8 ha" in t
    # filtros e busca
    for alvo in ('data-filtro-commodity="cafe"', 'data-filtro-commodity="gado"', "data-filtro-falta",
                 'id="busca-carteira"'):
        assert alvo in t
    # uma linha por imóvel, na ordem da coluna prioridade
    ids = re.findall(r"<td data-rot=\"Imóvel\"><b>(CVC-\d+)</b>", t)
    assert ids == ["CVC-05", "CVC-07", "CVC-06", "CVC-99"]
    assert f'href="/ficha/{NOME_PEND}"' in t and "itens a tratar" in t and "critérios faltam" in t
    assert 'data-commodity="gado"' in t and 'data-falta="sim"' in t
    # inconclusivo com motivo; ficha com caminho estranho não vira link
    assert "lat/lon fora do Brasil" in t and "segredo" not in t
    # "sem pendência" com critério sem verificação nunca fica verde; nunca "conforme"
    linha_sem = t[t.index("CVC-06"):].split("</tr>")[0]
    assert "st-sem" not in linha_sem and "st-nao" in linha_sem
    assert 'class="cont st-sem"' not in t and "conforme" not in t.lower()
    # o que mudou (colunas mudou/o_que_mudou da carteira) e fontes com data
    assert "1 imóvel mudou desde a execução anterior" in t and "entre 3 comparados" in t
    assert "03/11/2026" in t and "02/11/2026" in t and "na hora" in t and "Lista Suja" in t
    # nenhum documento em claro
    digitos = re.sub(r"\D", "", CPF_VALIDO)
    assert CPF_VALIDO not in t and digitos not in re.sub(r"\D", "", t.replace("3148103", ""))


def test_rota_da_ficha_acha_a_ficha_da_carteira_sem_sair_da_pasta():
    pasta = gravar_carteira(config.SAIDAS / "console")
    (pasta / "segredo.json").write_text(json.dumps(ficha_com_pendencia()), encoding="utf-8")
    c = cliente()
    assert c.get(f"/ficha/{NOME_PEND}").status_code == 200
    for nome in ("..%2Fsegredo", "..%2F..%2Fdemonstracao%2Fsegredo", "segredo"):
        assert c.get(f"/ficha/{nome}").status_code == 404


def test_fontes_mostram_a_idade():
    html = tela._fontes([{"procedencia": PROC}], date(2026, 11, 23))
    assert "há 20 dias" in html and "há 21 dias" in html and "nesta carteira, 30/10/2026" in html


@pytest.mark.skipif(not (DEMO_REAL / "carteira.csv").is_file(), reason="demonstração não gerada nesta máquina")
def test_carteira_de_demonstracao_real():
    shutil.copytree(DEMO_REAL, config.SAIDAS / "console" / "demonstracao")
    r = cliente().get("/carteira")
    assert r.status_code == 200
    with (DEMO_REAL / "carteira.csv").open(encoding="utf-8") as f:
        assert r.text.count("<tr data-grupo=") == sum(1 for _ in csv.DictReader(f))
    assert "conforme" not in r.text.lower() and not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", r.text)
