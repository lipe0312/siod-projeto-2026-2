"""Registro das validações e das transformações de cada fonte."""

import logging
from dataclasses import dataclass, field

import pandas as pd

log = logging.getLogger("pipeline")

SEVERIDADES = ("erro", "descarte", "correcao", "alerta")


@dataclass
class Validacao:
    codigo: str
    descricao: str
    severidade: str
    tratamento: str
    verificados: int
    ocorrencias: int


class ErroDeValidacao(Exception):
    """Falha que impede o processamento da fonte."""

    def __init__(self, validacao: Validacao):
        self.validacao = validacao
        super().__init__(f"{validacao.codigo}: {validacao.descricao} ({validacao.ocorrencias} ocorrências)")


@dataclass
class ResultadoFonte:
    fonte: str
    tipo_dado: str
    entrada: dict = field(default_factory=dict)
    transformacoes: list = field(default_factory=list)
    validacoes: list = field(default_factory=list)
    saida: dict = field(default_factory=dict)
    status: str = "pendente"
    mensagem: str = ""

    def transformar(self, descricao: str) -> None:
        self.transformacoes.append(descricao)
        log.info("[%s] transformação: %s", self.fonte, descricao)

    def validar(self, codigo, descricao, severidade, tratamento, falhas, verificados) -> int:
        """Registra uma validação. `falhas` é uma máscara booleana ou uma contagem."""
        if severidade not in SEVERIDADES:
            raise ValueError(f"severidade desconhecida: {severidade}")
        ocorrencias = int(falhas.sum()) if hasattr(falhas, "sum") else int(falhas)
        v = Validacao(codigo, descricao, severidade, tratamento, int(verificados), ocorrencias)
        self.validacoes.append(v)
        nivel = logging.WARNING if ocorrencias and severidade != "correcao" else logging.INFO
        log.log(nivel, "[%s] %s: %d de %d | %s", self.fonte, codigo, ocorrencias, verificados, tratamento)
        if severidade == "erro" and ocorrencias:
            raise ErroDeValidacao(v)
        return ocorrencias


class Marcas:
    """Acumula códigos de alerta por registro e os junta em uma coluna de texto."""

    def __init__(self, indice: pd.Index):
        self.indice = indice
        self._mascaras: dict[str, pd.Series] = {}

    def marcar(self, codigo: str, mascara: pd.Series) -> None:
        self._mascaras[codigo] = mascara.reindex(self.indice, fill_value=False).astype(bool)

    def coluna(self) -> pd.Series:
        texto = pd.Series("", index=self.indice, dtype="object")
        for codigo, mascara in self._mascaras.items():
            texto = texto.where(~mascara, texto + codigo + ";")
        return texto.str.rstrip(";")
