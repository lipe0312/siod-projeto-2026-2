"""Banco: migração, carga, segurança por linha e visões, num Postgres/PostGIS local (pytest --banco).

    docker compose -f banco/docker-compose.yml up -d
    pytest --banco tests/test_banco.py

Cada teste usa um banco novo, criado e apagado no mesmo servidor. O servidor vem de AGROVALID_TEST_URL (padrão: o do
docker-compose, na porta 5433).
"""

import itertools
import os
import uuid
from datetime import datetime

import pandas as pd
import psycopg
import pytest
from psycopg import errors, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from pipeline import config
from pipeline.armazenamento import banco, contratos, lago

pytestmark = pytest.mark.banco

SERVIDOR = os.environ.get("AGROVALID_TEST_URL", "postgresql://agrovalid:agrovalid@localhost:5433/postgres")
POLIGONO = "POLYGON((-47 -15, -46 -15, -46 -14, -47 -14, -47 -15))"
ORG_A, ORG_B = str(uuid.uuid4()), str(uuid.uuid4())
T1, T2 = datetime(2026, 10, 1, 3), datetime(2026, 11, 1, 3)


@pytest.fixture
def novo_banco():
    """Fábrica de bancos descartáveis: devolve a URL e apaga todos no fim."""
    criados = []

    def criar() -> str:
        nome = f"agrovalid_teste_{uuid.uuid4().hex[:8]}"
        with psycopg.connect(SERVIDOR, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
        criados.append(nome)
        return make_conninfo(SERVIDOR, dbname=nome)

    yield criar
    with psycopg.connect(SERVIDOR, autocommit=True) as conn:
        for nome in criados:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))


@pytest.fixture
def lago_sintetico(tmp_path, monkeypatch):
    """Lago vazio em tmp_path e sem o legado: só existe o que o teste gravar."""
    monkeypatch.setattr(config, "LAGO", tmp_path / "lago")
    monkeypatch.setattr(config, "DADOS_PROCESSADOS", tmp_path / "processed")


def linhas(tabela: str, *sobrescritas: dict) -> pd.DataFrame:
    """Linhas sintéticas que cumprem o contrato; cada dict muda colunas de uma linha."""
    c = contratos.carregar(tabela)
    padrao = {"texto": "x", "inteiro": 1, "decimal": 1.5, "logico": True, "json": "{}", "geometria": POLIGONO,
              "data_hora": pd.Timestamp("2026-10-01 12:00:00"), "data": pd.Timestamp("2026-10-01")}
    contador = itertools.count(1)
    registros = []
    for mudanca in sobrescritas:
        n = next(contador)
        r = {col.nome: padrao[col.tipo] for col in c.colunas}
        r.update({col.nome: f"{col.nome}-{n}" for col in c.colunas if col.nome in c.chave and col.tipo == "texto"})
        r.update(mudanca)
        registros.append(r)
    df = pd.DataFrame(registros, columns=c.nomes)
    for col in c.colunas:
        if col.tipo == "inteiro":
            df[col.nome] = df[col.nome].astype("Int64")
        if col.tipo == "data_hora":
            df[col.nome] = pd.to_datetime(df[col.nome])
    return df


def gravar(tabela: str, df: pd.DataFrame, momento: datetime = T1) -> None:
    lago.gravar(tabela, df, carga_id=f"teste:{momento:%Y%m%dT%H%M%S}", momento=momento)


def consultar(url: str, consulta: str, params=None):
    with psycopg.connect(url, autocommit=True) as conn:
        return conn.execute(consulta, params).fetchall()


# ---------------------------------------------------------------------------------------------------------------
# Migração e carga
# ---------------------------------------------------------------------------------------------------------------

def test_migrar_e_carregar_dados_sinteticos(novo_banco, lago_sintetico):
    url = novo_banco()
    fuso = pd.Timestamp("2026-01-01 12:00:00", tz="America/Bahia")  # UTC-3
    gravar("ref.terra_indigena", linhas("ref.terra_indigena", {}, {"geometria_wkt": None}))
    gravar("ref.embargo_ibama", linhas("ref.embargo_ibama", {"id_embargo": "e1", "data_embargo": fuso, "situacao": "ativo",
                                                              "descricao_infracao": "linha\ncom \"aspas\", vírgula e \\N"},
                                        {"id_embargo": "e2", "data_embargo": fuso}))
    gravar("ref.embargo_ibama", linhas("ref.embargo_ibama", {"id_embargo": "e1", "data_embargo": fuso, "situacao": "levantado",
                                                              "descricao_infracao": "x"}, {"id_embargo": "e2", "data_embargo": fuso}), T2)
    gravar("geo.imovel_car", linhas("geo.imovel_car", {"cod_imovel": "BA-1"}))
    gravar("geo.imovel_car", linhas("geo.imovel_car", {"cod_imovel": "BA-1", "condicao": "mudou"}), T2)

    resultado = banco.carregar(url, "completo", aplicar_migracoes=True)

    assert resultado["tabelas"]["ref.terra_indigena"]["linhas"] == 2
    assert resultado["tabelas"]["ref.embargo_ibama"]["linhas"] == 3          # todas as versões (e1 tem duas)
    assert resultado["tabelas"]["cad.organizacao"]["linhas"] is None         # fora do lago: pulada
    assert resultado["total_bytes"] > 0
    assert consultar(url, "SELECT nome FROM meta.migracao ORDER BY nome") == [
        (n,) for n in sorted(a.name for a in banco.arquivos_de_migracao("completo"))]
    # Geometria como EWKT no SRID do contrato; nula quando a linha não tem.
    assert consultar(url, "SELECT count(*), count(geometria), min(ST_SRID(geometria)) FROM ref.terra_indigena") \
        == [(2, 1, 4674)]
    # Embargo no completo ganha a geometria; fuso vira UTC sem fuso.
    assert consultar(url, "SELECT count(geometria) FROM ref.embargo_ibama") == [(3,)]
    assert consultar(url, "SELECT data_embargo FROM ref.embargo_ibama WHERE id_embargo = 'e1' AND valido_ate IS NULL") \
        == [(datetime(2026, 1, 1, 15),)]
    assert consultar(url, "SELECT descricao_infracao FROM ref.embargo_ibama WHERE situacao = 'ativo' AND id_embargo = 'e1'") \
        == [('linha\ncom "aspas", vírgula e \\N',)]
    # Visões do estado vigente.
    assert consultar(url, "SELECT id_embargo, situacao FROM ref.embargo_ibama_vigente ORDER BY id_embargo") \
        == [("e1", "levantado"), ("e2", "x")]
    assert consultar(url, "SELECT condicao FROM geo.imovel_car_vigente") == [("mudou",)]
    assert consultar(url, "SELECT count(*) FROM geo.imovel_car") == [(2,)]
    # Idempotente: recarregar não duplica.
    banco.carregar(url, "completo")
    assert consultar(url, "SELECT count(*) FROM ref.embargo_ibama") == [(3,)]
    assert consultar(url, "SELECT count(*) FROM ref.terra_indigena") == [(2,)]


def test_perfil_lite_nao_cria_o_que_e_do_completo(novo_banco, lago_sintetico):
    url = novo_banco()
    gravar("ref.embargo_ibama", linhas("ref.embargo_ibama", {"id_embargo": "e1"}))
    gravar("ref.alerta_deter", linhas("ref.alerta_deter", {}))
    resultado = banco.carregar(url, "lite", aplicar_migracoes=True)
    assert "ref.alerta_deter" not in resultado["tabelas"]
    assert consultar(url, "SELECT to_regclass('ref.alerta_deter') IS NULL") == [(True,)]
    assert consultar(url, "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'ref' "
                          "AND table_name = 'embargo_ibama' AND column_name = 'geometria'") == [(0,)]
    assert consultar(url, "SELECT count(*) FROM ref.embargo_ibama") == [(1,)]
    # Depois, o completo acrescenta a geometria e recria a visão.
    gravar("ref.embargo_ibama", linhas("ref.embargo_ibama", {"id_embargo": "e1"}), T2)
    banco.carregar(url, "completo", aplicar_migracoes=True, tabelas=["ref.embargo_ibama"])
    assert consultar(url, "SELECT count(geometria) FROM ref.embargo_ibama_vigente") == [(1,)]


def test_carga_sem_migracao_e_tabela_desconhecida_dao_erro_claro(novo_banco, lago_sintetico):
    url = novo_banco()
    with pytest.raises(banco.ErroDeCarga, match="--migrar"):
        banco.carregar(url, "lite")
    with pytest.raises(banco.ErroDeCarga, match="fora do perfil"):
        banco.carregar(url, "lite", True, ["ref.desmatamento_prodes"])


# ---------------------------------------------------------------------------------------------------------------
# Segurança por linha e visão de mudanças
# ---------------------------------------------------------------------------------------------------------------

@pytest.fixture
def banco_com_carteiras(novo_banco, lago_sintetico):
    url = novo_banco()
    banco.carregar(url, "lite", aplicar_migracoes=True, tabelas=["meta"])
    with psycopg.connect(url, autocommit=True) as conn:
        for org in (ORG_A, ORG_B):
            conn.execute("INSERT INTO cad.organizacao (organizacao_id, nome, tipo, criado_em) "
                         "VALUES (%s, %s, 'cooperativa', now())", (org, f"coop {org[:4]}"))
            conn.execute("INSERT INTO cad.imovel (imovel_id, organizacao_id, cod_car, criado_em) "
                         "VALUES (%s, %s, %s, now())", (f"im-{org}", org, f"BA-{org[:4]}"))
        conn.execute("INSERT INTO diag.execucao (execucao_id, organizacao_id, tipo, iniciada_em, ano_mes) VALUES "
                     "('ex-a', %s, 'carteira', now(), '2026-11'), ('ex-demo', NULL, 'demonstracao', now(), '2026-11')",
                     (ORG_A,))
        conn.execute("INSERT INTO diag.execucao_carga (execucao_id, fonte) VALUES ('ex-a', 'inpe_prodes'), "
                     "('ex-demo', 'inpe_prodes')")
    return url


def como_app(url: str, organizacao: str | None):
    conn = psycopg.connect(url, autocommit=True)  # sem transação: o erro não desfaz o SET ROLE
    conn.execute("SET ROLE agrovalid_app")
    if organizacao:
        conn.execute("SELECT set_config('app.organizacao_id', %s, false)", (organizacao,))
    return conn


def test_rls_uma_organizacao_nao_ve_a_carteira_da_outra(banco_com_carteiras):
    url = banco_com_carteiras
    with como_app(url, ORG_A) as a:
        assert a.execute("SELECT organizacao_id FROM cad.imovel").fetchall() == [(ORG_A,)]
        assert a.execute("SELECT organizacao_id FROM cad.organizacao").fetchall() == [(ORG_A,)]
    with como_app(url, ORG_B) as b:
        assert b.execute("SELECT organizacao_id FROM cad.imovel").fetchall() == [(ORG_B,)]
        # Demonstração (organizacao_id nulo) é de todos; a execução de A, não.
        assert b.execute("SELECT execucao_id FROM diag.execucao ORDER BY 1").fetchall() == [("ex-demo",)]
        # diag.execucao_carga não tem organizacao_id e segue a execução.
        assert b.execute("SELECT execucao_id FROM diag.execucao_carga").fetchall() == [("ex-demo",)]
    with como_app(url, None) as sem:  # sem a variável, nada passa
        assert sem.execute("SELECT count(*) FROM cad.imovel").fetchone() == (0,)
        assert sem.execute("SELECT count(*) FROM diag.execucao").fetchone() == (1,)  # só a demonstração
    # O dono (quem carrega) não é afetado.
    assert consultar(url, "SELECT count(*) FROM cad.imovel") == [(2,)]


def test_rls_papel_so_le_e_insere_na_propria_organizacao(banco_com_carteiras):
    url = banco_com_carteiras
    with como_app(url, ORG_A) as a:
        a.execute("INSERT INTO cad.imovel (imovel_id, organizacao_id, criado_em) VALUES ('novo', %s, now())", (ORG_A,))
        with pytest.raises(errors.InsufficientPrivilege):  # linha de outra organização
            a.execute("INSERT INTO cad.imovel (imovel_id, organizacao_id, criado_em) VALUES ('x', %s, now())", (ORG_B,))
    with como_app(url, ORG_A) as a:
        with pytest.raises(errors.InsufficientPrivilege):  # sem UPDATE
            a.execute("UPDATE cad.imovel SET cod_car = 'z'")
        with pytest.raises(errors.InsufficientPrivilege):  # sem DELETE
            a.execute("DELETE FROM cad.imovel")
        with pytest.raises(errors.InsufficientPrivilege):  # sem escrita em ref
            a.execute("DELETE FROM ref.lista_suja")
        assert a.execute("SELECT count(*) FROM ref.lista_suja").fetchone() == (0,)


def test_mudanca_acusa_o_criterio_que_mudou_entre_as_duas_ultimas_execucoes(banco_com_carteiras):
    url = banco_com_carteiras
    resultados = [  # (resultado, execução, imóvel, quando, situação do critério "embargo", do "prodes")
        ("r1", "e1", ORG_A, "CAR-1", "2026-09-01", "sem_ocorrencia", "sem_ocorrencia"),   # mais antiga: fora da comparação
        ("r2", "e2", ORG_A, "CAR-1", "2026-10-01", "indicio", "sem_ocorrencia"),
        ("r3", "e3", ORG_A, "CAR-1", "2026-11-01", "pendencia", "sem_ocorrencia"),
        ("r4", "e2", ORG_A, "CAR-2", "2026-10-01", "sem_ocorrencia", "sem_ocorrencia"),   # sem mudança
        ("r5", "e3", ORG_A, "CAR-2", "2026-11-01", "sem_ocorrencia", "sem_ocorrencia"),
        ("r6", "e3", ORG_B, "CAR-1", "2026-11-01", "pendencia", "pendencia"),             # outra org, uma execução só
        ("r7", "e3", ORG_A, "CAR-3", "2026-11-01", "pendencia", "pendencia"),             # uma execução só
    ]
    with psycopg.connect(url, autocommit=True) as conn:
        for rid, exe, org, car, quando, embargo, prodes in resultados:
            conn.execute("INSERT INTO diag.resultado_imovel (resultado_id, execucao_id, organizacao_id, cod_imovel, "
                         "situacao, gerado_em, ano_mes) VALUES (%s, %s, %s, %s, 'x', %s, %s)",
                         (rid, exe, org, car, quando, quando[:7]))
            for chave, situacao in (("embargo", embargo), ("prodes", prodes)):
                conn.execute("INSERT INTO diag.criterio (resultado_id, organizacao_id, chave, criterio, situacao, ano_mes) "
                             "VALUES (%s, %s, %s, %s, %s, %s)", (rid, org, chave, chave.upper(), situacao, quando[:7]))
    esperado = [(ORG_A, "CAR-1", "embargo", "indicio", "pendencia", datetime(2026, 10, 1), datetime(2026, 11, 1))]
    consulta = ("SELECT organizacao_id, cod_imovel, chave, situacao_anterior, situacao_atual, data_anterior, data_atual "
                "FROM diag.mudanca ORDER BY 1, 2, 3")
    assert consultar(url, consulta) == esperado
    with como_app(url, ORG_A) as a:
        assert a.execute(consulta).fetchall() == esperado
    with como_app(url, ORG_B) as b:  # a visão obedece à segurança por linha de quem consulta
        assert b.execute(consulta).fetchall() == []
