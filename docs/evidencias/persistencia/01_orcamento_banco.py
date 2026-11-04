"""Orçamento do banco: carrega o perfil lite e o completo num PostGIS local e mede o tamanho por tabela
(pg_total_relation_size: dados, índices e TOAST). Meta: lite <= 250 MB; o script falha se passar de 300 MB.

Roda da raiz, com o Postgres do banco/docker-compose.yml de pé (só local; recusa qualquer outro servidor):
    docker compose -f banco/docker-compose.yml up -d
    .venv/bin/python docs/evidencias/persistencia/01_orcamento_banco.py
A URL do servidor vem de AGROVALID_DATABASE_URL (padrão: localhost:5433). Cada perfil vai para um banco novo, apagado
no fim. Os dados vêm de lago.ler: do lago, ou do legado em data/processed enquanto a fonte não grava no lago.
Grava 01_orcamento_banco.json e 01_orcamento_banco.md ao lado do script.
"""
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from pipeline.armazenamento import banco, contratos, lago

PASTA = Path(__file__).resolve().parent
SERVIDOR = os.environ.get(banco.VARIAVEL_URL, "postgresql://agrovalid:agrovalid@localhost:5433/postgres")
META_LITE_MB, LIMITE_LITE_MB = 250, 300
LIMITE_SUPABASE_MB, LIMITE_NEON_MB = 500, 1024  # planos gratuitos (ADR 0011)

host = conninfo_to_dict(SERVIDOR).get("host", "localhost")
if host not in ("localhost", "127.0.0.1", "::1"):
    sys.exit(f"recusado: o orçamento só roda em Postgres local (host '{host}')")
logging.basicConfig(level=logging.WARNING, format="%(message)s")


def medir(perfil: str) -> dict:
    """Carrega o perfil num banco novo e devolve o resultado de banco.carregar com o tempo total."""
    nome = f"agrovalid_orcamento_{perfil}_{uuid.uuid4().hex[:6]}"
    with psycopg.connect(SERVIDOR, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    try:
        t0 = time.perf_counter()
        resultado = banco.carregar(make_conninfo(SERVIDOR, dbname=nome), perfil, aplicar_migracoes=True)
        resultado["segundos_total"] = round(time.perf_counter() - t0, 1)
    finally:
        with psycopg.connect(SERVIDOR, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))
    print(f"{perfil}: {resultado['total_bytes'] / 1e6:.1f} MB em {resultado['segundos_total']} s", flush=True)
    return resultado


def origem(tabela: str) -> str:
    return "lago" if lago.existe(tabela) else ("legado" if contratos.carregar(tabela).legado else "ausente")


def br(valor: float, casas: int = 1) -> str:
    """Número no formato brasileiro (1.551,4)."""
    return f"{valor:,.{casas}f}".translate(str.maketrans(",.", ".,"))


def tabela_md(resultado: dict) -> str:
    linhas = ["| Tabela | Origem | Linhas | MB | Segundos |", "|---|---|---:|---:|---:|"]
    for nome, d in sorted(resultado["tabelas"].items(), key=lambda kv: -kv[1]["bytes"]):
        n = "não carregada" if d["linhas"] is None else br(d["linhas"], 0)
        linhas.append(f"| `{nome}` | {origem(nome)} | {n} | {br(d['bytes'] / 1e6)} | {br(d['segundos'])} |")
    linhas.append(f"| **Total das tabelas** | | | **{br(resultado['total_bytes'] / 1e6)}** | "
                  f"{br(resultado['segundos_total'])} |")
    return "\n".join(linhas)


def main() -> int:
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    resultados = {p: medir(p) for p in ("lite", "completo")}
    lite_mb, completo_mb = (resultados[p]["total_bytes"] / 1e6 for p in ("lite", "completo"))
    descartadas = {t: d["descartadas_legado"] for r in resultados.values() for t, d in r["tabelas"].items()
                   if d["descartadas_legado"]}
    saida = {"gerado_em": agora, "meta_lite_mb": META_LITE_MB, "limite_lite_mb": LIMITE_LITE_MB,
             "lite_mb": round(lite_mb, 1), "completo_mb": round(completo_mb, 1),
             "cabe_supabase_500mb": lite_mb <= LIMITE_SUPABASE_MB, "cabe_neon_1gb": lite_mb <= LIMITE_NEON_MB,
             "linhas_do_legado_fora_da_chave": descartadas, "perfis": resultados}
    (PASTA / "01_orcamento_banco.json").write_text(json.dumps(saida, indent=2, ensure_ascii=False), encoding="utf-8")

    situacao = "dentro da meta" if lite_mb <= META_LITE_MB else (
        "acima da meta, abaixo do limite" if lite_mb <= LIMITE_LITE_MB else "ACIMA DO LIMITE")
    md = ["# Orçamento do banco: lite e completo", "",
          f"Medido em {agora} num PostGIS 17-3.5 local (`banco/docker-compose.yml`), com `python -m "
          "pipeline.armazenamento.banco`. Tamanho por `pg_total_relation_size` (dados, índices e TOAST). "
          "Cada perfil foi carregado num banco novo.", "",
          "| | MB | Meta | Supabase gratuito (500 MB) | Neon gratuito (1 GB por projeto) |", "|---|---:|---|---|---|",
          f"| **Lite** | **{br(lite_mb)}** | ≤ {META_LITE_MB} MB (limite {LIMITE_LITE_MB}): {situacao} | "
          f"{'cabe' if lite_mb <= LIMITE_SUPABASE_MB else 'não cabe'} | "
          f"{'cabe' if lite_mb <= LIMITE_NEON_MB else 'não cabe'} |",
          f"| **Completo** | **{br(completo_mb)}** | | {'cabe' if completo_mb <= LIMITE_SUPABASE_MB else 'não cabe'} | "
          f"{'cabe' if completo_mb <= LIMITE_NEON_MB else 'não cabe'} |", "",
          "## Perfil lite", "", tabela_md(resultados["lite"]), "", "## Perfil completo", "",
          tabela_md(resultados["completo"]), ""]
    if descartadas:
        md += ["## Linhas do legado fora da chave", "",
               "Enquanto a fonte não grava no lago, `lago.ler` entrega o arquivo antigo sem a validação do contrato. "
               "O carregador deixa de fora as linhas com chave nula ou repetida (o banco não as aceitaria):", ""]
        md += [f"- `{t}`: {n}" for t, n in descartadas.items()]
        md.append("")
    md += ["## Observações", "",
           "- \"Não carregada\": a tabela ainda não está no lago ou o legado não tem as colunas do contrato "
           "(`ref.lista_suja` espera `chave_registro`, que a fonte passa a gravar ao migrar para o lago). Ocupa só o "
           "espaço vazio (índices e catálogo).",
           "- `cad`, `diag`, `meta` e `geo.imovel_car` ainda não têm dados reais. Com uma carteira real, o lite cresce "
           "pouco: o peso está nas geometrias das camadas públicas.",
           "- O completo inclui o PRODES do Brasil inteiro, lido do legado `data/processed/inpe_prodes/`.", ""]
    (PASTA / "01_orcamento_banco.md").write_text("\n".join(md), encoding="utf-8")
    if lite_mb > LIMITE_LITE_MB:
        print(f"FALHA: lite com {lite_mb:.1f} MB passa do limite de {LIMITE_LITE_MB} MB", file=sys.stderr)
        return 1
    if lite_mb > META_LITE_MB:
        print(f"aviso: lite com {lite_mb:.1f} MB passa da meta de {META_LITE_MB} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
