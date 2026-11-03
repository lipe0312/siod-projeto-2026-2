"""Gera docs/marca/preview-direcoes.html e docs/marca/favicons/*.svg a partir da saída da skill brand-identity.
Uso: python3 preview.py <skill scripts dir> <docs/marca>
"""
import html, json, re, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import colorlib as cl

MARCA = Path(sys.argv[2])
WORK = MARCA / "agrovalid"
ST = json.loads((MARCA / "status.json").read_text())
ORDER = ["pendencia", "inconclusivo", "indicio", "sem_pendencia", "nao_verificado"]
ROLES_UI = [("background", "Fundo da página"), ("surface", "Cartões, tabela"), ("surfaceAlt", "Painel, linha alternada"),
            ("border", "Fios e divisórias"), ("text", "Texto"), ("textMuted", "Texto de apoio"),
            ("primary", "Botão principal, monograma"), ("accent", "Destaque da marca"), ("link", "Link")]
FONTS = {"A": ("Archivo", "Archivo"), "B": ("Fira Sans", "Fira Sans"), "C": ("Zilla Slab", "Source Sans 3")}
FONT_URL = ("https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@88..100,400..700"
            "&family=Fira+Sans:wght@400;600&family=Zilla+Slab:wght@700&family=Source+Sans+3:wght@400;600&display=swap")
e = html.escape


def cr(a, b):
    return cl.contrast_ratio(a, b)


def verdict(r, target):
    return f'<span class="ok">{r:.2f}</span>' if r >= target else f'<span class="bad">{r:.2f}</span>'


def recolour(svg, roles):
    """Troca data-color por fill concreto e tira atributos que só servem à skill."""
    def sub(m):
        role = m.group(1)
        return f'data-color="{role}" fill="{roles.get(role, role)}"'
    svg = re.sub(r'data-color="([^"]+)"', sub, svg)
    return svg


def square_viewbox(svg, pad=0.06):
    m = re.search(r'data-ink="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', svg)
    x0, y0, x1, y1 = map(float, m.groups())
    w, h = x1 - x0, y1 - y0
    s = max(w, h) * (1 + 2 * pad)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vb = f"{cx - s / 2:.3f} {cy - s / 2:.3f} {s:.3f} {s:.3f}"
    return re.sub(r'viewBox="[^"]+"', f'viewBox="{vb}"', svg, count=1)


def strip_meta(svg):
    svg = re.sub(r'\sdata-(?!color)[a-z-]+="[^"]*"', "", svg)
    return svg


def lockup_roles(mode_roles, pal):
    return {"primary": mode_roles["primary"], "accent": mode_roles["accent"], "text": mode_roles["text"]}


def logo_roles(x, mode, pal):
    """Cores do logo: no claro, hex exato da marca; no escuro, o passo claro da escala (o que a skill usa)."""
    r = pal["modes"][mode]
    if mode == "light":
        return {"primary": pal["brand"][0]["hex"], "accent": pal["brand"][1]["hex"], "text": r["text"]}
    if x == "C":  # marca de ferro em brasa no escuro
        return {"primary": r["accent"], "accent": r["accent"], "text": r["text"]}
    return {"primary": r["primary"], "accent": r["accent"], "text": r["text"]}


ICONS = {
    "pendencia": '<path d="M8 1.5 15 14.5H1Z"/><rect x="7.1" y="5.5" width="1.8" height="5" rx=".6" fill="var(--icon-cut)"/><circle cx="8" cy="12.3" r="1" fill="var(--icon-cut)"/>',
    "inconclusivo": '<circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M6.2 6.3a1.9 1.9 0 1 1 2.6 1.8c-.6.3-.8.6-.8 1.2v.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="11.7" r=".95"/>',
    "indicio": '<circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 1.8a6.2 6.2 0 0 1 0 12.4Z"/>',
    "sem_pendencia": '<path d="M2.5 8.5 6.3 12.2 13.6 4.2" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    "nao_verificado": '<circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-dasharray="2.6 2.2"/>',
}


def icon(s, color, size=14):
    return (f'<svg class="ico" viewBox="0 0 16 16" width="{size}" height="{size}" fill="currentColor" '
            f'style="color:{color}" aria-hidden="true">{ICONS[s]}</svg>')


# ---------------------------------------------------------------- dados fictícios da carteira (rotulados)
CARTEIRA = [
    # (situação, id, car, município/UF, ha, o que apareceu, primeiro passo, critérios)
    ("pendencia", "COOP-0142", "XX-0000000-FICT…01", "Município A/MT", 1240.0,
     "Embargo do IBAMA ativo dentro do polígono; alerta DETER após 31/12/2020",
     "Pedir ao IBAMA a revisão do embargo", "PPIPSNSNS"),
    ("pendencia", "COOP-0087", "XX-0000000-FICT…02", "Município B/PA", 610.5,
     "CAR suspenso no SICAR", "Regularizar o CAR na secretaria estadual", "PSNSSNSNS"),
    ("inconclusivo", "COOP-0233", "—", "—", None,
     "Linha sem localização: sem cod_car e sem lat/lon", "Pedir o recibo do CAR ao produtor", "QQQQQQQQQ"),
    ("inconclusivo", "COOP-0019", "—", "—", None,
     "Coordenada fora do Brasil (lat e lon trocados?)", "Conferir a coordenada na planilha", "QQQQQQQQQ"),
    ("indicio", "COOP-0310", "XX-0000000-FICT…05", "Município C/MG", 88.2,
     "Sobreposição pequena com território quilombola", "Conferir no INCRA o limite do território quilombola",
     "SISSSNSNS"),
    ("sem_pendencia", "COOP-0056", "XX-0000000-FICT…06", "Município D/MG", 42.0,
     "Nada nas fontes verificadas", "Trazer CCIR e SIGEF no atendimento", "NSSSSNSNS"),
]
CRIT_KEY = {"P": "pendencia", "Q": "inconclusivo", "I": "indicio", "S": "sem_pendencia", "N": "nao_verificado"}


def carteira(x, mode, pal, fonts):
    r = pal["modes"][mode]
    st = ST["sets"][x][mode]["status"]
    counts = {s: sum(1 for c in CARTEIRA if c[0] == s) for s in ORDER[:4]}
    placar = "".join(
        f'<div class="pl"><b style="color:{r["text"]}">{counts[s]}</b>'
        f'<span>{icon(s, st[s]["mark"], 12)} {e(st[s]["label"])}</span></div>' for s in ORDER[:4])
    rows = []
    for i, (s, pid, car, mun, ha, oque, passo, crit) in enumerate(CARTEIRA, 1):
        c = st[s]
        badge = (f'<span class="badge" style="background:{c["tint"]};color:{c["text"]}">'
                 f'{icon(s, c["text"], 12)}{e(c["label"])}</span>')
        crit_html = "".join(
            f'<i title="Critério {k + 1}: {st[CRIT_KEY[ch]]["label"]}">{icon(CRIT_KEY[ch], st[CRIT_KEY[ch]]["mark"], 11)}</i>'
            for k, ch in enumerate(crit))
        ha_s = "—" if ha is None else f"{ha:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        rows.append(
            f'<tr style="--bar:{c["mark"]}"><td class="n">{i}</td>'
            f'<td><b>{pid}</b><div class="car">{car}</div></td><td>{e(mun)}</td><td class="n">{ha_s}</td>'
            f'<td>{badge}</td><td>{e(oque)}<div class="crit">{crit_html}</div></td><td>{e(passo)}</td>'
            f'<td><a href="#" onclick="return false" style="color:{r["link"]}">ficha</a></td></tr>')
    btn = (f'<span class="btn" style="background:{r["primary"]};color:{r["onPrimary"]}">Enviar planilha</span>')
    return f'''<div class="mock" style="--bg:{r["background"]};--sf:{r["surface"]};--sa:{r["surfaceAlt"]};
--bd:{r["border"]};--tx:{r["text"]};--mu:{r["textMuted"]};--icon-cut:{r["surface"]};
font-family:'{fonts[1]}',system-ui,sans-serif">
<div class="mhead"><span class="mlogo">{LOCKUP[x][mode]}</span>
<nav><b>Carteira</b><span>Ficha do imóvel</span><span>Mudanças do mês</span></nav>{btn}</div>
<div class="mbody"><div class="eyebrow">Carteira priorizada</div>
<h4 style="font-family:'{fonts[0]}',system-ui,sans-serif">Quem atender primeiro</h4>
<p class="mu">Pré-diagnóstico com fontes públicas: não é atestado de conformidade. <em>Dados fictícios para a amostra.</em></p>
<div class="placar">{placar}</div>
<div class="tw"><table><thead><tr><th>#</th><th>Produtor / CAR</th><th>Município</th><th>ha</th><th>Resultado</th>
<th>O que apareceu · critérios</th><th>Primeiro passo</th><th></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<p class="mu legend">{"".join(f'<span>{icon(s, st[s]["mark"], 11)} {st[s]["label"]}</span>' for s in ORDER)}</p>
</div></div>'''


# ---------------------------------------------------------------- montar
LOCKUP, FAV = {}, {}
sets_json = json.loads((WORK / "sets.json").read_text())["sets"]
data = {}
for sj in sets_json:
    x = sj["identity"]["set"]["id"]
    pal = json.loads((WORK / f"sets/{x}/palette.json").read_text())
    ident = json.loads((WORK / f"sets/{x}/identity.json").read_text())
    b = WORK / f"sets/{x}/logo/build"
    lock = (b / "master-lockup-horizontal.svg").read_text()
    big = (b / "master-symbol.svg").read_text()
    small_p = b / "master-symbol-small.svg"
    small = small_p.read_text() if small_p.exists() else big
    LOCKUP[x], FAV[x] = {}, {}
    for mode in ("light", "dark"):
        roles = logo_roles(x, mode, pal)
        LOCKUP[x][mode] = strip_meta(recolour(lock, roles)).replace("<svg ", '<svg class="lockup" role="img" aria-label="AgroValid" ', 1)
        FAV[x][mode] = {
            "small": strip_meta(square_viewbox(recolour(small, roles))),
            "big": strip_meta(square_viewbox(recolour(big, roles))),
            "roles": roles,
            "parts": sorted(set(re.findall(r'data-color="([^"]+)"', small + big))),
        }
    data[x] = (sj, pal, ident)

# favicon.svg com troca claro/escuro embutida (para uso real em <link rel="icon">)
(MARCA / "favicons").mkdir(exist_ok=True)
for x in data:
    lt, dk = FAV[x]["light"], FAV[x]["dark"]
    body = re.sub(r"^<svg[^>]*>|</svg>$", "", (WORK / f"sets/{x}/logo/build/" /
                  ("master-symbol-small.svg" if (WORK / f"sets/{x}/logo/build/master-symbol-small.svg").exists()
                   else "master-symbol.svg")).read_text().strip())
    vb = re.search(r'viewBox="([^"]+)"', lt["small"]).group(1)
    css = "".join(f'[data-color="{k}"]{{fill:{v}}}' for k, v in lt["roles"].items())
    css_d = "".join(f'[data-color="{k}"]{{fill:{v}}}' for k, v in dk["roles"].items())
    (MARCA / "favicons" / f"favicon-{x}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}"><style>{css}'
        f'@media (prefers-color-scheme: dark){{{css_d}}}</style>{strip_meta(body)}</svg>\n')


def fav_block(x, pal):
    out = []
    for mode, label in (("light", "Fundo claro"), ("dark", "Fundo escuro")):
        g = pal["modes"][mode]["background"]
        f = FAV[x][mode]
        meas = " · ".join(f'{p} {cr(f["roles"][p], g):.2f}:1' for p in f["parts"] if p in f["roles"])
        out.append(f'''<div class="favrow" style="background:{g}">
<div class="fv"><div class="s16">{f["small"]}</div><span>16</span></div>
<div class="fv"><div class="s32">{f["small"]}</div><span>32</span></div>
<div class="fv"><div class="s128">{f["big"]}</div><span>128</span></div>
<div class="fv"><canvas class="px" width="16" height="16" data-svg="{e(f["small"])}"></canvas><span>16 px ampliado 4×</span></div>
<div class="fv tab"><div class="tabmock" style="background:{pal["modes"][mode]["surface"]};color:{pal["modes"][mode]["text"]}">
<div class="s16">{f["small"]}</div>AgroValid · Carteira</div><span>aba do navegador</span></div>
</div><p class="cap">{label} {g} · contraste das partes do símbolo no fundo: {meas} (meta 3:1, WCAG 1.4.11)</p>''')
    return "".join(out)


def palette_block(x, sj, pal):
    brand = sj["palette"]["brand"]
    ext = pal.get("extended") or []
    sw = "".join(f'<div class="sw"><div class="chip" style="background:{c["hex"]}"></div><b>{e(c["name"])}</b>'
                 f'<code>{c["hex"]}</code><span>{e(c["usage"])}</span>'
                 f'<span class="mu">branco {cr(c["hex"], "#ffffff"):.2f} · preto {cr(c["hex"], "#000000"):.2f}</span></div>'
                 for c in brand)
    sw += "".join(f'<div class="sw"><div class="chip" style="background:{c["hex"]}"></div><b>{e(c["name"])}</b>'
                  f'<code>{c["hex"]}</code><span>{e(c.get("usage", ""))} (cor estendida)</span>'
                  f'<span class="mu">branco {cr(c["hex"], "#ffffff"):.2f} · preto {cr(c["hex"], "#000000"):.2f}</span></div>'
                  for c in ext)
    rows = []
    for k, use in ROLES_UI:
        lt, dk = pal["modes"]["light"][k], pal["modes"]["dark"][k]
        rows.append(f'<tr><td>{use}</td><td><i class="dot" style="background:{lt}"></i><code>{lt}</code></td>'
                    f'<td><i class="dot" style="background:{dk}"></i><code>{dk}</code></td></tr>')
    return f'<div class="swatches">{sw}</div><table class="roles"><thead><tr><th>Papel na interface</th><th>Claro</th><th>Escuro</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'


def contrast_block(pal):
    pairs = [("Texto / fundo", "text", "background", 4.5), ("Texto / superfície", "text", "surface", 4.5),
             ("Texto de apoio / fundo", "textMuted", "background", 4.5),
             ("Texto de apoio / superfície", "textMuted", "surface", 4.5),
             ("Rótulo no botão / primária", "onPrimary", "primary", 4.5),
             ("Rótulo / destaque", "onAccent", "accent", 4.5), ("Link / superfície", "link", "surface", 4.5),
             ("Primária / fundo (forma)", "primary", "background", 3.0),
             ("Destaque / fundo (forma)", "accent", "background", 3.0),
             ("Fio / superfície", "border", "surface", None),
             ("Link / texto (link sem sublinhado)", "link", "text", 3.0)]
    rows = []
    for lab, f, b, t in pairs:
        cells = []
        for m in ("light", "dark"):
            r = cr(pal["modes"][m][f], pal["modes"][m][b])
            cells.append(f"<td>{verdict(r, t) if t else f'{r:.2f}'}</td>")
        rows.append(f'<tr><td>{lab}</td><td class="mu">{f"{t}:1" if t else "decorativo"}</td>{"".join(cells)}</tr>')
    return ('<table class="ct"><thead><tr><th>Par</th><th>Meta</th><th>Claro</th><th>Escuro</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def status_block(x):
    out = []
    for mode, lab in (("light", "Claro"), ("dark", "Escuro")):
        S = ST["sets"][x][mode]
        st = S["status"]
        cells = []
        for s in ORDER:
            c = st[s]
            k = c["contrast"]
            cvd = "".join(f'<i style="background:{c["cvd"][kk]}" title="{kk}"></i>' for kk in ("normal", "protan", "deutan", "tritan"))
            cells.append(f'''<div class="stc"><span class="badge" style="background:{c["tint"]};color:{c["text"]}">{icon(s, c["text"], 12)}{e(c["label"])}</span>
<div class="stline"><i class="dot" style="background:{c["mark"]}"></i><code>{c["mark"]}</code> marcador</div>
<div class="stline mu">rótulo <code>{c["text"]}</code> sobre <code>{c["tint"]}</code></div>
<div class="stline">marcador/fundo {verdict(k["mark_on_background"], 3)} · /superfície {verdict(k["mark_on_surface"], 3)}</div>
<div class="stline">rótulo/selo {verdict(k["text_on_tint"], 4.5)}</div>
<div class="cvd">{cvd}</div></div>''')
        md = S["min_delta_e"]
        pend = ST["sets"][x][mode]["pairs"]
        worst = min(pend, key=lambda p: min(p[k] for k in ("normal", "protan", "deutan", "tritan")))
        out.append(f'''<div class="stgrid" style="background:{json.loads((WORK / f"sets/{x}/palette.json").read_text())["modes"][mode]["surface"]};
color:{json.loads((WORK / f"sets/{x}/palette.json").read_text())["modes"][mode]["text"]}"><div class="stmode">{lab}</div>{"".join(cells)}</div>
<p class="cap">{lab}: menor ΔE2000 entre os cinco marcadores, normal {md["normal"]} · protanopia {md["protan"]} · deuteranopia {md["deutan"]} · tritanopia {md["tritan"]}.
Par mais próximo: {ST["sets"][x][mode]["status"][worst["a"]]["label"]} × {ST["sets"][x][mode]["status"][worst["b"]]["label"]}.
Faixa de cores por selo = visão normal, protan, deutan, tritan simulados.</p>''')
    return "".join(out)


sections, summary = [], []
REC = {"A": "Recomendada", "B": "", "C": ""}
for x, (sj, pal, ident) in data.items():
    s = sj["identity"]["set"]
    fonts = FONTS[x]
    warns = []
    sections.append(f'''<section class="dir" id="dir-{x}">
<header class="dh"><div class="dl">{x}</div><div><h2>{e(s["name"])} {"<span class='rec'>Recomendada</span>" if s["recommended"] else ""}</h2>
<p class="mech">{e(s["mechanism"])}</p>
<p class="mu"><b>Única coisa alta:</b> {e(s["expression_move"])}<br><b>Onde se afasta do óbvio:</b> {e(s["differs_by"])}</p>
<p class="mu"><b>Tipo:</b> {e(fonts[0])} (títulos e nome) · {e(fonts[1])} (texto, algarismos tabulares)</p></div></header>

<h3>Logo</h3>
<div class="logos"><div style="background:{pal["modes"]["light"]["background"]}">{LOCKUP[x]["light"]}</div>
<div style="background:{pal["modes"]["dark"]["background"]}">{LOCKUP[x]["dark"]}</div></div>
<p class="cap">{e(sj["identity"]["logo"]["concept"])} O nome é contorno da fonte (OFL), não texto vivo.</p>

<h3>Favicon</h3>{fav_block(x, pal)}

<h3>Paleta</h3>{palette_block(x, sj, pal)}

<h3>Contraste medido (WCAG 2.x)</h3>{contrast_block(pal)}

<h3>Cores de situação</h3>{status_block(x)}

<h3>Tela de exemplo · Carteira priorizada</h3>
<div class="mocks">{carteira(x, "light", pal, fonts)}{carteira(x, "dark", pal, fonts)}</div>
</section>''')
    summary.append(f'<a class="sum" href="#dir-{x}"><span class="sl">{x}</span><span class="sfav">{FAV[x]["light"]["small"]}</span>'
                   f'<b>{e(s["name"])}</b>{"<span class=rec>Recomendada</span>" if s["recommended"] else ""}'
                   f'<span class="sp">{"".join(f"<i style=background:{c["hex"]}></i>" for c in sj["palette"]["brand"])}</span>'
                   f'<span class="mu">{e(sj["palette"]["direction"])}</span></a>')

CSS = """
:root{--bg:#f4f4f1;--sf:#fff;--tx:#1b1d1a;--mu:#5b5f58;--bd:#d9dad4;--ok:#1d6b3a;--bad:#a3261b;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121411;--sf:#1b1e1a;--tx:#eef0ec;--mu:#a3a8a0;--bd:#30342e;--ok:#6fcf8f;--bad:#ff8a7a;color-scheme:dark}}
:root[data-theme=dark]{--bg:#121411;--sf:#1b1e1a;--tx:#eef0ec;--mu:#a3a8a0;--bd:#30342e;--ok:#6fcf8f;--bad:#ff8a7a;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 'Archivo',system-ui,sans-serif}
main{max-width:1240px;margin:0 auto;padding:32px 16px 80px}
h1{font-size:34px;line-height:1.1;margin:0 0 8px;letter-spacing:-.01em}h2{font-size:26px;margin:0 0 6px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mu);margin:36px 0 12px;border-top:1px solid var(--bd);padding-top:16px}
.mu{color:var(--mu)}code{font:12px ui-monospace,Menlo,monospace}.cap{font-size:13px;color:var(--mu);margin:6px 0 14px}
.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:700}.bad::after{content:" ✕"}
.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}
.toggle{border:1px solid var(--bd);background:var(--sf);color:var(--tx);border-radius:6px;padding:6px 10px;font:inherit;cursor:pointer}
.sums{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin:24px 0}
.sum{display:grid;grid-template-columns:auto auto 1fr;gap:4px 10px;align-items:center;background:var(--sf);border:1px solid var(--bd);border-radius:8px;padding:14px;color:inherit;text-decoration:none}
.sum .sl{font-weight:700;color:var(--mu)}.sfav svg{width:32px;height:32px;display:block}.sum .rec{grid-column:3}.sum .sp,.sum .mu{grid-column:1/-1;font-size:13px}
.sp i{display:inline-block;width:28px;height:14px;margin-right:4px;border-radius:2px}
.rec{display:inline-block;font-size:12px;font-weight:600;background:var(--tx);color:var(--bg);border-radius:4px;padding:1px 7px;vertical-align:middle}
.dir{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:24px;margin:28px 0}
.dh{display:flex;gap:18px}.dl{font-size:44px;font-weight:700;line-height:1;color:var(--mu)}.mech{font-size:17px;margin:4px 0 10px;max-width:70ch}
.logos{display:grid;grid-template-columns:1fr 1fr;gap:10px}.logos div{border-radius:8px;padding:32px 24px;display:flex;justify-content:center;border:1px solid var(--bd)}
.lockup{height:56px;width:auto;max-width:100%}
.favrow{display:flex;gap:28px;align-items:flex-end;padding:20px;border-radius:8px;border:1px solid var(--bd);flex-wrap:wrap}
.fv{display:flex;flex-direction:column;align-items:center;gap:6px}.fv span{font-size:11px;opacity:.7;color:#888}
.s16 svg{width:16px;height:16px;display:block}.s32 svg{width:32px;height:32px;display:block}.s128 svg{width:128px;height:128px;display:block}
canvas.px{width:64px;height:64px;image-rendering:pixelated;image-rendering:crisp-edges}
.tabmock{display:flex;gap:8px;align-items:center;font-size:12px;padding:8px 12px;border-radius:8px 8px 0 0;font-family:system-ui}
.swatches{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:14px}
.sw{display:flex;flex-direction:column;gap:2px;font-size:13px}.sw .chip{height:64px;border-radius:6px;border:1px solid var(--bd);margin-bottom:4px}
table{border-collapse:collapse;width:100%}.roles td,.roles th,.ct td,.ct th{padding:6px 8px;border-bottom:1px solid var(--bd);text-align:left;font-size:13px}
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;vertical-align:-1px;margin-right:6px;border:1px solid rgba(128,128,128,.4)}
.stgrid{display:grid;grid-template-columns:70px repeat(5,1fr);gap:10px;padding:14px;border-radius:8px;border:1px solid var(--bd);overflow-x:auto}
.stmode{font-weight:600;font-size:13px}.stc{font-size:12px;display:flex;flex-direction:column;gap:4px;min-width:150px}
.stline code{font-size:11px}.cvd{display:flex;gap:2px;margin-top:2px}.cvd i{flex:1;height:12px;border-radius:2px}
.badge{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:2px 8px 2px 6px;border-radius:4px;white-space:nowrap;align-self:flex-start}
.ico{flex:none;vertical-align:-2px}
.mocks{display:grid;grid-template-columns:1fr;gap:16px}
.mock{background:var(--bg);color:var(--tx);border-radius:8px;border:1px solid var(--bd);overflow:hidden;font-size:13px}
.mock .mu{color:var(--mu)}.mhead{display:flex;align-items:center;gap:24px;padding:12px 18px;background:var(--sf);border-bottom:1px solid var(--bd);flex-wrap:wrap}
.mhead .lockup{height:22px}.mhead nav{display:flex;gap:18px;flex:1;color:var(--mu)}.mhead nav b{color:var(--tx)}
.btn{border-radius:5px;padding:6px 12px;font-weight:600}
.mbody{padding:18px}.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--mu)}
.mbody h4{font-size:22px;margin:2px 0 4px}.placar{display:flex;gap:10px;margin:12px 0;flex-wrap:wrap}
.pl{background:var(--sf);border:1px solid var(--bd);border-radius:6px;padding:8px 14px;display:flex;flex-direction:column;min-width:120px}
.pl b{font-size:22px;font-variant-numeric:tabular-nums}.pl span{color:var(--mu);font-size:12px;display:flex;gap:5px;align-items:center}
.tw{overflow-x:auto;background:var(--sf);border:1px solid var(--bd);border-radius:6px}
.mock table th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--mu);text-align:left;padding:8px 10px;border-bottom:1px solid var(--bd);font-weight:600}
.mock table td{padding:9px 10px;border-bottom:1px solid var(--bd);vertical-align:top}
.mock tbody tr td:first-child{box-shadow:inset 3px 0 0 var(--bar)}.mock tbody tr:nth-child(even){background:var(--sa)}
.n{font-variant-numeric:tabular-nums;text-align:right}.car{font:11px ui-monospace,Menlo,monospace;color:var(--mu)}
.crit{display:flex;gap:3px;margin-top:5px}.crit i{display:inline-flex}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-top:10px}
.legend span{display:inline-flex;gap:4px;align-items:center}
.notes{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:24px}.notes li{margin:4px 0}
@media (max-width:720px){.logos{grid-template-columns:1fr}.dh{flex-direction:column;gap:4px}.dir{padding:16px}}
"""

JS = """
document.querySelectorAll('canvas.px').forEach(c=>{const img=new Image();
img.onload=()=>{const x=c.getContext('2d');x.imageSmoothingEnabled=true;x.drawImage(img,0,0,16,16)};
const s=c.dataset.svg.replace('<svg ','<svg width="16" height="16" ');
img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(s)});
const t=document.getElementById('theme');t.onclick=()=>{const r=document.documentElement;
const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
r.dataset.theme=dark?'light':'dark'};
"""

page = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AgroValid · Identidade visual</title>
<link rel="icon" href="favicons/favicon-A.svg" type="image/svg+xml">
<link rel="stylesheet" href="{FONT_URL}"><style>{CSS}</style></head><body><main>
<div class="top"><div><div class="mu">AgroValid · identidade visual · rascunho para aprovação · 03/11/2026</div>
<h1>Três direções de paleta e favicon</h1>
<p class="mu" style="max-width:75ch">Cada direção traz paleta, contraste medido nos modos claro e escuro, cinco cores de situação testadas com
daltonismo simulado, favicon AV em 16, 32 e 128 px, logo e a Carteira priorizada com dados fictícios.
Os números vêm de script; o resto é julgamento visual e está dito como tal no fim da página.</p></div>
<button class="toggle" id="theme" type="button">Alternar claro/escuro da página</button></div>
<div class="sums">{"".join(summary)}</div>
<section class="notes"><h2>Recomendação: A · Curva de nível</h2>
<p>É a direção que cumpre o briefing com menos atrito. O verde de mata quase preto e a terra roxa ficam longe tanto do verde folha
quanto do azul de fintech. O monograma é o próprio AV da fonte, sem objeto desenhado em volta, e as duas barras de nível são o único
traço de campo: dão a raiz rural sem cair no ícone de folha. Também é a única das três que o auditor da skill não marcou com nenhum
padrão típico de IA (fundo creme, terracota, dourado). Os pontos fracos: em 16 px a versão pequena fica com uma barra só e a skill aponta detalhe abaixo de 1 px; o link na cor
primária fica quase igual ao texto, então o link precisa de sublinhado (como na tela de exemplo). Mata e terra roxa foram
separadas pela luminosidade para não se confundirem com protanopia (ΔE2000 2,1 na primeira versão, 8,9 nesta).</p>
<p class="mu">B (Grão) é mais próxima e literal, com a soja pedida no briefing, mas o AV vazado fica apertado em 16 px. C (Marca de ferro)
tem mais personalidade e é a mais pecuária; a serifa grossa e o fundo de couro puxam para o tom de "fazenda" e menos para "ferramenta técnica".</p></section>
{"".join(sections)}
<section class="notes" id="honestidade"><h2>O que foi medido e o que é julgamento</h2>
<h3 style="margin-top:8px">Medido (script)</h3><ul>
<li>Contraste WCAG 2.x de cada par de cores, no claro e no escuro (fórmula de luminância relativa; colorlib da skill brand-identity e palette_audit.py). Nenhum gate da skill falhou nas três direções.</li>
<li>Cores de situação: marcador ≥ 3:1 no fundo e na superfície; rótulo ≥ 4,5:1 sobre o selo. Escolhidas por busca que maximiza a menor distância CIEDE2000 entre os cinco marcadores, com visão normal e com protanopia, deuteranopia e tritanopia simuladas (Machado 2009 e Brettel 1997). Menor distância obtida, no pior tipo de visão: @@LO@@ a @@HI@@ conforme a direção e o modo (detalhe em cada direção e em status.json).</li>
<li>Favicon e logo: contraste de cada parte do símbolo sobre o fundo; renders de 16 e 32 px e auditoria do SVG pela skill (logo_audit: sem gate; avisos de tamanho pequeno em A e B).</li>
<li>Fontes: licença OFL, cobertura dos caracteres do português e algarismos tabulares (fonts audit da skill).</li>
<li>Padrões típicos de IA: a skill compara cada cor com regiões OKLCH conhecidas (creme, terracota, dourado). A ficou livre; B e C têm o dourado/palha e C a brasa, com a justificativa do briefing registrada.</li></ul>
<h3>Julgamento visual (meu)</h3><ul>
<li>Se cada cor "parece" terra, palha, couro, cerrado ou mata; se a direção soa sóbria e técnica; se lembra ESG genérico.</li>
<li>Se o favicon "lê" como AV em 16 px (o pixel ampliado ajuda, mas a leitura é sua), e se o grão, a curva de nível ou a marca de ferro são reconhecíveis.</li>
<li>A recomendação e a escolha de matiz de cada situação (vermelho de brasa para pendência, âmbar para indício, azul-violeta para inconclusivo, verde-água para sem pendência, cinza para não verificado).</li>
<li>Distância ΔE2000 ≥ 14 é um limite prático, não norma. Ainda assim, cada situação tem ícone e texto próprios, para não depender só da cor (WCAG 1.4.1).</li></ul>
<h3>Limites</h3><ul>
<li>A simulação de daltonismo cobre dicromacia completa; não substitui teste com pessoas.</li>
<li>A página carrega as fontes do Google Fonts ao abrir; sem rede, o texto cai na fonte do sistema (o logo não muda, é contorno).</li>
<li>Os dados da carteira são fictícios. As colunas e a ordem seguem pipeline/carteira.py; "regularizar o CAR", "revisão do embargo" e "limite do território quilombola" vêm de docs/visao-do-produto.md; os passos das linhas inconclusivas e da linha sem pendência foram escritos por mim a partir das regras da planilha descritas no mesmo documento.</li>
<li>Consulta de marca no INPI ainda não foi feita (docs/visao-do-produto.md).</li></ul></section>
</main><script>{JS}</script></body></html>"""
_mins = [min(m["min_delta_e"].values()) for v in ST["sets"].values() for m in v.values()]
page = page.replace("@@LO@@", f"{min(_mins):.1f}".replace(".", ",")).replace("@@HI@@", f"{max(_mins):.1f}".replace(".", ","))
(MARCA / "preview-direcoes.html").write_text(page)
print("ok", MARCA / "preview-direcoes.html", len(page))
