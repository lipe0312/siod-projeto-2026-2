"""Configuração da API, só por variável de ambiente (nenhum segredo no código).

    AGROVALID_DATABASE_URL  URL do Postgres (local: postgresql://agrovalid:agrovalid@localhost:5434/agrovalid)
    AGROVALID_AMBIENTE      local | homologacao | producao (padrão: local). Fora do local, /docs some.
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
    ambiente: str = "local"

    @property
    def local(self) -> bool:
        return self.ambiente == "local"


def carregar() -> Configuracao:
    ambiente = os.environ.get(VARIAVEL_AMBIENTE, "local")
    if ambiente not in AMBIENTES:
        raise ConfiguracaoInvalida(f"{VARIAVEL_AMBIENTE}={ambiente!r}: use um de {', '.join(AMBIENTES)}")
    return Configuracao(url_banco=os.environ.get(VARIAVEL_URL), ambiente=ambiente)
