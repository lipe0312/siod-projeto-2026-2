"""Validação de CPF/CNPJ e pseudonimização dos documentos."""

import hashlib
import hmac
import logging
import os
import re
import secrets

import pandas as pd

from pipeline import config

log = logging.getLogger("pipeline")


def somente_digitos(valores: pd.Series) -> pd.Series:
    return valores.astype("string").str.replace(r"\D", "", regex=True).replace("", pd.NA)


def cpf_valido(numero: str) -> bool:
    if len(numero) != 11 or not numero.isdigit() or numero == numero[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(numero[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10) % 11 % 10 != int(numero[n]):
            return False
    return True


def cnpj_valido(numero: str) -> bool:
    if len(numero) != 14 or not numero.isdigit() or numero == numero[0] * 14:
        return False
    pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n in (12, 13):
        soma = sum(int(numero[i]) * pesos[i + (13 - n)] for i in range(n))
        resto = soma % 11
        if (0 if resto < 2 else 11 - resto) != int(numero[n]):
            return False
    return True


def tipo_documento(numeros: pd.Series) -> pd.Series:
    tamanho = numeros.str.len()
    tipo = pd.Series(pd.NA, index=numeros.index, dtype="string")
    return tipo.mask(tamanho.eq(11).fillna(False), "CPF").mask(tamanho.eq(14).fillna(False), "CNPJ")


def digito_valido(numeros: pd.Series) -> pd.Series:
    def verificar(n):
        if pd.isna(n):
            return False
        return cpf_valido(n) if len(n) == 11 else cnpj_valido(n) if len(n) == 14 else False

    return numeros.map(verificar).astype(bool)


NOME_DE_DOCUMENTO = re.compile(r"cpf|cnpj|documento", re.IGNORECASE)
FORMATO_CPF_CNPJ = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
OMITIDO = "[documento omitido]"


def sem_documento(valores: dict, preservar=()) -> dict:
    """Colunas livres de uma planilha sem CPF ou CNPJ em claro: sai a coluna com nome de documento, e o valor no
    formato de um vira OMITIDO. `preservar`: colunas conhecidas, que passam sem conferência (ex.: cod_car)."""
    saida = {}
    for k, v in valores.items():
        if k in preservar:
            saida[k] = v
        elif not NOME_DE_DOCUMENTO.search(str(k)):
            saida[k] = OMITIDO if isinstance(v, str) and FORMATO_CPF_CNPJ.search(v) else v
    return saida


def carregar_chave() -> bytes:
    """Lê a chave da variável de ambiente ou do arquivo local; cria o arquivo se não existir."""
    valor = os.environ.get(config.CHAVE_ENV)
    if valor:
        return valor.encode()
    if not config.CHAVE_ARQUIVO.exists():
        config.CHAVE_ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        config.CHAVE_ARQUIVO.write_text(secrets.token_hex(32))
        log.warning("Chave de pseudonimização criada em %s. Guarde-a: sem ela os códigos não se repetem.",
                    config.CHAVE_ARQUIVO.relative_to(config.RAIZ))
    return config.CHAVE_ARQUIVO.read_text().strip().encode()


def pseudonimizar(numeros: pd.Series, chave: bytes) -> pd.Series:
    """HMAC-SHA256 do documento (só dígitos). Documentos ausentes continuam ausentes."""
    return numeros.map(
        lambda n: pd.NA if pd.isna(n) else hmac.new(chave, n.encode(), hashlib.sha256).hexdigest()
    ).astype("string")
