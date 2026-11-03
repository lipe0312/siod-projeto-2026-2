"""Cores de situação v2 (direção C · Marca de ferro): famílias de matiz do campo, luminosidade livre.
Busca a combinação que maximiza a menor ΔE2000 entre as cinco, em visão normal e em protan/deutan/tritan simulados,
com marcador >= 3:1 no fundo e na superfície e >= 10 de distância das cores da marca."""
import sys, itertools, json, random
sys.path.insert(0, sys.argv[1]); import colorlib as cl
FAM = {  # nome do campo, matizes OKLCH, cromas
 "pendencia":      ("Urucum",   [25, 30], [0.15, 0.18]),
 "inconclusivo":   ("Represa",  [235, 250], [0.06, 0.09]),
 "indicio":        ("Milho",    [70, 80], [0.12, 0.15]),
 "sem_pendencia":  ("Pasto",    [150, 165], [0.08, 0.11]),
 "nao_verificado": ("Palha seca", [60], [0.012]),
}
MODES = {"light": (["#ffffff", "#f7f4f1"], ["#5c3621", "#ae4d15"], [i/100 for i in range(32, 70, 3)]),
         "dark":  (["#1d1714", "#2a221e"], ["#bc896e", "#f07c43"], [i/100 for i in range(58, 92, 3)])}
KINDS = ("normal",) + cl.CVD_KINDS
out = {}
for m, (grounds, brand, Ls) in MODES.items():
    cands = {}
    for k, (_, hs, cs) in FAM.items():
        cands[k] = [c for c in {cl.oklch_to_hex(L, C, h) for h in hs for C in cs for L in Ls}
                    if min(cl.contrast_ratio(c, g) for g in grounds) >= 3 and
                    (k == "nao_verificado" or min(cl.delta_e2000(c, b) for b in brand) >= 10)]
    ks = list(FAM); sims = {c: {kd: (c if kd == "normal" else cl.simulate_cvd(c, kd)) for kd in KINDS}
                            for k in ks for c in cands[k]}
    def score(sel):
        return min(cl.delta_e2000(sims[a][kd], sims[b][kd]) for a, b in itertools.combinations(sel, 2) for kd in KINDS)
    random.seed(3); best = (None, -1)
    for _ in range(60):
        sel = [random.choice(cands[k]) for k in ks]; cur = score(sel); imp = True
        while imp:
            imp = False
            for i, k in enumerate(ks):
                for c in cands[k]:
                    t = sel[:]; t[i] = c; v = score(t)
                    if v > cur + 1e-9: sel, cur, imp = t, v, True
        if cur > best[1]: best = (sel, cur)
    sel, sc = best
    per = {}
    for k, c in zip(ks, sel):
        per[k] = {"nome": FAM[k][0], "hex": c, "L": round(cl.hex_to_oklch(c)[0], 3),
                  "contraste_fundo": round(cl.contrast_ratio(c, grounds[0]), 2),
                  "contraste_superficie": round(cl.contrast_ratio(c, grounds[1]), 2)}
    mins = {kd: round(min(cl.delta_e2000(sims[a][kd], sims[b][kd]) for a, b in itertools.combinations(sel, 2)), 1) for kd in KINDS}
    out[m] = {"status": per, "min_delta_e": mins}
    print(m, mins); [print("  ", k, v) for k, v in per.items()]
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
