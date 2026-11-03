"""Como cada tipo de histórico grava e lê uma tabela do lago (contratos/LEIA-ME.md, seção Histórico).

Cada função recebe a pasta da tabela, o DataFrame já validado pelo contrato, o contrato, o carga_id e o momento da
carga, e devolve um resumo do que foi gravado (vai para o ResultadoFonte e para meta.carga). Toda escrita é atômica:
grava num arquivo temporário e troca pelo definitivo.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline.armazenamento.contratos import Contrato

ARQ_VIGENTE = "_vigente.json"
ARQ_VERSOES = "versoes.parquet"
ARQ_PARTE = "part.parquet"


# ---------------------------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------------------------

def gravar_parquet(df: pd.DataFrame, arquivo: Path) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_name(f".{arquivo.name}.{uuid.uuid4().hex[:8]}.tmp")
    df.to_parquet(temporario, index=False)
    os.replace(temporario, arquivo)


def _gravar_json(dados: dict, arquivo: Path) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_name(f".{arquivo.name}.tmp")
    temporario.write_text(json.dumps(dados, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(temporario, arquivo)


def _texto(df: pd.DataFrame, colunas) -> pd.DataFrame:
    """Valores como texto, para o hash não depender do dtype com que o Parquet foi lido de volta."""
    saida = pd.DataFrame(index=df.index)
    for c in colunas:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            s = s.dt.tz_localize(None) if getattr(s.dt, "tz", None) is not None else s
            s = s.dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
        saida[c] = s.astype("string").fillna("\x00")
    return saida


def hash_linhas(df: pd.DataFrame, colunas) -> pd.Series:
    """Hash de 16 dígitos hexadecimais por linha, sobre as colunas dadas."""
    if df.empty:
        return pd.Series([], index=df.index, dtype="string")
    valores = pd.util.hash_pandas_object(_texto(df, list(colunas)), index=False)
    return valores.map(lambda v: f"{v:016x}").astype("string").set_axis(df.index)


def chave_linhas(df: pd.DataFrame, chave) -> pd.Series:
    return hash_linhas(df, chave)


def hash_conteudo(df: pd.DataFrame, contrato: Contrato) -> str:
    """SHA-256 do conteúdo, independente da ordem das linhas."""
    linhas = hash_linhas(df, contrato.nomes).sort_values()
    return hashlib.sha256("".join(linhas.tolist()).encode()).hexdigest()


def _pasta_carga(carga_id: str) -> str:
    return "carga=" + carga_id.split(":")[-1]


def _particoes(df: pd.DataFrame, contrato: Contrato):
    if not contrato.particao:
        yield None, df
        return
    for valor, grupo in df.groupby(contrato.particao, sort=True, dropna=False):
        yield valor, grupo


def _sub(pasta: Path, contrato: Contrato, valor) -> Path:
    return pasta / f"{contrato.particao}={valor}" if contrato.particao else pasta


def ler_vigente_json(pasta: Path) -> dict | None:
    arquivo = pasta / ARQ_VIGENTE
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else None


def _ler_arquivos(arquivos: list[Path], colunas=None) -> pd.DataFrame | None:
    arquivos = [a for a in arquivos if a.exists()]
    if not arquivos:
        return None
    partes = [pd.read_parquet(a, columns=colunas) for a in arquivos]
    return pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]


def _arquivos_particao(raiz: Path, contrato: Contrato, nome_arquivo: str, particao=None) -> list[Path]:
    if contrato.particao and particao is not None:
        return [raiz / f"{contrato.particao}={particao}" / nome_arquivo]
    if contrato.particao:
        return sorted(raiz.glob(f"{contrato.particao}=*/{nome_arquivo}"))
    return [raiz / nome_arquivo]


# ---------------------------------------------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------------------------------------------

def fotografia(pasta: Path, df: pd.DataFrame, contrato: Contrato, carga_id: str, momento: datetime) -> dict:
    """Pasta carga=<momento>/ nova só quando o conteúdo muda; _vigente.json aponta a carga em vigor."""
    conteudo = hash_conteudo(df, contrato)
    vigente = ler_vigente_json(pasta)
    if vigente and vigente["conteudo_sha256"] == conteudo:
        return {"historico": "fotografia", "novo": False, "carga_vigente": vigente["carga_id"], "linhas": len(df)}
    destino = pasta / _pasta_carga(carga_id)
    df = df.assign(carga_id=carga_id)
    for valor, grupo in _particoes(df, contrato):
        gravar_parquet(grupo, _sub(destino, contrato, valor) / ARQ_PARTE)
    _gravar_json({"carga_id": carga_id, "pasta": destino.name, "conteudo_sha256": conteudo, "linhas": len(df),
                  "gravado_em": momento.isoformat(timespec="seconds"),
                  "carga_anterior": vigente["carga_id"] if vigente else None}, pasta / ARQ_VIGENTE)
    return {"historico": "fotografia", "novo": True, "carga_vigente": carga_id, "linhas": len(df),
            "carga_anterior": vigente["carga_id"] if vigente else None}


def validade(pasta: Path, df: pd.DataFrame, contrato: Contrato, carga_id: str, momento: datetime) -> dict:
    """Um arquivo com todas as versões. Registro novo ou com coluna acompanhada alterada abre uma versão; o que sumiu
    da fonte tem a versão fechada (valido_ate). Mudança só em coluna não acompanhada corrige a versão aberta, sem
    abrir outra."""
    instante = pd.Timestamp(momento)
    novo = df.assign(hash_linha=hash_linhas(df, contrato.acompanhar), _k=chave_linhas(df, contrato.chave))
    arquivo = pasta / ARQ_VERSOES
    if not arquivo.exists():
        saida = novo.drop(columns="_k").assign(carga_id=carga_id, valido_de=instante, valido_ate=pd.NaT)
        gravar_parquet(saida, arquivo)
        return {"historico": "validade", "inseridos": len(novo), "alterados": 0, "encerrados": 0,
                "inalterados": 0, "versoes": len(saida)}
    hist = pd.read_parquet(arquivo)
    aberto = hist["valido_ate"].isna()
    fechadas, abertas = hist[~aberto], hist[aberto].copy()
    abertas["_k"] = chave_linhas(abertas, contrato.chave)
    anteriores = abertas.set_index("_k")
    em_ambos = novo["_k"].isin(anteriores.index)
    mesmo_hash = em_ambos & (novo["_k"].map(anteriores["hash_linha"]) == novo["hash_linha"]).fillna(False)
    sumiram = ~abertas["_k"].isin(novo["_k"])
    alterados = em_ambos & ~mesmo_hash

    # Versões que continuam abertas, com os valores atuais (corrige coluna não acompanhada).
    continuam = novo[mesmo_hash].assign(carga_id=novo.loc[mesmo_hash, "_k"].map(anteriores["carga_id"]),
                                        valido_de=novo.loc[mesmo_hash, "_k"].map(anteriores["valido_de"]),
                                        valido_ate=pd.NaT)
    abertas_novas = novo[~mesmo_hash].assign(carga_id=carga_id, valido_de=instante, valido_ate=pd.NaT)
    encerradas = abertas[sumiram | abertas["_k"].isin(novo.loc[alterados, "_k"])].assign(valido_ate=instante)
    partes = [fechadas, encerradas.drop(columns="_k"), continuam.drop(columns="_k"), abertas_novas.drop(columns="_k")]
    saida = pd.concat([p for p in partes if not p.empty], ignore_index=True)[hist.columns]
    gravar_parquet(saida, arquivo)
    return {"historico": "validade", "inseridos": int((~em_ambos).sum()), "alterados": int(alterados.sum()),
            "encerrados": int(sumiram.sum()), "inalterados": int(mesmo_hash.sum()), "versoes": len(saida)}


def acrescimo(pasta: Path, df: pd.DataFrame, contrato: Contrato, carga_id: str, momento: datetime) -> dict:
    """Registro novo entra, registro alterado é regravado com a carga nova, registro igual mantém a carga em que
    entrou. Sem `substituir_particao`, o que sumiu da fonte continua; com ela, a partição gravada é a verdade inteira.
    Partição sem mudança não é regravada."""
    resumo = {"historico": "acrescimo", "inseridos": 0, "alterados": 0, "removidos": 0, "particoes_gravadas": []}
    colunas = [n for n in contrato.nomes if n not in contrato.chave] or contrato.nomes
    for valor, grupo in _particoes(df, contrato):
        arquivo = _sub(pasta, contrato, valor) / ARQ_PARTE
        novo = grupo.assign(hash_linha=hash_linhas(grupo, colunas), _k=chave_linhas(grupo, contrato.chave))
        if arquivo.exists():
            velho = pd.read_parquet(arquivo)
            velho["_k"] = chave_linhas(velho, contrato.chave)
            anteriores = velho.set_index("_k")
            em_ambos = novo["_k"].isin(anteriores.index)
            igual = em_ambos & (novo["_k"].map(anteriores["hash_linha"]) == novo["hash_linha"]).fillna(False)
            carga = novo["_k"].map(anteriores["carga_id"]).where(igual, carga_id)
            novo = novo.assign(carga_id=carga)
            ficam = velho.iloc[0:0] if contrato.substituir_particao else velho[~velho["_k"].isin(novo["_k"])]
            removidos = int((~velho["_k"].isin(novo["_k"])).sum()) if contrato.substituir_particao else 0
            inseridos, alterados = int((~em_ambos).sum()), int((em_ambos & ~igual).sum())
            if not inseridos and not alterados and not removidos:
                continue
            saida = pd.concat([ficam, novo], ignore_index=True)
        else:
            novo = novo.assign(carga_id=carga_id)
            saida, inseridos, alterados, removidos = novo, len(novo), 0, 0
        gravar_parquet(saida.drop(columns="_k")[[*contrato.nomes, "carga_id", "hash_linha"]], arquivo)
        resumo["inseridos"] += inseridos
        resumo["alterados"] += alterados
        resumo["removidos"] += removidos
        resumo["particoes_gravadas"].append(str(valor) if valor is not None else "única")
    return resumo


def por_consulta(pasta: Path, df: pd.DataFrame, contrato: Contrato, carga_id: str, momento: datetime) -> dict:
    """Uma versão por consulta. A versão é acrescentada só quando difere da mais recente da mesma chave."""
    resumo = {"historico": "por_consulta", "inseridos": 0, "repetidos": 0}
    for valor, grupo in _particoes(df, contrato):
        arquivo = _sub(pasta, contrato, valor) / ARQ_VERSOES
        novo = grupo.assign(carga_id=carga_id, consultado_em=pd.Timestamp(momento))
        if arquivo.exists():
            velho = pd.read_parquet(arquivo)
            ultimas = velho.sort_values("consultado_em").drop_duplicates(list(contrato.chave), keep="last")
            ultimas = ultimas.assign(_k=chave_linhas(ultimas, contrato.chave),
                                     _h=hash_linhas(ultimas, contrato.nomes)).set_index("_k")["_h"]
            repetido = (chave_linhas(novo, contrato.chave).map(ultimas) == hash_linhas(novo, contrato.nomes))
            repetido = repetido.fillna(False).astype(bool)
            resumo["repetidos"] += int(repetido.sum())
            novo = novo[~repetido]
            if novo.empty:
                continue
            novo = pd.concat([velho, novo], ignore_index=True)
            resumo["inseridos"] += int((~repetido).sum())
        else:
            resumo["inseridos"] += len(novo)
        gravar_parquet(novo, arquivo)
    return resumo


def registro(pasta: Path, df: pd.DataFrame, contrato: Contrato, carga_id: str, momento: datetime) -> dict:
    """Linhas próprias do sistema, só acrescentadas: um arquivo novo por gravação (nada é reescrito)."""
    for valor, grupo in _particoes(df, contrato):
        gravar_parquet(grupo, _sub(pasta, contrato, valor) / f"part-{momento:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
                                                            ".parquet")
    return {"historico": "registro", "inseridos": len(df)}


GRAVAR = {"fotografia": fotografia, "validade": validade, "acrescimo": acrescimo, "por_consulta": por_consulta,
          "registro": registro}


# ---------------------------------------------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------------------------------------------

def ler(pasta: Path, contrato: Contrato, vigente: bool = True, particao=None, colunas=None) -> pd.DataFrame | None:
    """Lê a tabela. Com `vigente`, devolve só o estado atual, com as colunas do contrato mais `carga_id`. Sem ela,
    devolve o histórico inteiro, com as colunas de controle. None se a tabela ainda não foi gravada."""
    extras = ["carga_id"] if "carga_id" in contrato.controle else []
    pedidas = None if colunas is None else list(dict.fromkeys([*colunas, *extras]))
    h = contrato.historico
    if h == "fotografia":
        estado = ler_vigente_json(pasta)
        if estado is None:
            return None
        if not vigente:
            return _ler_arquivos(sorted(pasta.glob(f"carga=*/**/{ARQ_PARTE}")), pedidas)
        return _ler_arquivos(_arquivos_particao(pasta / estado["pasta"], contrato, ARQ_PARTE, particao), pedidas)
    if h == "validade":
        leitura = None if pedidas is None else list(dict.fromkeys([*pedidas, "valido_ate"]))
        df = _ler_arquivos([pasta / ARQ_VERSOES], leitura)
        if df is None or not vigente:
            return df
        return df[df["valido_ate"].isna()].reset_index(drop=True)[pedidas or [*contrato.nomes, *extras]]
    if h == "acrescimo":
        df = _ler_arquivos(_arquivos_particao(pasta, contrato, ARQ_PARTE, particao), pedidas)
        return df if df is None or not vigente else df[pedidas or [*contrato.nomes, *extras]]
    if h == "por_consulta":
        leitura = None if pedidas is None else list(dict.fromkeys([*pedidas, *contrato.chave, "consultado_em"]))
        df = _ler_arquivos(_arquivos_particao(pasta, contrato, ARQ_VERSOES, particao), leitura)
        if df is None or not vigente:
            return df
        df = df.sort_values("consultado_em").drop_duplicates(list(contrato.chave), keep="last")
        return df.reset_index(drop=True)[pedidas or [*contrato.nomes, *extras]]
    arquivos = sorted(pasta.glob("**/part-*.parquet")) if particao is None else \
        sorted((pasta / f"{contrato.particao}={particao}").glob("part-*.parquet"))
    return _ler_arquivos(arquivos, pedidas)
