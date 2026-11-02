"""Pré-diagnóstico fora de MG: um CAR por bioma, achado pelo ponto com a UF informada, e a ficha pelo código.

Roda da raiz: .venv/bin/python docs/evidencias/atividade-04/cobertura-e-persistencia/03_prediagnostico_brasil.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
PASTA = Path(__file__).resolve().parent
import json, time
from pipeline import prediagnostico as p
from pipeline.fontes import sicar
PONTOS = {
 "PA Paragominas (Amazônia)": ("PA", -3.10, -47.60),
 "MT Sorriso (Amazônia/Cerrado)": ("MT", -12.55, -55.70),
 "BA Juazeiro (Caatinga)": ("BA", -9.40, -40.35),
 "RS Rosário do Sul (Pampa)": ("RS", -30.90, -55.50),
 "MS Corumbá (Pantanal)": ("MS", -19.00, -57.00),
 "SP Ribeirão Preto (Mata Atlântica/Cerrado)": ("SP", -21.20, -47.80),
 "PR Cascavel (Mata Atlântica)": ("PR", -24.95, -53.45),
}
OFF = [(0,0),(0.02,0),(0,0.02),(-0.02,0),(0,-0.02),(0.05,0.05),(-0.05,-0.05)]
saida = {}
for nome, (uf, lat, lon) in PONTOS.items():
    t = time.time(); cod = None
    try:
        for dy, dx in OFF:
            df, r = sicar.consultar_ponto(lat+dy, lon+dx, uf=uf)
            df = df[df["status_imovel"] != "CA"]
            if len(df) == 1:
                cod = df["cod_imovel"].iloc[0]; break
        if not cod:
            saida[nome] = {"s": round(time.time()-t,1), "erro": "nenhum ponto caiu em exatamente 1 CAR"}
        else:
            f = p.executar(cod_imovel=cod)
            crit = {c["chave"]: (c["situacao"], c["evidencia"][:160]) for c in f["criterios"] if not c["chave"].startswith("ab_s_")}
            saida[nome] = {"s": round(time.time()-t,1), "car": cod, "resultado": f["resultado"]["situacao"],
                           "prodes": f["consulta"].get("prodes"), "criterios": crit}
    except Exception as e:
        saida[nome] = {"s": round(time.time()-t,1), "car": cod, "erro": f"{type(e).__name__}: {e}"[:400]}
    print(nome, json.dumps(saida[nome], ensure_ascii=False, default=str), flush=True)
(PASTA / "03_prediagnostico_brasil.json").write_text(json.dumps(saida, indent=1, ensure_ascii=False, default=str))
