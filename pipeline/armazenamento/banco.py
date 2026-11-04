"""Carrega o lago no Postgres/PostGIS (ADR 0011 e 0017). O banco é descartável: é uma cópia refeita do lago.

    AGROVALID_DATABASE_URL=postgresql://... python -m pipeline.armazenamento.banco --perfil lite --migrar
    python -m pipeline.armazenamento.banco --perfil completo --url postgresql://... --tabelas ref.embargo_ibama

Cada tabela é recarregada por inteiro e de forma idempotente, numa transação própria: TRUNCATE + COPY. O que entra:
fotografia só a versão vigente; validade, acréscimo, por consulta e registro todo o histórico. A geometria vai como
EWKT (`SRID=4674;...`). Tabela que ainda não está no lago (cad e diag vazios) é pulada com aviso. Enquanto uma fonte
não grava no lago, `lago.ler` cai no arquivo legado, sem as colunas de controle: `carga_id` vira "legado" e a
versão começa agora (`valido_de` e `consultado_em`).
"""

import argparse
import hashlib
import io
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from pipeline.armazenamento import contratos, ddl, lago
from pipeline.armazenamento.contratos import Contrato

log = logging.getLogger("pipeline")

VARIAVEL_URL = "AGROVALID_DATABASE_URL"
MIGRACOES = ddl.MIGRACOES
# A 0003 (tabelas pesadas e geometrias do perfil completo) não se aplica ao lite.
SO_COMPLETO = ("0003_",)
LINHAS_POR_BLOCO = 50_000
NULO = r"\N"


class ErroDeCarga(Exception):
    """Falta a URL do banco, tabela fora do perfil ou dado que o banco recusou."""


# ---------------------------------------------------------------------------------------------------------------
# Migrações
# ---------------------------------------------------------------------------------------------------------------

def arquivos_de_migracao(perfil: str) -> list[Path]:
    arquivos = sorted(MIGRACOES.glob("*.sql"))
    return [a for a in arquivos if perfil == "completo" or not a.name.startswith(SO_COMPLETO)]


def _aplicadas(conn: psycopg.Connection) -> dict[str, str]:
    if conn.execute("SELECT to_regclass('meta.migracao')").fetchone()[0] is None:
        return {}
    return dict(conn.execute("SELECT nome, sha256 FROM meta.migracao").fetchall())


def migrar(conn: psycopg.Connection, perfil: str) -> list[str]:
    """Aplica, em ordem, as migrações que faltam (cada uma numa transação) e as registra em meta.migracao."""
    feitas = _aplicadas(conn)
    novas = []
    for arquivo in arquivos_de_migracao(perfil):
        texto = arquivo.read_text(encoding="utf-8")
        sha = hashlib.sha256(texto.encode()).hexdigest()
        if arquivo.name in feitas:
            if feitas[arquivo.name] != sha:
                log.warning("[banco] %s mudou depois de aplicada; recrie o banco para pegar a versão nova", arquivo.name)
            continue
        with conn.transaction():
            conn.execute(texto)
            conn.execute("INSERT INTO meta.migracao (nome, sha256) VALUES (%s, %s)", (arquivo.name, sha))
        novas.append(arquivo.name)
        log.info("[banco] migração aplicada: %s", arquivo.name)
    return novas


# ---------------------------------------------------------------------------------------------------------------
# Preparo do DataFrame para o COPY
# ---------------------------------------------------------------------------------------------------------------

def _utc_sem_fuso(serie: pd.Series) -> pd.Series:
    """O que vier com fuso é convertido para UTC; o que vier sem fuso já é tratado como UTC."""
    return pd.to_datetime(serie, utc=True).dt.tz_localize(None)


def _iso(serie: pd.Series, unidade: str) -> pd.Series:
    """ISO com o ano de 4 dígitos sempre (a fonte traz 0026; o strftime do pandas o encurtaria para 26)."""
    valores = serie.to_numpy(dtype=f"datetime64[{unidade}]")
    texto = pd.Series(np.datetime_as_string(valores, unit=unidade), index=serie.index, dtype="string")
    return texto.where(~np.isnat(valores))


def _como_texto(serie: pd.Series, tipo: str) -> pd.Series:
    """Valores no formato que o COPY (CSV) lê, com <NA> para nulo."""
    if tipo == "inteiro":
        return pd.to_numeric(serie).astype("Int64")
    if tipo == "decimal":
        return pd.to_numeric(serie).astype("float64")
    if tipo == "logico":
        return serie.astype("boolean")
    if tipo == "data_hora":
        return _iso(_utc_sem_fuso(serie), "us").str.replace("T", " ", regex=False)
    if tipo == "data":
        return _iso(pd.to_datetime(serie), "D")
    if tipo == "geometria":
        texto = serie.astype("string")
        return ("SRID=" + str(ddl.SRID) + ";" + texto).where(texto.notna() & (texto != ""))
    return serie.astype("string")


def completar_controle(df: pd.DataFrame, c: Contrato, agora: pd.Timestamp) -> tuple[pd.DataFrame, int]:
    """Leitura do legado vem sem as colunas de controle e sem a validação do contrato. Preenche o controle (a chave do
    banco exige valido_de e consultado_em) e tira o que a chave não aceita: nulo e repetição. Devolve o DataFrame e
    quantas linhas tirou."""
    faltam = [n for n in c.controle if n not in df.columns]
    if not faltam:
        return df, 0
    padrao = {"carga_id": "legado", "valido_de": agora, "consultado_em": agora}
    df = df.assign(**{n: padrao.get(n) for n in faltam})
    chave = list(c.chave)
    ruim = df[chave].isna().any(axis=1) | df.duplicated(chave, keep="first")
    log.warning("[banco] %s lida do legado: controle %s preenchido; %s linha(s) fora da chave (nula ou repetida) "
                "deixadas de lado", c.tabela, faltam, int(ruim.sum()))
    return df[~ruim].reset_index(drop=True), int(ruim.sum())


def preparar(df: pd.DataFrame, c: Contrato, perfil: str) -> tuple[pd.DataFrame, list[str]]:
    """(df só com as colunas do banco no perfil, na ordem, com os nomes do banco; tipos de cada uma)."""
    colunas = ddl.colunas_banco(c, perfil)
    tipos = {x.nome: x.tipo for x in c.colunas}
    tipos.update({"carga_id": "texto", "hash_linha": "texto", "valido_de": "data_hora", "valido_ate": "data_hora",
                  "consultado_em": "data_hora"})
    saida = pd.DataFrame({nome: df[origem] for nome, origem in colunas})
    return saida, [tipos[origem] for _, origem in colunas]


def blocos_csv(df: pd.DataFrame, tipos: list[str]):
    """Texto CSV do DataFrame em blocos, já convertido para o formato do banco (nulo = \\N). O fim de linha é CRLF para
    que um CR solto dentro de um texto saia entre aspas."""
    for ini in range(0, len(df), LINHAS_POR_BLOCO):
        parte = df.iloc[ini:ini + LINHAS_POR_BLOCO]
        parte = pd.DataFrame({n: _como_texto(parte[n], t) for n, t in zip(df.columns, tipos)}, index=parte.index)
        yield parte.to_csv(index=False, header=False, na_rep=NULO, lineterminator="\r\n")


# ---------------------------------------------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------------------------------------------

def carregar_tabela(conn: psycopg.Connection, c: Contrato, perfil: str, agora: pd.Timestamp) -> tuple[int, int] | None:
    """Recarrega a tabela. Devolve (linhas carregadas, linhas do legado fora da chave), ou None se a tabela ainda não
    está no lago."""
    df = lago.ler_ou_none(c.tabela, vigente=c.historico == "fotografia")
    if df is None:
        log.warning("[banco] %s ainda não está no lago; pulada", c.tabela)
        return None
    faltam = [n for n in c.nomes if n not in df.columns]
    if faltam:
        if lago.existe(c.tabela):
            raise ErroDeCarga(f"{c.tabela}: o lago não tem as colunas {faltam} do contrato")
        log.warning("[banco] %s: o legado não tem as colunas %s do contrato; pulada até a fonte gravar no lago",
                    c.tabela, faltam)
        return None
    df, descartadas = completar_controle(df, c, agora)
    df, tipos = preparar(df, c, perfil)
    nomes = ", ".join(df.columns)
    try:
        with conn.transaction():
            conn.execute(f"TRUNCATE {c.tabela}")
            with conn.cursor() as cur, cur.copy(
                    f"COPY {c.tabela} ({nomes}) FROM STDIN WITH (FORMAT csv, NULL '{NULO}')") as copia:
                for bloco in blocos_csv(df, tipos):
                    copia.write(bloco)
            conn.execute(f"ANALYZE {c.tabela}")
    except psycopg.Error as erro:
        raise ErroDeCarga(f"{c.tabela}: o banco recusou a carga ({str(erro).splitlines()[0]})") from erro
    return len(df), descartadas


def tamanhos(conn: psycopg.Connection, selecionadas: list[Contrato]) -> dict[str, int]:
    """Bytes por tabela (dados, índices e TOAST), por pg_total_relation_size."""
    return {c.tabela: conn.execute("SELECT pg_total_relation_size(%s::regclass)", (c.tabela,)).fetchone()[0]
            for c in selecionadas}


def escolher(perfil: str, tabelas: list[str] | None) -> list[Contrato]:
    """Tabelas do perfil; `tabelas` restringe (nome completo ou só o esquema)."""
    do_perfil = ddl.tabelas(perfil)
    if not tabelas:
        return do_perfil
    nomes = {c.tabela for c in do_perfil}
    desconhecidas = [t for t in tabelas if t not in nomes and not any(n.startswith(t + ".") for n in nomes)]
    if desconhecidas:
        raise ErroDeCarga(f"tabela(s) fora do perfil {perfil} ou sem contrato: {', '.join(desconhecidas)}")
    return [c for c in do_perfil if c.tabela in tabelas or c.esquema in tabelas]


def carregar(url: str, perfil: str, aplicar_migracoes: bool = False, tabelas: list[str] | None = None) -> dict:
    """Carrega o perfil e devolve {"tabelas": {nome: {"linhas", "bytes", "segundos"}}, "total_bytes", "banco_bytes"}."""
    selecionadas = escolher(perfil, tabelas)
    agora = pd.Timestamp.now("UTC").tz_localize(None)
    resumo = {}
    with psycopg.connect(url, autocommit=True) as conn:
        if aplicar_migracoes:
            migrar(conn, perfil)
        elif not _aplicadas(conn):
            raise ErroDeCarga("o banco não tem as migrações aplicadas; rode com --migrar")
        for c in selecionadas:
            t0 = time.perf_counter()
            feito = carregar_tabela(conn, c, perfil, agora)
            linhas, descartadas = feito or (None, 0)
            resumo[c.tabela] = {"linhas": linhas, "descartadas_legado": descartadas,
                                "segundos": round(time.perf_counter() - t0, 1)}
            if linhas is not None:
                log.info("[banco] %s: %s linhas", c.tabela, linhas)
        sizes = tamanhos(conn, ddl.tabelas(perfil))
        banco_bytes = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]
    for nome, tamanho in sizes.items():
        resumo.setdefault(nome, {"linhas": None, "descartadas_legado": 0, "segundos": 0.0})["bytes"] = tamanho
    return {"perfil": perfil, "tabelas": resumo, "total_bytes": sum(sizes.values()), "banco_bytes": banco_bytes}


def tabela_de_tamanhos(resultado: dict) -> str:
    linhas = sorted(resultado["tabelas"].items(), key=lambda kv: -kv[1]["bytes"])
    largura = max(len(n) for n, _ in linhas)
    saida = [f"{'tabela':<{largura}}  {'linhas':>10}  {'MB':>9}"]
    for nome, d in linhas:
        n = "pulada" if d["linhas"] is None else f"{d['linhas']:,}".replace(",", ".")
        saida.append(f"{nome:<{largura}}  {n:>10}  {d['bytes'] / 1e6:>9.2f}")
    saida.append(f"{'total das tabelas':<{largura}}  {'':>10}  {resultado['total_bytes'] / 1e6:>9.2f}")
    saida.append(f"{'banco inteiro (pg_database_size)':<{largura}}  {'':>10}  {resultado['banco_bytes'] / 1e6:>9.2f}")
    return "\n".join(saida)


def principal(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.armazenamento.banco", description=__doc__.split("\n")[0])
    ap.add_argument("--perfil", choices=("lite", "completo"), required=True)
    ap.add_argument("--url", help=f"URL do Postgres; sem ela, a variável {VARIAVEL_URL}")
    ap.add_argument("--migrar", action="store_true", help="aplica antes as migrações que faltam")
    ap.add_argument("--tabelas", nargs="+", metavar="TABELA", help="só estas tabelas (esquema.tabela ou o esquema)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    url = args.url or os.environ.get(VARIAVEL_URL)
    if not url:
        print(f"erro: informe a URL do banco com --url ou com a variável {VARIAVEL_URL}", file=sys.stderr)
        return 2
    try:
        resultado = carregar(url, args.perfil, args.migrar, args.tabelas)
    except ErroDeCarga as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    print(tabela_de_tamanhos(resultado))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
