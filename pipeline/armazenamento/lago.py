"""Lago: o dado tratado em data/lago/<esquema>/<tabela>/, validado pelo contrato e com histórico (ADR 0017).

    lago.gravar("ref.embargo_ibama", df, resultado)   # valida, grava conforme o histórico, anota no resultado
    lago.ler("ref.embargo_ibama")                     # estado vigente: colunas do contrato mais carga_id
    lago.ler("ref.desmatamento_prodes", particao="MG")
    lago.ler("ref.embargo_ibama", vigente=False)      # todas as versões

Transição: enquanto uma fonte não grava no lago, `ler` cai no arquivo antigo de data/processed/ indicado em `legado`
no contrato (com aviso no log). Sem nenhum dos dois, levanta TabelaAusente.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline import config
from pipeline.armazenamento import contratos, historico
from pipeline.validacao import ResultadoFonte

log = logging.getLogger("pipeline")


class TabelaAusente(FileNotFoundError):
    """A tabela ainda não foi gravada no lago (nem existe o arquivo legado)."""


def pasta(tabela: str) -> Path:
    esquema, nome = tabela.split(".")
    return config.LAGO / esquema / nome


def _relativo(caminho: Path) -> str:
    return str(caminho.relative_to(config.RAIZ)) if caminho.is_relative_to(config.RAIZ) else str(caminho)


def momento_da_carga(carga_id: str) -> datetime:
    return datetime.strptime(carga_id.split(":")[-1], "%Y%m%dT%H%M%S")


def gravar(tabela: str, df: pd.DataFrame, resultado: ResultadoFonte | None = None, carga_id: str | None = None,
           momento: datetime | None = None) -> dict:
    """Valida `df` contra o contrato e grava conforme o histórico da tabela. A carga vem do `resultado` (o mesmo
    carga_id que vai para meta.carga) ou de `carga_id`. O resumo da gravação fica em resultado.saida["tabelas"]."""
    contrato = contratos.carregar(tabela)
    carga_id = carga_id or (resultado.carga_id if resultado else None)
    if not carga_id:
        raise ValueError(f"{tabela}: gravar exige o ResultadoFonte ou o carga_id")
    momento = momento or momento_da_carga(carga_id)
    df = contratos.validar(df, contrato)
    resumo = historico.GRAVAR[contrato.historico](pasta(tabela), df, contrato, carga_id, momento)
    if resultado is not None:
        resultado.saida.setdefault("tabelas", {})[tabela] = resumo
        resultado.transformar(f"Gravado em {tabela} ({contrato.historico}): "
                              + ", ".join(f"{k} {v}" for k, v in resumo.items() if k != "historico"))
    return resumo


def quadro(tabela: str, linhas: list[dict]) -> pd.DataFrame:
    """DataFrame com as colunas e os tipos do contrato (linhas vazias viram quadro vazio com as colunas certas)."""
    contrato = contratos.carregar(tabela)
    df = pd.DataFrame(linhas, columns=contrato.nomes)
    for c in contrato.colunas:
        if c.tipo == "data_hora":
            df[c.nome] = pd.to_datetime(df[c.nome])
        elif c.tipo == "inteiro":
            df[c.nome] = df[c.nome].astype("Int64")
        elif c.tipo == "decimal":
            df[c.nome] = pd.to_numeric(df[c.nome]).astype("float64")
        elif c.tipo == "logico":
            df[c.nome] = df[c.nome].astype("boolean")
        else:
            df[c.nome] = df[c.nome].astype("string")
    return df


def existe(tabela: str) -> bool:
    contrato = contratos.carregar(tabela)
    p = pasta(tabela)
    if contrato.historico == "fotografia":
        return (p / historico.ARQ_VIGENTE).exists()
    return p.exists() and any(p.rglob("*.parquet"))


def _ler_legado(contrato: contratos.Contrato, particao=None, colunas=None) -> pd.DataFrame | None:
    if not contrato.legado:
        return None
    caminho = config.DADOS_PROCESSADOS / contrato.legado
    if caminho.is_dir():
        if particao is not None:
            arquivos = [caminho / f"{contrato.particao}={particao}" / "part.parquet"]
        else:
            arquivos = sorted(caminho.glob(f"{contrato.particao}=*/part.parquet"))
        arquivos = [a for a in arquivos if a.exists()]
        if not arquivos:
            return None
        df = pd.concat([pd.read_parquet(a, columns=colunas) for a in arquivos], ignore_index=True)
    elif caminho.exists():
        df = pd.read_parquet(caminho, columns=colunas)
    else:
        return None
    log.warning("[lago] %s ainda não está no lago; lido de %s (legado)", contrato.tabela, _relativo(caminho))
    return df


def ler(tabela: str, vigente: bool = True, particao=None, colunas: list[str] | None = None) -> pd.DataFrame:
    """Estado vigente da tabela (ou o histórico, com vigente=False). `particao` lê só uma partição (ex.: a UF)."""
    contrato = contratos.carregar(tabela)
    df = historico.ler(pasta(tabela), contrato, vigente, particao, colunas)
    if df is None:
        df = _ler_legado(contrato, particao, colunas)
    if df is None:
        raise TabelaAusente(f"{tabela} não está no lago ({_relativo(pasta(tabela))})")
    return df


def ler_ou_none(tabela: str, **kwargs) -> pd.DataFrame | None:
    try:
        return ler(tabela, **kwargs)
    except TabelaAusente:
        return None


def gravar_descartes(df: pd.DataFrame, resultado: ResultadoFonte, chave: str | list[str],
                     motivo: str = "motivo") -> dict:
    """Descartes de uma carga em meta.descarte: identificador, motivo e o registro original em JSON."""
    chave = [chave] if isinstance(chave, str) else list(chave)
    if df.empty:
        return {"historico": "registro", "inseridos": 0}
    ident = df[chave].astype("string").fillna("").agg("|".join, axis=1)
    sem_id = ident.str.strip("|") == ""
    ident = ident.where(~sem_id, "linha:" + pd.Series(range(len(df)), index=df.index).astype(str))
    dados = df.drop(columns=[motivo], errors="ignore")
    registros = [json.dumps(r, ensure_ascii=False, default=str) for r in
                 json.loads(dados.to_json(orient="records", date_format="iso", force_ascii=False))]
    saida = pd.DataFrame({"carga_id": resultado.carga_id, "fonte": resultado.fonte, "registro_id": ident.to_numpy(),
                          "motivo": df[motivo].astype("string").to_numpy() if motivo in df else pd.NA,
                          "dados_json": registros})
    # O mesmo registro pode ter mais de um motivo; fica uma linha com os motivos juntos.
    saida = saida.groupby(["carga_id", "fonte", "registro_id"], as_index=False, sort=False).agg(
        motivo=("motivo", lambda m: "; ".join(dict.fromkeys(m.dropna()))), dados_json=("dados_json", "first"))
    return gravar("meta.descarte", saida, carga_id=resultado.carga_id)
