"""Contratos de dados (contratos/<esquema>/<tabela>.yaml): leitura e validação do DataFrame antes de gravar no lago.

O formato está em contratos/LEIA-ME.md. O contrato é a definição única da tabela: o lago valida contra ele e o DDL do
banco é gerado dele.
"""

import functools
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
from pandas.api import types

from pipeline import config

TIPOS = ("texto", "inteiro", "decimal", "logico", "data_hora", "data", "json", "geometria")
HISTORICOS = ("fotografia", "validade", "acrescimo", "por_consulta", "registro")
PERFIS = ("lite", "completo", "fora")
# Colunas que o lago acrescenta conforme o histórico (não estão no contrato; ver contratos/LEIA-ME.md).
CONTROLE = {"fotografia": ("carga_id",), "validade": ("carga_id", "valido_de", "valido_ate", "hash_linha"),
            "acrescimo": ("carga_id", "hash_linha"), "por_consulta": ("carga_id", "consultado_em"), "registro": ()}


class ErroDeContrato(Exception):
    """DataFrame diferente do contrato da tabela, ou contrato malformado."""


@dataclass(frozen=True)
class Coluna:
    nome: str
    tipo: str
    nulo: bool = True


@dataclass(frozen=True)
class Contrato:
    tabela: str
    descricao: str
    fonte: str
    chave: tuple[str, ...]
    historico: str
    perfil_banco: str
    colunas: tuple[Coluna, ...]
    acompanhar: tuple[str, ...] = ()
    particao: str | None = None
    substituir_particao: bool = False
    geometria: dict | None = None
    unico: tuple[str, ...] = ()

    @property
    def esquema(self) -> str:
        return self.tabela.split(".")[0]

    @property
    def nome(self) -> str:
        return self.tabela.split(".")[1]

    @property
    def nomes(self) -> list[str]:
        return [c.nome for c in self.colunas]

    @property
    def controle(self) -> tuple[str, ...]:
        return CONTROLE[self.historico]


def _ler(arquivo: Path) -> Contrato:
    d = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    tabela = d.get("tabela", "")
    esperado = f"{arquivo.parent.name}.{arquivo.stem}"
    if tabela != esperado:
        raise ErroDeContrato(f"{arquivo}: tabela '{tabela}' diferente do caminho ({esperado})")
    colunas = tuple(Coluna(c["nome"], c["tipo"], c.get("nulo", True)) for c in d["colunas"])
    contrato = Contrato(tabela=tabela, descricao=d.get("descricao", ""), fonte=d["fonte"], chave=tuple(d["chave"]),
                        historico=d["historico"], perfil_banco=d["perfil_banco"], colunas=colunas,
                        acompanhar=tuple(d.get("acompanhar", ())), particao=d.get("particao"),
                        substituir_particao=bool(d.get("substituir_particao", False)), geometria=d.get("geometria"),
                        unico=tuple(d.get("unico", ())))
    problemas = [f"tipo '{c.tipo}' da coluna {c.nome}" for c in colunas if c.tipo not in TIPOS]
    problemas += [f"histórico '{contrato.historico}'"] if contrato.historico not in HISTORICOS else []
    problemas += [f"perfil '{contrato.perfil_banco}'"] if contrato.perfil_banco not in PERFIS else []
    referidas = [*contrato.chave, *contrato.acompanhar, *contrato.unico, *([contrato.particao] if contrato.particao else [])]
    problemas += [f"coluna '{n}' citada e não declarada" for n in referidas if n not in contrato.nomes]
    problemas += [f"chave '{n}' aceita nulo" for n in contrato.chave
                  if next(c for c in colunas if c.nome == n).nulo] if not problemas else []
    if contrato.historico == "validade" and not contrato.acompanhar:
        problemas.append("histórico 'validade' sem 'acompanhar'")
    if problemas:
        raise ErroDeContrato(f"{arquivo}: " + "; ".join(problemas))
    return contrato


@functools.cache
def todos() -> dict[str, Contrato]:
    """Todos os contratos, por nome da tabela (esquema.tabela)."""
    arquivos = sorted(config.CONTRATOS.glob("*/*.yaml"))
    return {c.tabela: c for c in map(_ler, arquivos)}


def carregar(tabela: str) -> Contrato:
    try:
        return todos()[tabela]
    except KeyError:
        raise ErroDeContrato(f"sem contrato para {tabela} em {config.CONTRATOS}") from None


def catalogo_fontes() -> list[dict]:
    """Catálogo de fontes (contratos/fontes.yaml), base de meta.fonte."""
    return yaml.safe_load((config.CONTRATOS / "fontes.yaml").read_text(encoding="utf-8"))


def _tipo_confere(serie: pd.Series, tipo: str) -> bool:
    valores = serie.dropna()
    if valores.empty:
        return True
    if tipo in ("texto", "json", "geometria"):
        return types.is_string_dtype(serie) or valores.map(lambda v: isinstance(v, str)).all()
    if tipo == "inteiro":
        return types.is_integer_dtype(serie) or (types.is_float_dtype(serie) and (valores % 1 == 0).all())
    if tipo == "decimal":
        return types.is_numeric_dtype(serie) and not types.is_bool_dtype(serie)
    if tipo == "logico":
        return types.is_bool_dtype(serie) or valores.map(lambda v: isinstance(v, bool)).all()
    if tipo == "data_hora":
        return types.is_datetime64_any_dtype(serie)
    if tipo == "data":
        return types.is_datetime64_any_dtype(serie) or valores.map(lambda v: hasattr(v, "isoformat")).all()
    return False


def validar(df: pd.DataFrame, contrato: Contrato) -> pd.DataFrame:
    """Confere colunas, tipos, nulos e chave. Devolve o DataFrame com as colunas na ordem do contrato, sem as colunas
    de controle (o lago as recalcula). Coluna a mais, a menos, de tipo errado, nulo proibido ou chave repetida
    levantam ErroDeContrato."""
    tabela = contrato.tabela
    df = df.drop(columns=[c for c in contrato.controle if c in df.columns])
    faltam = [n for n in contrato.nomes if n not in df.columns]
    sobram = [n for n in df.columns if n not in contrato.nomes]
    if faltam or sobram:
        raise ErroDeContrato(f"{tabela}: colunas que faltam {faltam}; colunas fora do contrato {sobram}")
    erros = [f"{c.nome} não é {c.tipo} ({df[c.nome].dtype})" for c in contrato.colunas
             if not _tipo_confere(df[c.nome], c.tipo)]
    erros += [f"{c.nome} com {n} nulo(s)" for c in contrato.colunas
              if not c.nulo and (n := int(df[c.nome].isna().sum()))]
    repetidas = int(df.duplicated(list(contrato.chave)).sum())
    if repetidas:
        erros.append(f"chave {list(contrato.chave)} repetida em {repetidas} linha(s)")
    if erros:
        raise ErroDeContrato(f"{tabela}: " + "; ".join(erros))
    df = df[contrato.nomes].reset_index(drop=True)
    # Número no dtype do contrato: o hash do histórico compara texto, e 5 (Int64) e 5.0 (float) abririam versão nova.
    for c in contrato.colunas:
        if c.tipo == "inteiro" and not types.is_integer_dtype(df[c.nome]):
            df[c.nome] = df[c.nome].astype("Int64")
        elif c.tipo == "decimal" and not types.is_float_dtype(df[c.nome]):
            df[c.nome] = df[c.nome].astype("float64")
    return df
