"""Gera as fichas dos CARs de demonstração, copia para esta pasta e tira um print de cada página com o Chrome.

Roda da raiz: .venv/bin/python docs/evidencias/atividade-04/prediagnostico/01_demonstracao.py [--sem-baixar-prodes]
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
    # --sem-baixar-prodes: não inclui UF nova no lote (TerraBrasilis fora do ar); o desmatamento dela fica inconclusivo.
    indice = prediagnostico.demonstracao(baixar_prodes="--sem-baixar-prodes" not in sys.argv)
    nomes = {"index"} | set(config.CARS_DEMONSTRACAO)
    for arquivo in config.PREDIAGNOSTICO.glob("*"):
        if arquivo.suffix in (".html", ".md", ".json") and arquivo.stem in nomes:
            shutil.copy(arquivo, PASTA / arquivo.name)
    if Path(CHROME).exists():
        print_da_pagina(indice, PASTA / "index.png", 4600)
        for cod in config.CARS_DEMONSTRACAO:
            print_da_pagina(config.PREDIAGNOSTICO / f"{cod}.html", PASTA / f"{cod}.png", 4400)


if __name__ == "__main__":
    main()
