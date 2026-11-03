"""Tabela de referência de municípios do IBGE e resolução de município por nome e UF."""

import json
import re
import unicodedata

import pandas as pd

from pipeline import config
from pipeline.armazenamento import lago
from pipeline.download import baixar
from pipeline.validacao import ResultadoFonte

# Nomes usados nos alertas do INPE que diferem do nome oficial no IBGE.
# Cada entrada foi conferida manualmente contra a lista do IBGE (chave normalizada "NOME|UF").
APELIDOS = {
    "SANTO ANTONIO DO LEVERGER|MT": "SANTO ANTONIO DE LEVERGER|MT",
    "SANTA ISABEL DO PARA|PA": "SANTA IZABEL DO PARA|PA",
    "FORTALEZA DO TABOCAO|TO": "TABOCAO|TO",
    "MUQUEM DE SAO FRANCISCO|BA": "MUQUEM DO SAO FRANCISCO|BA",
}


def normalizar_nome(nome) -> str:
    if nome is None or pd.isna(nome):
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]", " ", sem_acento.upper())).strip()


def _uf(municipio: dict):
    for caminho in (("microrregiao", "mesorregiao", "UF"), ("regiao-imediata", "regiao-intermediaria", "UF")):
        no = municipio
        for chave in caminho:
            no = (no or {}).get(chave)
        if no:
            return no.get("sigla")
    return None


def construir_referencia(dados, resultado: ResultadoFonte) -> pd.DataFrame:
    resultado.validar("IBGE_ESTRUTURA_RESPOSTA", "Resposta da API é uma lista de municípios com id e nome",
                      "erro", "interrompe IBAMA e DETER, que dependem da referência",
                      int(not (isinstance(dados, list) and all("id" in m and "nome" in m for m in dados))), 1)
    ref = pd.DataFrame({
        "cod_municipio": [str(m["id"]) for m in dados],
        "municipio": [m["nome"] for m in dados],
        "uf": [_uf(m) for m in dados],
    })
    resultado.validar("IBGE_QUANTIDADE_INESPERADA", "Lista com ao menos 5.500 municípios", "erro",
                      "interrompe IBAMA e DETER, que dependem da referência", int(len(ref) < 5500), 1)
    resultado.validar("IBGE_UF_AUSENTE", "Município sem UF identificável", "erro", "interrompe IBAMA e DETER, que dependem da referência",
                      ref["uf"].isna(), len(ref))
    resultado.validar("IBGE_CODIGO_DUPLICADO", "Código IBGE repetido", "erro", "interrompe IBAMA e DETER, que dependem da referência",
                      ref["cod_municipio"].duplicated(), len(ref))
    ref["chave"] = ref["municipio"].map(normalizar_nome) + "|" + ref["uf"]
    resultado.validar("IBGE_NOME_UF_DUPLICADO", "Nome normalizado + UF repetido (impede resolver por nome)",
                      "erro", "interrompe IBAMA e DETER, que dependem da referência", ref["chave"].duplicated(), len(ref))
    resultado.transformar("Normalização do nome (sem acento, maiúsculas, só letras e números) + UF como chave")
    return ref


def carregar_referencia(atualizar: bool = False) -> tuple[pd.DataFrame, ResultadoFonte]:
    resultado = ResultadoFonte("ibge_municipios", "API (JSON)")
    resultado.entrada = baixar(config.URL_IBGE_MUNICIPIOS, config.DADOS_BRUTOS / "ibge_municipios.json", atualizar)
    dados = json.loads((config.DADOS_BRUTOS / "ibge_municipios.json").read_text(encoding="utf-8"))
    resultado.entrada["registros_recebidos"] = len(dados) if isinstance(dados, list) else 0
    ref = construir_referencia(dados, resultado)
    lago.gravar("geo.municipio", ref, resultado)
    resultado.saida.update({"arquivo": lago._relativo(lago.pasta("geo.municipio")), "registros_produzidos": len(ref)})
    resultado.status = "ok"
    return ref, resultado


def resolver_por_nome(nomes: pd.Series, ufs: pd.Series, ref: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Devolve (código IBGE, máscara de nomes corrigidos por apelido)."""
    chave = nomes.map(normalizar_nome) + "|" + ufs.fillna("").astype(str).str.upper()
    corrigido = chave.isin(APELIDOS.keys())
    chave = chave.replace(APELIDOS)
    mapa = ref.set_index("chave")["cod_municipio"]
    return chave.map(mapa).astype("string"), corrigido
