"""Fonte sob demanda: relatório do AB+S (Agro Brasil + Sustentável), pela API pública de validação.

Uma consulta por relatório, nunca em lote: o código de autenticidade (UUID) impresso no relatório é extraído do PDF,
tem o formato validado aqui (a API não distingue código malformado de inexistente) e é consultado nos três endpoints
públicos. A resposta bruta vai para data/raw/ab_s/<endpoint>/, com CPF e CNPJ pseudonimizados antes de gravar.
O AB+S é referência para comparar critérios; o projeto não declara conformidade a partir dele (ADR 0008).
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pdfplumber

from pipeline import config
from pipeline.documentos import pseudonimizar
from pipeline.download import consultar as consultar_url
from pipeline.validacao import ResultadoFonte

log = logging.getLogger("pipeline")

UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
ROTULO = re.compile(r"autenticidade\s*:?\s*(\S+)", re.IGNORECASE)
CPF_CNPJ = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
CAMPOS_DOCUMENTO = re.compile(r"cpf|cnpj|documento", re.IGNORECASE)

# Critérios do relatório de qualificação (transcritos do relatório de demonstração emitido em 07/05/2025) e a
# fonte aberta que o projeto usa para cada um. O código interno é o da taxonomia do AB+S no código público do site.
CRITERIOS = pd.DataFrame([
    (1, "Fundiária: dados cadastrais", "sim", "VERIFICACAO_DADOS_CADASTRAIS", "INCRA (SNCR)", "Conforme",
     "nenhuma", "não verifica", "A consulta pública do SNCR tem hCaptcha e não traz a situação cadastral; o CCIR trazido "
     "pelo produtor no atendimento supre o dado"),
    (2, "Fundiária: dados geoespaciais", "não", "VERIFICACAO_DADOS_GEO", "SIGEF-GEO (INCRA)", "Não conforme",
     "nenhuma", "não verifica", "Acervo do INCRA sem DNS também de uma máquina no Brasil (02/11/2026) e SIGEF com login "
     "gov.br; o espelho do CMR/FUNAI só tem parcelas em volta de terras indígenas (ADR 0016)"),
    (3, "Ambiental: CAR", "sim", "VERIFICACAO_CAR", "SICAR", "Conforme",
     "SICAR, WFS público (pipeline/fontes/sicar.py)", "parcial",
     "Existência e status do CAR; o vínculo CAR-SNCR não é verificável"),
    (4, "Trabalhista: Lista Suja", "sim", "VERIFICACAO_TRABALHO_ESCRAVO", "MTE", "Conforme",
     "Lista Suja, PDF oficial (pipeline/fontes/mte_lista_suja.py)", "verifica",
     "Por documento pseudonimizado; exige o CPF/CNPJ de cada proprietário"),
    (5, "Sobreposição: terras indígenas", "sim", "VERIFICACAO_SOBREPOSICAO_INDIGENA", "FUNAI", "Conforme",
     "FUNAI, WFS (pipeline/fontes/funai_terras_indigenas.py)", "verifica", "Sobreposição com o polígono do CAR"),
    (6, "Sobreposição: área quilombola", "sim", "VERIFICACAO_SOBREPOSICAO_QUILOMBOLA", "INCRA", "Conforme",
     "INCRA pelo CMR/FUNAI e IBGE 2022, combinados (pipeline/fontes/incra_quilombolas.py)", "verifica",
     "Base do INCRA (cadastro de 28/10/2026) e os territórios do IBGE de 31/07/2022 que o INCRA não tem (ADR 0016)"),
    (7, "Ambiental: embargos do IBAMA", "não", "VERIFICACAO_EMBARGOS_IBAMA", "IBAMA", "Conforme",
     "IBAMA, CSV público (pipeline/fontes/ibama_embargos.py)", "verifica",
     "Por documento e, com o polígono do CAR, por sobreposição (pipeline/cruzamento.py)"),
    (8, "Sobreposição: CAR x SIGEF-GEO", "não", "VERIFICACAO_SOBREPOSICAO_GEO_CAR", "CAR e SIGEF-GEO",
     "Não conforme", "nenhuma", "não verifica", "Depende do critério 2"),
    (9, "Sobreposição: unidade de conservação", "sim", "VERIFICACAO_SOBREPOSICAO_UNIDADE_CONSERVACAO", "MMA",
     "Conforme", "MMA, CNUC (pipeline/fontes/mma_unidades_conservacao.py)", "verifica",
     "Sobreposição com o polígono do CAR; APA, ARIE e RPPN como indício"),
], columns=["n", "criterio_ab_s", "obrigatorio", "codigo_interno", "fonte_ab_s", "resultado_demonstracao",
            "fonte_aberta_projeto", "cobertura_projeto", "observacao"])


def validar_uuid(texto: str) -> dict:
    """Formato 8-4-4-4-12 em hexadecimal (36 caracteres); informa também versão e variante."""
    t = (texto or "").strip().lower()
    ok = len(t) == 36 and UUID.fullmatch(t) is not None
    return {"formato_valido": ok, "versao": int(t[14], 16) if ok else None, "variante_rfc4122": ok and t[19] in "89ab"}


def procurar_uuid(texto: str) -> str | None:
    """Prefere o valor logo após 'autenticidade'; senão, o primeiro UUID do texto."""
    m = ROTULO.search(texto or "")
    if m and UUID.fullmatch(m.group(1).strip(".,;").lower()):
        return m.group(1).strip(".,;").lower()
    m = UUID.search(texto or "")
    return m.group(0).lower() if m else None


def extrair_uuid(pdf: Path) -> str | None:
    """Código de autenticidade a partir do texto do PDF (relatório com camada de texto)."""
    with pdfplumber.open(pdf) as documento:
        texto = "\n".join(p.extract_text() or "" for p in documento.pages)
    return procurar_uuid(texto)


def interpretar(status_http: int, corpo, data: str) -> str:
    """Leitura de uma resposta da API para o registro do projeto. `data` no formato DD/MM/AAAA."""
    if status_http == 200:
        return "localizado"
    if status_http == 404:
        return f"não localizado na consulta pública em {data}"
    return f"erro do serviço (HTTP {status_http}) em {data}; repetir a consulta"


def mensagem(corpo) -> str:
    if isinstance(corpo, dict):
        return str(corpo.get("message") or corpo.get("mensagem") or corpo.get("detail") or corpo.get("error") or "")
    return ""


def pseudonimizar_resposta(dados, chave: bytes) -> tuple[object, int]:
    """Troca CPF e CNPJ por HMAC-SHA256 (pipeline/documentos.py) em qualquer ponto do JSON. Devolve (dados, trocas)."""
    trocas = 0

    def hmac(texto: str) -> str:
        return "hmac:" + pseudonimizar(pd.Series([re.sub(r"\D", "", texto)]), chave).iloc[0]

    def percorrer(valor, campo=""):
        nonlocal trocas
        if isinstance(valor, dict):
            return {k: percorrer(v, k) for k, v in valor.items()}
        if isinstance(valor, list):
            return [percorrer(v, campo) for v in valor]
        if isinstance(valor, str):
            if CAMPOS_DOCUMENTO.search(campo) and re.sub(r"\D", "", valor):
                trocas += 1
                return hmac(valor)
            novo, n = CPF_CNPJ.subn(lambda m: hmac(m.group(0)), valor)
            trocas += n
            return novo
        return valor

    return percorrer(dados), trocas


def consultar(uuid: str, chave: bytes, atualizar: bool = False) -> tuple[pd.DataFrame, ResultadoFonte]:
    """Consulta os três endpoints públicos para um código de autenticidade. Uma linha por endpoint.

    Código fora do formato interrompe antes de qualquer requisição (ErroDeValidacao).
    """
    resultado = ResultadoFonte("ab_s", "API (JSON), sob demanda por relatório")
    resultado.entrada = {"servico": config.URL_AB_S_PUBLICO, "endpoints": list(config.AB_S_ENDPOINTS),
                         "requisicoes": []}
    formato = validar_uuid(uuid)
    resultado.validar("ABS_UUID_FORMATO_INVALIDO", "Código de autenticidade fora do formato UUID (8-4-4-4-12 hex)",
                      "erro", "não consulta: a API devolveria 404 ou 500 como se o relatório não existisse",
                      int(not formato["formato_valido"]), 1)
    uuid = uuid.strip().lower()
    agora = datetime.now(timezone.utc)

    def tratar(conteudo: bytes):
        try:
            dados = json.loads(conteudo)
        except ValueError:
            return conteudo, None
        dados, trocas = pseudonimizar_resposta(dados, chave)
        if not trocas:
            return conteudo, None
        return json.dumps(dados, ensure_ascii=False).encode(), f"{trocas} CPF/CNPJ trocados por HMAC-SHA256"

    linhas = []
    for endpoint in config.AB_S_ENDPOINTS:
        destino = config.DADOS_BRUTOS / "ab_s" / endpoint / f"{uuid}_{agora:%Y%m%d}.json"
        conteudo, meta = consultar_url(f"{config.URL_AB_S_PUBLICO}/{endpoint}/{uuid}", destino, atualizar=atualizar,
                                       tratar=tratar, pausa=config.PAUSA_ENTRE_CONSULTAS_S)
        try:
            corpo = json.loads(conteudo)
        except ValueError:
            corpo = None
        data = datetime.fromisoformat(meta["consultado_em_utc"]).strftime("%d/%m/%Y")
        nota = meta.get("tratamento_antes_de_gravar") or "0"
        linhas.append({"endpoint": endpoint, "status_http": meta["status_http"], "json_valido": corpo is not None,
                       "documentos_pseudonimizados": int(nota.split()[0]),
                       "situacao": interpretar(meta["status_http"], corpo, data), "mensagem": mensagem(corpo)[:200],
                       "consultado_em_utc": meta["consultado_em_utc"],
                       "arquivo": str(destino.relative_to(config.RAIZ))})
        resultado.entrada["requisicoes"].append({"endpoint": endpoint, "sha256": meta["sha256"],
                                                 "consultado_em_utc": meta["consultado_em_utc"]})
    df = pd.DataFrame(linhas)
    resultado.transformar("Uma requisição por endpoint; resposta gravada como veio, com CPF/CNPJ pseudonimizados")
    resultado.validar("ABS_RESPOSTA_NAO_JSON", "Corpo da resposta não é JSON", "alerta", "registrado como erro do serviço",
                      ~df["json_valido"], len(df))
    resultado.validar("ABS_NAO_LOCALIZADO", "Código não localizado (HTTP 404)", "alerta",
                      "registrar 'não localizado na consulta pública em [data]', nunca 'relatório falso'",
                      df["status_http"] == 404, len(df))
    resultado.validar("ABS_ERRO_SERVICO", "Erro do serviço (HTTP diferente de 200 e 404)", "alerta",
                      "repetir a consulta depois", ~df["status_http"].isin([200, 404]), len(df))
    resultado.validar("ABS_DOCUMENTO_PSEUDONIMIZADO", "CPF/CNPJ na resposta", "correcao",
                      "trocado por HMAC-SHA256 antes de gravar", int(df["documentos_pseudonimizados"].sum()), len(df))
    resultado.saida = {"registros_produzidos": len(df), "situacoes": df["situacao"].tolist()}
    resultado.status = "ok"
    return df, resultado
