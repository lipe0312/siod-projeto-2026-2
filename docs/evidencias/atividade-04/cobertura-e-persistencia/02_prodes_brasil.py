"""Conta os polígonos PRODES de cada bioma e ano no Brasil (WFS do TerraBrasilis, resultType=hits), para
dimensionar o PRODES em lote nacional.

Roda da raiz: .venv/bin/python docs/evidencias/atividade-04/cobertura-e-persistencia/02_prodes_brasil.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
PASTA = Path(__file__).resolve().parent
import json
from pipeline import config, wfs
camadas = {
 "amazonia_legal": ("prodes-legal-amz", "prodes-legal-amz:yearly_deforestation"),
 "amazonia_bioma": ("prodes-amazon-nb", "prodes-amazon-nb:yearly_deforestation_biome"),
 "cerrado": ("prodes-cerrado-nb", "prodes-cerrado-nb:yearly_deforestation"),
 "mata_atlantica": ("prodes-mata-atlantica-nb", "prodes-mata-atlantica-nb:yearly_deforestation"),
 "caatinga": ("prodes-caatinga-nb", "prodes-caatinga-nb:yearly_deforestation"),
 "pampa": ("prodes-pampa-nb", "prodes-pampa-nb:yearly_deforestation"),
 "pantanal": ("prodes-pantanal-nb", "prodes-pantanal-nb:yearly_deforestation"),
}
out = {}
for nome, (ws, tipo) in camadas.items():
    url = config.URL_WFS_INPE.format(workspace=ws)
    out[nome] = {}
    for ano in range(2019, 2028):
        try:
            out[nome][ano] = wfs.contar(url, tipo, f"year={ano}")
        except Exception as e:
            out[nome][ano] = f"erro {type(e).__name__}"
    print(nome, out[nome], flush=True)
(PASTA / "02_prodes_brasil.json").write_text(json.dumps(out, indent=1))
