"""Chave de API por organização (ADR 0021): gerar, conferir o formato, criar, revogar e listar.

A chave tem o prefixo `agv_<ambiente>_` (identificável por varredura de segredo) e aparece uma única vez, na criação.
O banco guarda só o SHA-256 dela em `cad.chave_api`; quem confere é a função `cad.autenticar_chave_api` (migração 0004).

    AGROVALID_DATABASE_URL=postgresql://... python -m api.chaves criar --organizacao demonstracao
    python -m api.chaves listar --organizacao demonstracao
    python -m api.chaves revogar --chave-id <uuid>

Criar, revogar e listar são tarefas de administração: rodam como o dono das tabelas, nunca pela API.
"""

import argparse
import hashlib
import re
import secrets
import sys
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from api import config

VALIDADE_DIAS = 90
ESCOPO = "leitura"
BRASILIA = ZoneInfo("America/Sao_Paulo")
_FORMATO = re.compile(r"^agv_(" + "|".join(config.AMBIENTES) + r")_[A-Za-z0-9_-]{43}$")


def agora() -> datetime:
    """Horário de Brasília sem fuso, como o resto do banco."""
    return datetime.now(BRASILIA).replace(tzinfo=None, microsecond=0)


def gerar(ambiente: str) -> str:
    if ambiente not in config.AMBIENTES:
        raise ValueError(f"ambiente desconhecido: {ambiente}")
    return f"agv_{ambiente}_{secrets.token_urlsafe(32)}"


def ambiente_da_chave(chave: str) -> str | None:
    """Ambiente do prefixo, ou None se a chave não tem o formato esperado."""
    achado = _FORMATO.match(chave or "")
    return achado.group(1) if achado else None


def hash_da_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def identificador(chave: str) -> str:
    """Parte não secreta que aparece em listagens: o prefixo e 6 caracteres."""
    return chave[:len(f"agv_{ambiente_da_chave(chave)}_") + 6]


def criar(conn: psycopg.Connection, organizacao_id: str, ambiente: str, validade_dias: int = VALIDADE_DIAS,
          momento: datetime | None = None) -> tuple[str, str]:
    """Cria a chave e devolve (texto da chave, chave_id). O texto não fica guardado em lugar nenhum."""
    chave = gerar(ambiente)
    chave_id = str(uuid.uuid4())
    criada = momento or agora()
    conn.execute("INSERT INTO cad.chave_api (chave_id, organizacao_id, identificador, hash_sha256, escopo, criada_em, "
                 "expira_em) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (chave_id, organizacao_id, identificador(chave), hash_da_chave(chave), ESCOPO, criada,
                  criada + timedelta(days=validade_dias)))
    return chave, chave_id


def revogar(conn: psycopg.Connection, chave_id: str, momento: datetime | None = None) -> bool:
    cur = conn.execute("UPDATE cad.chave_api SET revogada_em = %s WHERE chave_id = %s AND revogada_em IS NULL",
                       (momento or agora(), chave_id))
    return cur.rowcount == 1


def listar(conn: psycopg.Connection, organizacao_id: str) -> list[dict]:
    """Chaves da organização, sem o hash."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT chave_id, identificador, escopo, criada_em, expira_em, revogada_em, ultimo_uso_em "
                           "FROM cad.chave_api WHERE organizacao_id = %s ORDER BY criada_em",
                           (organizacao_id,)).fetchall()


def principal(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m api.chaves", description="Chaves de API por organização (ADR 0021)")
    sub = p.add_subparsers(dest="acao", required=True)
    c = sub.add_parser("criar")
    c.add_argument("--organizacao", required=True)
    c.add_argument("--validade-dias", type=int, default=VALIDADE_DIAS)
    lst = sub.add_parser("listar")
    lst.add_argument("--organizacao", required=True)
    r = sub.add_parser("revogar")
    r.add_argument("--chave-id", required=True)
    args = p.parse_args(argv)
    cfg = config.carregar()
    if not cfg.url_banco:
        print(f"defina {config.VARIAVEL_URL}", file=sys.stderr)
        return 2
    with psycopg.connect(cfg.url_banco, autocommit=True) as conn:
        if args.acao == "criar":
            chave, chave_id = criar(conn, args.organizacao, cfg.ambiente, args.validade_dias)
            print(f"chave_id: {chave_id}\nchave (mostrada só agora; guarde no cofre): {chave}")
        elif args.acao == "listar":
            for linha in listar(conn, args.organizacao):
                print(" | ".join(f"{k}={v}" for k, v in linha.items()))
        else:
            if not revogar(conn, args.chave_id):
                print("chave não encontrada ou já revogada", file=sys.stderr)
                return 1
            print("revogada")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
