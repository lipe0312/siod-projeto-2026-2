"""Acesso ao banco por requisição (ADR 0020): uma transação, papel sem BYPASSRLS e organização só da transação.

Dentro de `sessao(conn, hash)`:
    SET LOCAL ROLE agrovalid_leitura          -- papel só com SELECT; a RLS vale
    SELECT cad.autenticar_chave_api(hash)    -- organização da chave válida (marca o último uso)
    SELECT set_config('app.organizacao_id', org, true)   -- = SET LOCAL, com o valor parametrizado

Nada disso é de sessão: no COMMIT ou no ROLLBACK o papel volta ao da conexão e a organização some, então a mesma
conexão pode servir à requisição seguinte, de outra organização, sem vazar (tests/test_api_banco.py prova).
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

PAPEL_LEITURA = "agrovalid_leitura"
TEMPO_CONEXAO_S = 5


class ChaveInvalida(Exception):
    """Chave inexistente, revogada, expirada ou de outro escopo. O motivo não vai ao cliente."""


def conectar(url: str) -> psycopg.Connection:
    # autocommit: cada `conn.transaction()` é um BEGIN/COMMIT explícito, sem transação aberta entre requisições.
    return psycopg.connect(url, autocommit=True, connect_timeout=TEMPO_CONEXAO_S)


@contextmanager
def sessao(conn: psycopg.Connection, hash_chave: str) -> Iterator[str]:
    """Transação da requisição, já com o papel de leitura e a organização da chave. Devolve o organizacao_id."""
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {PAPEL_LEITURA}")
        org = conn.execute("SELECT cad.autenticar_chave_api(%s)", (hash_chave,)).fetchone()[0]
        if not org:
            raise ChaveInvalida()
        conn.execute("SELECT set_config('app.organizacao_id', %s, true)", (org,))
        yield org


def saude(conn: psycopg.Connection) -> None:
    conn.execute("SELECT 1").fetchone()
