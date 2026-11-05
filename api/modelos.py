"""Modelos de resposta (ADR 0020). Nenhum tem documento: `documento_hash`, CPF e CNPJ não existem aqui.

Toda resposta de /v1 traz a execução (`execucao_id`) e as fontes usadas nela (`fonte`, `carga_id`, `data`).
Fonte com `carga_id` nulo não tinha carga quando a execução rodou: os critérios dela saem inconclusivos na ficha.
"""

from datetime import datetime

from pydantic import BaseModel


class Execucao(BaseModel):
    execucao_id: str
    tipo: str
    iniciada_em: datetime
    terminada_em: datetime | None = None
    versao_codigo: str | None = None


class FonteUsada(BaseModel):
    fonte: str
    carga_id: str | None = None
    data: datetime | None = None
    status: str | None = None


class Rastro(BaseModel):
    execucao: Execucao
    fontes: list[FonteUsada]


class Imovel(BaseModel):
    resultado_id: str
    execucao_id: str
    imovel_id: str | None = None
    cod_imovel: str | None = None
    nome_area: str | None = None
    commodity: str | None = None
    uf: str | None = None
    cod_municipio: str | None = None
    area_ha: float | None = None
    situacao: str
    resumo: str | None = None
    prioridade: int | None = None
    n_pendencias: int | None = None
    n_indicios: int | None = None
    n_inconclusivos: int | None = None
    n_nao_verificados: int | None = None
    n_sem_ocorrencia: int | None = None
    gerado_em: datetime


class Carteira(Rastro):
    imoveis: list[Imovel]


class Criterio(BaseModel):
    chave: str
    criterio: str | None = None
    criterio_ab_s: int | None = None
    situacao: str
    evidencia: str | None = None
    encaminhamento: str | None = None
    fonte: str | None = None
    aviso: str | None = None


class Evidencia(BaseModel):
    evidencia_id: str
    chave_criterio: str
    tabela: str
    registro_id: str
    carga_id: str | None = None
    classe: str | None = None
    inter_ha: float | None = None
    fracao_objeto: float | None = None
    fracao_car: float | None = None
    largura_m: float | None = None
    data_imagem: datetime | None = None


class Ficha(Rastro):
    imovel: Imovel
    criterios: list[Criterio]
    evidencias: list[Evidencia]


class Mudanca(BaseModel):
    cod_imovel: str
    chave: str
    criterio: str | None = None
    situacao_anterior: str | None = None
    situacao_atual: str | None = None
    data_anterior: datetime
    data_atual: datetime
    resultado_anterior_id: str
    resultado_atual_id: str
    execucao_atual_id: str


class Mudancas(Rastro):
    mudancas: list[Mudanca]


class Saude(BaseModel):
    banco: str


class Erro(BaseModel):
    erro: str
    request_id: str
