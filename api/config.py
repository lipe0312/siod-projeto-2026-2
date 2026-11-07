"""Configuração da API, só por variável de ambiente (nenhum segredo no código).

    AGROVALID_DATABASE_URL  URL do Postgres (local: postgresql://agrovalid:agrovalid@localhost:5434/agrovalid)
    AGROVALID_AMBIENTE      local | homologacao | producao. Falha fechada: ausente, /docs fica desligado e nenhuma
                            chave é aceita; valor desconhecido é recusado na partida.
"""

import os
from dataclasses import dataclass

VARIAVEL_URL = "AGROVALID_DATABASE_URL"
VARIAVEL_AMBIENTE = "AGROVALID_AMBIENTE"
AMBIENTES = ("local", "homologacao", "producao")


class ConfiguracaoInvalida(Exception):
    pass


@dataclass(frozen=True)
class Configuracao:
    url_banco: str | None
    ambiente: str | None = None  # None = não declarado: nada de /docs e nenhuma chave aceita

    @property
    def local(self) -> bool:
        """Só quando declarado explicitamente; ausente nunca vira local."""
        return self.ambiente == "local"


def carregar() -> Configuracao:
    ambiente = os.environ.get(VARIAVEL_AMBIENTE) or None
    if ambiente is not None and ambiente not in AMBIENTES:
        raise ConfiguracaoInvalida(f"{VARIAVEL_AMBIENTE}={ambiente!r}: use um de {', '.join(AMBIENTES)}")
    return Configuracao(url_banco=os.environ.get(VARIAVEL_URL), ambiente=ambiente)
