"""API de leitura contra o Postgres local (pytest --banco): RLS por requisição, chave de API e nenhum documento.

    AGROVALID_PG_PORTA=5434 docker compose -f banco/docker-compose.yml up -d
    AGROVALID_TEST_URL=postgresql://agrovalid:agrovalid@localhost:5434/postgres pytest --banco tests/test_api_banco.py

Dado sintético: a organização `demonstracao` e uma segunda cooperativa, cada uma com duas execuções de um imóvel.
"""

import json
import os
import re
import uuid
from datetime import datetime, timedelta

import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import errors, sql
from psycopg.conninfo import make_conninfo

from api import app as api_app
from api import chaves, config
from conftest import CHAVE, CNPJ_VALIDO, CPF_VALIDO
from pipeline.armazenamento import banco
from pipeline.documentos import pseudonimizar, somente_digitos

pytestmark = pytest.mark.banco

SERVIDOR = os.environ.get("AGROVALID_TEST_URL", "postgresql://agrovalid:agrovalid@localhost:5434/postgres")
DEMO, OUTRA = "demonstracao", str(uuid.uuid4())
T1, T2 = datetime(2026, 10, 1, 3), datetime(2026, 11, 1, 3)
CARGA = "inpe_prodes:20261001T030000"
HASH_CPF = pseudonimizar(somente_digitos(pd.Series([CPF_VALIDO])), CHAVE).iloc[0]


@pytest.fixture
def url():
    nome = f"agrovalid_teste_api_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(SERVIDOR, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    endereco = make_conninfo(SERVIDOR, dbname=nome)
    try:
        with psycopg.connect(endereco, autocommit=True) as conn:
            banco.migrar(conn, "lite")
            _semear(conn)
        yield endereco
    finally:
        with psycopg.connect(SERVIDOR, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))


def _semear(conn: psycopg.Connection) -> None:
    """Como dono das tabelas (sem RLS): duas execuções por organização; o desmatamento muda na segunda."""
    conn.execute("INSERT INTO meta.carga (carga_id, fonte, iniciada_em, status) VALUES (%s, 'inpe_prodes', %s, 'ok')",
                 (CARGA, T1))
    conn.execute("INSERT INTO cad.organizacao (organizacao_id, nome, tipo, criado_em) VALUES (%s, 'Coop sintética', "
                 "'cooperativa', %s)", (OUTRA, T1))
    for org, sigla in ((DEMO, "DEMO"), (OUTRA, "OUTRA")):
        imovel_id = f"im-{sigla}"
        conn.execute("INSERT INTO cad.imovel (imovel_id, organizacao_id, cod_car, nome_area, criado_em) "
                     "VALUES (%s, %s, %s, %s, %s)", (imovel_id, org, f"BA-{sigla}", f"Fazenda {sigla}", T1))
        for momento, situacao in ((T1, "sem ocorrência"), (T2, "pendência")):
            ex, res = str(uuid.uuid4()), str(uuid.uuid4())
            ano_mes = f"{momento:%Y-%m}"
            conn.execute("INSERT INTO diag.execucao (execucao_id, organizacao_id, tipo, iniciada_em, terminada_em, "
                         "ano_mes) VALUES (%s, %s, 'carteira', %s, %s, %s)",
                         (ex, org, momento, momento + timedelta(minutes=5), ano_mes))
            conn.execute("INSERT INTO diag.execucao_carga (execucao_id, fonte, carga_id) VALUES (%s, 'inpe_prodes', "
                         "%s), (%s, 'mte_lista_suja', NULL)", (ex, CARGA, ex))
            conn.execute("INSERT INTO diag.resultado_imovel (resultado_id, execucao_id, organizacao_id, imovel_id, "
                         "cod_imovel, uf, situacao, prioridade, gerado_em, ano_mes) "
                         "VALUES (%s, %s, %s, %s, %s, 'BA', %s, 1, %s, %s)",
                         (res, ex, org, imovel_id, f"BA-{sigla}", situacao, momento, ano_mes))
            conn.execute("INSERT INTO diag.criterio (resultado_id, organizacao_id, chave, criterio, criterio_ab_s, "
                         "situacao, evidencia, ano_mes) VALUES "
                         "(%s, %s, 'desmatamento', 'Desmatamento', 1, %s, 'PRODES 2025', %s), "
                         "(%s, %s, 'lista_suja', 'Lista Suja', 4, 'inconclusivo', 'Lista indisponível', %s)",
                         (res, org, situacao, ano_mes, res, org, ano_mes))
            # O detalhe da evidência pode levar o documento: a API nunca o devolve.
            detalhes = json.dumps({"documento_hash": HASH_CPF, "cpf": CPF_VALIDO, "cnpj": CNPJ_VALIDO})
            conn.execute("INSERT INTO diag.evidencia (evidencia_id, resultado_id, organizacao_id, chave_criterio, tabela, "
                         "registro_id, carga_id, classe, inter_ha, detalhes_json, ano_mes) "
                         "VALUES (%s, %s, %s, 'desmatamento', 'ref.desmatamento_prodes', %s, %s, 'prodes', 2.5, %s, %s)",
                         (str(uuid.uuid4()), res, org, f"uuid-{sigla}", CARGA, detalhes, ano_mes))


@pytest.fixture
def chaves_das_orgs(url):
    with psycopg.connect(url, autocommit=True) as conn:
        return {org: chaves.criar(conn, org, "local")[0] for org in (DEMO, OUTRA)}


def _cliente(url: str, conexao=None) -> TestClient:
    app = api_app.criar_app(config.Configuracao(url_banco=url, ambiente="local"))
    if conexao is not None:
        def compartilhada():
            yield conexao
        app.dependency_overrides[api_app.conexao] = compartilhada
    return TestClient(app, raise_server_exceptions=False)


def _auth(chave: str) -> dict:
    return {"Authorization": f"Bearer {chave}"}


def _sem_documento(texto: str) -> None:
    digitos = re.sub(r"\D", "", CPF_VALIDO)
    for proibido in ("documento", "cpf", "cnpj", HASH_CPF, CPF_VALIDO, digitos, CNPJ_VALIDO):
        assert proibido not in texto.lower() if proibido.isalpha() else proibido not in texto, proibido
    assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)


# ---------------------------------------------------------------------------------------------------------------
# Papel e segurança por linha
# ---------------------------------------------------------------------------------------------------------------

def test_papel_de_leitura_so_le_e_nao_passa_por_cima_da_rls(url):
    with psycopg.connect(url, autocommit=True) as conn:
        assert conn.execute("SELECT rolbypassrls, rolcanlogin, rolsuper FROM pg_roles WHERE rolname = 'agrovalid_leitura'"
                            ).fetchone() == (False, False, False)
        for tabela in ("cad.imovel", "diag.resultado_imovel", "meta.carga"):
            assert conn.execute("SELECT has_table_privilege('agrovalid_leitura', %s, 'SELECT')", (tabela,)).fetchone()[0]
            for priv in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                assert not conn.execute("SELECT has_table_privilege('agrovalid_leitura', %s, %s)",
                                        (tabela, priv)).fetchone()[0], (tabela, priv)
        for papel in ("agrovalid_leitura", "agrovalid_app"):  # ninguém da aplicação lê o hash da chave
            assert not conn.execute("SELECT has_table_privilege(%s, 'cad.chave_api', 'SELECT')", (papel,)).fetchone()[0]
        assert not conn.execute("SELECT has_schema_privilege('agrovalid_leitura', 'ref', 'USAGE')").fetchone()[0]
        with conn.transaction():
            conn.execute("SET LOCAL ROLE agrovalid_leitura")
            with pytest.raises(errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute("SELECT * FROM cad.chave_api")
            with pytest.raises(errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute("UPDATE cad.imovel SET nome_area = 'x'")


def test_rls_demonstracao_nao_le_a_outra_organizacao(url):
    with psycopg.connect(url, autocommit=True) as conn, conn.transaction():
        conn.execute("SET LOCAL ROLE agrovalid_leitura")
        conn.execute("SELECT set_config('app.organizacao_id', %s, true)", (DEMO,))
        for tabela in ("cad.imovel", "diag.execucao", "diag.resultado_imovel", "diag.criterio", "diag.evidencia",
                       "diag.mudanca"):
            orgs = {o for (o,) in conn.execute(f"SELECT DISTINCT organizacao_id FROM {tabela}").fetchall()}
            assert orgs == {DEMO}, tabela
        assert conn.execute("SELECT count(*) FROM cad.organizacao").fetchone() == (0,)


# ---------------------------------------------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------------------------------------------

def test_cada_chave_le_so_a_propria_carteira_com_execucao_e_fontes(url, chaves_das_orgs):
    cliente = _cliente(url)
    for org, sigla in ((DEMO, "DEMO"), (OUTRA, "OUTRA")):
        r = cliente.get("/v1/carteira", headers=_auth(chaves_das_orgs[org]))
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert [i["cod_imovel"] for i in corpo["imoveis"]] == [f"BA-{sigla}"]  # a outra não aparece, nem a demonstração
        assert corpo["imoveis"][0]["situacao"] == "pendência"                 # a última execução
        assert corpo["imoveis"][0]["nome_area"] == f"Fazenda {sigla}"
        assert corpo["execucao"]["execucao_id"] == corpo["imoveis"][0]["execucao_id"]
        assert corpo["execucao"]["iniciada_em"] == T2.isoformat()
        fontes = {f["fonte"]: f for f in corpo["fontes"]}
        assert fontes["inpe_prodes"]["carga_id"] == CARGA and fontes["inpe_prodes"]["data"] == T1.isoformat()
        assert fontes["mte_lista_suja"]["carga_id"] is None  # fonte sem carga fica visível, não some
        _sem_documento(r.text)


def test_ficha_traz_criterios_e_evidencias_sem_documento_e_nao_abre_a_de_outra_org(url, chaves_das_orgs):
    cliente = _cliente(url)
    carteira_demo = cliente.get("/v1/carteira", headers=_auth(chaves_das_orgs[DEMO])).json()
    resultado_id = carteira_demo["imoveis"][0]["resultado_id"]
    r = cliente.get(f"/v1/fichas/{resultado_id}", headers=_auth(chaves_das_orgs[DEMO]))
    assert r.status_code == 200, r.text
    ficha = r.json()
    assert {c["chave"]: c["situacao"] for c in ficha["criterios"]} == {"desmatamento": "pendência",
                                                                         "lista_suja": "inconclusivo"}
    [ev] = ficha["evidencias"]
    assert (ev["tabela"], ev["registro_id"], ev["carga_id"], ev["inter_ha"]) == \
        ("ref.desmatamento_prodes", "uuid-DEMO", CARGA, 2.5)
    assert "detalhes_json" not in ev
    assert ficha["execucao"]["execucao_id"] == ficha["imovel"]["execucao_id"] and ficha["fontes"]
    _sem_documento(r.text)
    # A outra organização não abre a ficha da demonstração, nem sabendo o resultado_id.
    outra = cliente.get(f"/v1/fichas/{resultado_id}", headers=_auth(chaves_das_orgs[OUTRA]))
    assert outra.status_code == 404 and outra.json()["erro"] == "ficha não encontrada"
    assert cliente.get("/v1/fichas/nao-e-uuid", headers=_auth(chaves_das_orgs[DEMO])).status_code == 422


def test_mudancas_da_organizacao(url, chaves_das_orgs):
    cliente = _cliente(url)
    r = cliente.get("/v1/mudancas", headers=_auth(chaves_das_orgs[OUTRA]))
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert [(m["cod_imovel"], m["chave"], m["situacao_anterior"], m["situacao_atual"]) for m in corpo["mudancas"]] \
        == [("BA-OUTRA", "desmatamento", "sem ocorrência", "pendência")]
    assert corpo["mudancas"][0]["execucao_atual_id"] == corpo["execucao"]["execucao_id"]
    assert {f["fonte"] for f in corpo["fontes"]} == {"inpe_prodes", "mte_lista_suja"}
    _sem_documento(r.text)


def test_organizacao_sem_execucao_recebe_404(url):
    with psycopg.connect(url, autocommit=True) as conn:
        chave, _ = chaves.criar(conn, str(uuid.uuid4()), "local")
    cliente = _cliente(url)
    for caminho in ("/v1/carteira", "/v1/mudancas"):
        assert cliente.get(caminho, headers=_auth(chave)).status_code == 404


def test_saude_testa_o_banco(url):
    r = _cliente(url).get("/saude")
    assert r.status_code == 200 and r.json() == {"banco": "ok"}


# ---------------------------------------------------------------------------------------------------------------
# A organização não vaza entre requisições na mesma conexão
# ---------------------------------------------------------------------------------------------------------------

def test_consulta_da_rota_roda_com_o_papel_de_leitura_e_a_organizacao_da_chave(url, chaves_das_orgs, monkeypatch):
    visto = []

    def espiar(conn):
        visto.append(conn.execute("SELECT current_user, current_setting('app.organizacao_id', true), "
                                  "current_setting('transaction_isolation')").fetchone())
        return None

    monkeypatch.setattr(api_app.consultas, "carteira", espiar)
    assert _cliente(url).get("/v1/carteira", headers=_auth(chaves_das_orgs[OUTRA])).status_code == 404
    assert visto == [("agrovalid_leitura", OUTRA, "read committed")]


def test_mesma_conexao_serve_duas_organizacoes_sem_vazar(url, chaves_das_orgs):
    with psycopg.connect(url, autocommit=True) as conn:
        dono = conn.execute("SELECT current_user").fetchone()[0]
        cliente = _cliente(url, conexao=conn)
        a = cliente.get("/v1/carteira", headers=_auth(chaves_das_orgs[DEMO])).json()
        b = cliente.get("/v1/carteira", headers=_auth(chaves_das_orgs[OUTRA])).json()
        assert [i["cod_imovel"] for i in a["imoveis"]] == ["BA-DEMO"]
        assert [i["cod_imovel"] for i in b["imoveis"]] == ["BA-OUTRA"]
        # Requisição com chave inválida na mesma conexão: nada de B fica para ela.
        assert cliente.get("/v1/carteira", headers=_auth(chaves.gerar("local"))).status_code == 401
        # Depois do COMMIT o papel e a organização voltaram ao que eram: SET LOCAL não sobrevive à transação.
        assert conn.execute("SELECT current_user").fetchone()[0] == dono
        assert conn.execute("SELECT coalesce(current_setting('app.organizacao_id', true), '')").fetchone()[0] == ""
        assert not conn.info.transaction_status  # nenhuma transação aberta entre requisições (IDLE = 0)
        with conn.transaction():
            conn.execute("SET LOCAL ROLE agrovalid_leitura")
            assert conn.execute("SELECT count(*) FROM cad.imovel").fetchone() == (0,)
            assert conn.execute("SELECT count(*) FROM diag.resultado_imovel WHERE organizacao_id = %s",
                                (OUTRA,)).fetchone() == (0,)


# ---------------------------------------------------------------------------------------------------------------
# Chave de API: validade, revogação, último uso
# ---------------------------------------------------------------------------------------------------------------

def test_chave_expirada_revogada_ou_de_outro_ambiente_da_401(url):
    with psycopg.connect(url, autocommit=True) as conn:
        expirada, _ = chaves.criar(conn, OUTRA, "local", momento=chaves.agora() - timedelta(days=91))
        revogada, revogada_id = chaves.criar(conn, OUTRA, "local")
        assert chaves.revogar(conn, revogada_id) and not chaves.revogar(conn, revogada_id)
        de_producao, _ = chaves.criar(conn, OUTRA, "producao")
    cliente = _cliente(url)
    for chave in (expirada, revogada, de_producao):
        r = cliente.get("/v1/carteira", headers=_auth(chave))
        assert r.status_code == 401 and r.json()["erro"] == "chave de API ausente ou inválida"


def test_so_o_hash_fica_no_banco_e_o_ultimo_uso_e_marcado(url):
    with psycopg.connect(url, autocommit=True) as conn:
        chave, chave_id = chaves.criar(conn, OUTRA, "local")
        linha = conn.execute("SELECT identificador, hash_sha256, escopo, expira_em - criada_em, ultimo_uso_em "
                             "FROM cad.chave_api WHERE chave_id = %s", (chave_id,)).fetchone()
        assert linha[:4] == (chave[:16], chaves.hash_da_chave(chave), "leitura", timedelta(days=90))
        assert linha[4] is None
        texto = str(conn.execute("SELECT * FROM cad.chave_api").fetchall())
        assert chave not in texto and chave[16:] not in texto
        _cliente(url).get("/v1/carteira", headers=_auth(chave))
        uso = conn.execute("SELECT ultimo_uso_em FROM cad.chave_api WHERE chave_id = %s", (chave_id,)).fetchone()[0]
        assert uso is not None and abs(uso - chaves.agora()) < timedelta(minutes=1)  # Brasília, sem fuso
        listadas = chaves.listar(conn, OUTRA)
        assert [c["chave_id"] for c in listadas] == [chave_id] and "hash_sha256" not in listadas[0]
