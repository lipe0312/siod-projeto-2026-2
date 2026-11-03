"""Cores de situação do AgroValid por direção, escolhidas por busca e medidas.

Para cada direção e modo (claro/escuro), cada situação tem:
  mark  - cor sólida do marcador (ponto, barra lateral, ícone): precisa de >= 3:1 no fundo e na superfície (WCAG 1.4.11)
  text  - cor do rótulo sobre o tint: precisa de >= 4.5:1 (WCAG 1.4.3)
  tint  - fundo do selo
A busca maximiza a menor distância CIEDE2000 entre marcadores, com visão normal e com protanopia,
deuteranopia e tritanopia simuladas (Machado 2009 / Brettel 1997, via colorlib da skill).
Uso: python3 status.py <skill scripts dir> <work dir> <saida.json>
"""
import itertools, json, sys
sys.path.insert(0, sys.argv[1])
import colorlib as cl

WORK, OUT = sys.argv[2], sys.argv[3]
KINDS = ("normal",) + cl.CVD_KINDS
ORDER = ["pendencia", "inconclusivo", "indicio", "sem_pendencia", "nao_verificado"]
LABEL = {"pendencia": "Pendência", "inconclusivo": "Inconclusivo", "indicio": "Indício",
         "sem_pendencia": "Sem pendência", "nao_verificado": "Não verificado"}

# Faixas de busca (OKLCH). Mesmas famílias de matiz nas três direções, para a regra de leitura ser uma só;
# cada direção ajusta matiz e croma dentro da família.
BASE = {
    "pendencia":      {"h": [24, 30, 36], "C": [0.15, 0.18]},
    "inconclusivo":   {"h": [255, 270, 285, 300], "C": [0.07, 0.10]},
    "indicio":        {"h": [65, 72, 80], "C": [0.12, 0.15]},
    "sem_pendencia":  {"h": [150, 165, 180], "C": [0.08, 0.11]},
    "nao_verificado": {"h": None, "C": [0.0]},
}
L_LIGHT = [0.40, 0.45, 0.50, 0.55, 0.60, 0.64]
L_DARK = [0.62, 0.68, 0.74, 0.80, 0.86]


def ok(L, C, h):
    return cl.oklch_to_hex(L, C, h if h is not None else 0)


def sep(colors):
    """Menor ΔE2000 entre pares, por tipo de visão."""
    res = {}
    for k in KINDS:
        sim = [c if k == "normal" else cl.simulate_cvd(c, k) for c in colors]
        res[k] = min(cl.delta_e2000(a, b) for a, b in itertools.combinations(sim, 2))
    return res


def search(pal, mode, neutral_h):
    roles = pal["modes"][mode]
    grounds = [roles["background"], roles["surface"]]
    brand_refs = [roles["primary"], roles["accent"]]
    Ls_all = L_LIGHT if mode == "light" else L_DARK
    # A pendência fica num vermelho de brasa médio e o indício num âmbar claro, para a cor manter o sentido.
    L_FIX = {"light": {"pendencia": [0.45, 0.50, 0.55], "indicio": [0.58, 0.62, 0.66]},
             "dark": {"pendencia": [0.64, 0.68, 0.72], "indicio": [0.80, 0.84, 0.88]}}[mode]
    cands = {}
    for s, spec in BASE.items():
        lst = []
        hs = spec["h"] or [neutral_h]
        Cs = spec["C"] if spec["h"] else [0.012]
        for h in hs:
            for C in Cs:
                for L in L_FIX.get(s, Ls_all):
                    c = ok(L, C, h)
                    if min(cl.contrast_ratio(c, g) for g in grounds) < 3.0:
                        continue
                    if s != "nao_verificado" and min(cl.delta_e2000(c, b) for b in brand_refs) < 10:
                        continue  # selo não pode parecer botão da marca
                    lst.append((c, L, C, h))
        cands[s] = lst
    import random
    random.seed(7)
    sims = {s_: [{k: (c[0] if k == "normal" else cl.simulate_cvd(c[0], k)) for k in KINDS} for c in cands[s_]]
            for s_ in ORDER}
    cache = {}
    def d(i, a, j, b, k):
        key = (i, a, j, b, k)
        if key not in cache:
            cache[key] = cl.delta_e2000(sims[ORDER[i]][a][k], sims[ORDER[j]][b][k])
        return cache[key]
    def score(idx):
        worst = 1e9; norm = 1e9
        for i, j in itertools.combinations(range(len(ORDER)), 2):
            for k in KINDS:
                v = d(i, idx[i], j, idx[j], k)
                worst = min(worst, v)
                if k == "normal": norm = min(norm, v)
        return worst if norm >= 18 else worst - 100
    best, best_score = None, -1e9
    for _ in range(40):
        idx = [random.randrange(len(cands[s_])) for s_ in ORDER]
        cur = score(idx); improved = True
        while improved:
            improved = False
            for i in range(len(ORDER)):
                for a in range(len(cands[ORDER[i]])):
                    if a == idx[i]: continue
                    t = idx[:]; t[i] = a; v = score(t)
                    if v > cur + 1e-9: idx, cur, improved = t, v, True
        if cur > best_score: best, best_score = idx[:], cur
    combo = tuple(cands[ORDER[i]][best[i]] for i in range(len(ORDER)))
    return combo, sep([c[0] for c in combo])


def finish(pal, mode, combo):
    roles = pal["modes"][mode]
    out = {}
    for s, (mark, L, C, h) in zip(ORDER, combo):
        if mode == "light":
            tint = ok(0.955, min(C, 0.035) if C else 0.006, h)
            textL = min(L, 0.46)
            text = ok(textL, C, h)
            while cl.contrast_ratio(text, tint) < 4.5 and textL > 0.2:
                textL -= 0.02; text = ok(textL, C, h)
        else:
            tint = ok(0.29, min(C, 0.05) if C else 0.008, h)
            textL = max(L, 0.84)
            text = ok(textL, min(C, 0.12), h)
            while cl.contrast_ratio(text, tint) < 4.5 and textL < 0.98:
                textL += 0.02; text = ok(textL, min(C, 0.12), h)
        out[s] = {
            "label": LABEL[s], "mark": mark, "text": text, "tint": tint,
            "oklch": [round(L, 3), round(C, 3), round(h or 0, 1)],
            "contrast": {
                "mark_on_background": round(cl.contrast_ratio(mark, roles["background"]), 2),
                "mark_on_surface": round(cl.contrast_ratio(mark, roles["surface"]), 2),
                "text_on_tint": round(cl.contrast_ratio(text, tint), 2),
                "text_on_surface": round(cl.contrast_ratio(text, roles["surface"]), 2),
            },
            "cvd": {k: (mark if k == "normal" else cl.simulate_cvd(mark, k)) for k in KINDS},
            "grey_L": round(cl.hex_to_oklch(mark)[0], 3),
        }
    return out


def pair_table(st):
    rows = []
    for a, b in itertools.combinations(ORDER, 2):
        row = {"a": a, "b": b}
        for k in KINDS:
            ca, cb = st[a]["cvd"][k], st[b]["cvd"][k]
            row[k] = round(cl.delta_e2000(ca, cb), 1)
        row["dL"] = round(abs(st[a]["grey_L"] - st[b]["grey_L"]), 3)
        rows.append(row)
    return rows


result = {"method": __doc__.strip(), "sets": {}}
for x in "ABC":
    pal = json.load(open(f"{WORK}/sets/{x}/palette.json"))
    nh = cl.hex_to_oklch(pal["modes"]["light"]["textMuted"])[2]
    result["sets"][x] = {}
    for mode in ("light", "dark"):
        combo, sc = search(pal, mode, nh)
        st = finish(pal, mode, combo)
        result["sets"][x][mode] = {"status": st, "min_delta_e": {k: round(v, 1) for k, v in sc.items()},
                                   "pairs": pair_table(st)}
        print(x, mode, {k: round(v, 1) for k, v in sc.items()}, [st[s]["mark"] for s in ORDER])
json.dump(result, open(OUT, "w"), ensure_ascii=False, indent=1)
