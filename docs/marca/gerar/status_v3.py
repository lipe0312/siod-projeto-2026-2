"""Situações v3: semáforo (vermelho, amarelo, verde) + azul e cinza, no padrão de cor da direção C.
Mede: ícone >= 3:1 no selo e na superfície; texto do selo >= 4.5:1; distância das cores da marca; ΔE2000 entre ícones
com visão normal e protan/deutan/tritan simulados. Uso: python3 status_v3.py <scripts da skill> <saida.json>"""
import sys, json, itertools
sys.path.insert(0, sys.argv[1]); import colorlib as cl
ST = {
 "light": {"ground": ["#ffffff", "#f7f4f1"], "brand": ["#5c3621", "#ae4d15"], "s": {
   "pendencia":      ("#a51d14", "#861a11", "#fdeceb"),
   "indicio":        ("#a86200", "#774400", "#fdf1d8"),
   "sem_pendencia":  ("#2d7a47", "#1d5633", "#e6f2e9"),
   "inconclusivo":   ("#2d4f8c", "#233f70", "#e8edf6"),
   "nao_verificado": ("#6f655f", "#4d4440", "#efebe8")}},
 "dark": {"ground": ["#1d1714", "#2a221e"], "brand": ["#bc896e", "#f07c43"], "s": {
   "pendencia":      ("#f0695e", "#ffb4ab", "#3d1f1b"),
   "indicio":        ("#f2b53a", "#ffd88a", "#3a2c12"),
   "sem_pendencia":  ("#62c486", "#a8e8bb", "#1b3323"),
   "inconclusivo":   ("#8ea6ec", "#c9d5f7", "#1f2538"),
   "nao_verificado": ("#a39a93", "#d6cec8", "#332a25")}}}
out = {}
for m, d in ST.items():
    out[m] = {}
    for k, (ic, tx, tint) in d["s"].items():
        out[m][k] = {"icone": ic, "texto": tx, "selo": tint,
            "icone_selo": round(cl.contrast_ratio(ic, tint), 2),
            "icone_superficie": round(min(cl.contrast_ratio(ic, g) for g in d["ground"]), 2),
            "texto_selo": round(cl.contrast_ratio(tx, tint), 2),
            "dist_marca": round(min(cl.delta_e2000(ic, b) for b in d["brand"]), 1)}
        print(m, k, out[m][k])
    ks = list(d["s"]); ics = {k: d["s"][k][0] for k in ks}
    for kind in ("normal",) + cl.CVD_KINDS:
        sim = {k: ics[k] if kind == "normal" else cl.simulate_cvd(ics[k], kind) for k in ks}
        a, b = min(itertools.combinations(ks, 2), key=lambda p: cl.delta_e2000(sim[p[0]], sim[p[1]]))
        v = round(cl.delta_e2000(sim[a], sim[b]), 1)
        out[m].setdefault("_min_delta_e", {})[kind] = [v, a, b]
        print("  ", kind, v, a, b)
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
