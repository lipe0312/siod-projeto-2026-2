"""Gera as fichas dos CARs de demonstração, copia para esta pasta e tira um print de cada página com o Chrome.

Roda da raiz: .venv/bin/python docs/evidencias/atividade-04/prediagnostico/01_demonstracao.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipeline import config, prediagnostico, relatorio  # noqa: E402

PASTA = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def print_da_pagina(html: Path, png: Path, altura: int) -> None:
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", f"--window-size=1200,{altura}",
                    f"--screenshot={png}", html.as_uri()], check=True, capture_output=True)


def main() -> None:
    relatorio.configurar_log(config.LOGS / "prediagnostico_demonstracao.log")
    indice = prediagnostico.demonstracao()
    for arquivo in config.PREDIAGNOSTICO.glob("*"):
        if arquivo.suffix in (".html", ".md", ".json"):
            shutil.copy(arquivo, PASTA / arquivo.name)
    if Path(CHROME).exists():
        print_da_pagina(indice, PASTA / "index.png", 2300)
        for cod in config.CARS_DEMONSTRACAO:
            print_da_pagina(config.PREDIAGNOSTICO / f"{cod}.html", PASTA / f"{cod}.png", 3600)


if __name__ == "__main__":
    main()
