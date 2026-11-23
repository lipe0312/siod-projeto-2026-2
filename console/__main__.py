"""Console local do operador: .venv/bin/python -m console [--porta 8765] → http://127.0.0.1:8765

Só escuta em 127.0.0.1 (ADR 0027): não há opção de host, para não virar porta pública por engano.
"""

import argparse
import sys
from datetime import datetime

import uvicorn

from pipeline import config, relatorio

HOST = "127.0.0.1"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m console",
                                     description="Console local do técnico: consulta um imóvel e mostra o cruzamento.")
    parser.add_argument("--porta", type=int, default=8765, help="porta em 127.0.0.1 (padrão 8765)")
    args = parser.parse_args(argv)
    if not 1024 <= args.porta <= 65535:
        parser.error("--porta entre 1024 e 65535")
    relatorio.configurar_log(config.LOGS / f"console_{datetime.now():%Y%m%d_%H%M%S}.log")

    from console.servidor import criar_app

    print(f"Console do AgroValid em http://{HOST}:{args.porta} (Ctrl+C para encerrar)")
    uvicorn.run(criar_app(), host=HOST, port=args.porta, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
