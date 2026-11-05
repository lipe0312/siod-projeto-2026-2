"""Consultas da API: SQL parametrizado, sem ORM (ADR 0020). Rodam dentro de `banco.sessao`.

Toda consulta filtra também `organizacao_id = current_setting('app.organizacao_id', true)`, além da RLS: a política de
leitura de `diag` deixa a demonstração visível a todos, e a carteira de uma cooperativa não deve misturá-la.
Nenhuma coluna de documento é lida; `diag.evidencia.detalhes_json` fica de fora porque pode levar `documento_hash`.
"""

import psycopg
from psycopg.rows import dict_row

ORG = "current_setting('app.organizacao_id', true)"

_EXECUCAO = f"""
SELECT execucao_id, tipo, iniciada_em, terminada_em, versao_codigo
FROM diag.execucao
WHERE organizacao_id = {ORG}
ORDER BY iniciada_em DESC, execucao_id DESC
LIMIT 1"""

_EXECUCAO_POR_ID = """
SELECT execucao_id, tipo, iniciada_em, terminada_em, versao_codigo
FROM diag.execucao
WHERE execucao_id = %s"""

_FONTES = """
SELECT ec.fonte, ec.carga_id, c.iniciada_em AS data, c.status
FROM diag.execucao_carga ec
LEFT JOIN meta.carga c ON c.carga_id = ec.carga_id
WHERE ec.execucao_id = %s
ORDER BY ec.fonte"""

_COLUNAS_IMOVEL = """
    r.resultado_id, r.execucao_id, r.imovel_id, r.cod_imovel, i.nome_area, i.commodity, r.uf, r.cod_municipio,
    r.area_ha, r.situacao, r.resumo, r.prioridade, r.n_pendencias, r.n_indicios, r.n_inconclusivos,
    r.n_nao_verificados, r.n_sem_ocorrencia, r.gerado_em"""

_IMOVEIS = f"""
SELECT {_COLUNAS_IMOVEL}
FROM diag.resultado_imovel r
LEFT JOIN cad.imovel i ON i.imovel_id = r.imovel_id
WHERE r.execucao_id = %s AND r.organizacao_id = {ORG}
ORDER BY r.prioridade NULLS LAST, r.cod_imovel, r.resultado_id"""

_RESULTADO = f"""
SELECT {_COLUNAS_IMOVEL}
FROM diag.resultado_imovel r
LEFT JOIN cad.imovel i ON i.imovel_id = r.imovel_id
WHERE r.resultado_id = %s AND r.organizacao_id = {ORG}"""

_CRITERIOS = f"""
SELECT chave, criterio, criterio_ab_s, situacao, evidencia, encaminhamento, fonte, aviso
FROM diag.criterio
WHERE resultado_id = %s AND organizacao_id = {ORG}
ORDER BY criterio_ab_s NULLS LAST, chave"""

_EVIDENCIAS = f"""
SELECT evidencia_id, chave_criterio, tabela, registro_id, carga_id, classe, inter_ha, fracao_objeto, fracao_car,
       largura_m, data_imagem
FROM diag.evidencia
WHERE resultado_id = %s AND organizacao_id = {ORG}
ORDER BY chave_criterio, tabela, registro_id"""

_MUDANCAS = f"""
SELECT m.cod_imovel, m.chave, m.criterio, m.situacao_anterior, m.situacao_atual, m.data_anterior, m.data_atual,
       m.resultado_anterior_id, m.resultado_atual_id, r.execucao_id AS execucao_atual_id
FROM diag.mudanca m
JOIN diag.resultado_imovel r ON r.resultado_id = m.resultado_atual_id
WHERE m.organizacao_id = {ORG}
ORDER BY m.data_atual DESC, m.cod_imovel, m.chave"""


def _todas(conn: psycopg.Connection, consulta: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(consulta, params).fetchall()


def _uma(conn: psycopg.Connection, consulta: str, params=()) -> dict | None:
    linhas = _todas(conn, consulta, params)
    return linhas[0] if linhas else None


def _com_fontes(conn: psycopg.Connection, execucao: dict) -> dict:
    return {"execucao": execucao, "fontes": _todas(conn, _FONTES, (execucao["execucao_id"],))}


def carteira(conn: psycopg.Connection) -> dict | None:
    """Última execução da organização, com as fontes usadas e os imóveis por prioridade."""
    execucao = _uma(conn, _EXECUCAO)
    if execucao is None:
        return None
    return {**_com_fontes(conn, execucao), "imoveis": _todas(conn, _IMOVEIS, (execucao["execucao_id"],))}


def ficha(conn: psycopg.Connection, resultado_id: str) -> dict | None:
    """Resultado de um imóvel com critérios e evidências, ou None se não é da organização."""
    imovel = _uma(conn, _RESULTADO, (resultado_id,))
    if imovel is None:
        return None
    execucao = _uma(conn, _EXECUCAO_POR_ID, (imovel["execucao_id"],))
    return {**_com_fontes(conn, execucao), "imovel": imovel,
            "criterios": _todas(conn, _CRITERIOS, (resultado_id,)),
            "evidencias": _todas(conn, _EVIDENCIAS, (resultado_id,))}


def mudancas(conn: psycopg.Connection) -> dict | None:
    """Critérios que mudaram entre as duas últimas execuções de cada imóvel, com a execução mais recente."""
    execucao = _uma(conn, _EXECUCAO)
    if execucao is None:
        return None
    return {**_com_fontes(conn, execucao), "mudancas": _todas(conn, _MUDANCAS)}
