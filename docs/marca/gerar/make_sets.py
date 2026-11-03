"""Gera docs/marca/agrovalid/sets.json com as três direções do AgroValid."""
import json, sys

OUT = sys.argv[1]

def face(family, weights, loc, case="as-is", tracking=0, features=(), fallback="system-ui, sans-serif"):
    return {"family": family, "source": "google", "license": "OFL-1.1", "weights": list(weights),
            "location": loc, "features": list(features), "case": case, "tracking": tracking,
            "fallback": fallback, "file": None}

def brand(i, name, hex_, usage):
    return {"id": f"brand-{i}", "name": name, "hex": hex_, "source": "chosen", "locked": False, "usage": usage,
            "print": {"lab_d50": None, "cmyk": None, "pantone_ref": None}}

def logo(concept, colors, tags, tracking, case="as-is", min_px=16):
    return {"type": "symbol+wordmark", "concept": concept, "symbol": "logo/symbol.svg",
            "wordmark": {"text": "AgroValid", "role": "display", "location": None, "tracking": tracking, "case": case},
            "monogram": None, "lockups": ["horizontal", "stacked"], "colors": colors, "tags": tags,
            "clear_space": {"unit": "cap-height", "multiple": 1, "inferred": True},
            "min_size": {"px": min_px, "mm": 6}, "defect": None}

# ---------------------------------------------------------------- A · Curva de nível
A_SYMBOL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<path id="av" data-glyphs="AV" data-x="50" data-baseline="60" data-cap="50" data-anchor="middle" data-color="primary"/>
<rect id="nivel-1" x="6" y="68" width="88" height="8" rx="4" data-color="accent"/>
<rect id="nivel-2" x="22" y="82" width="56" height="8" rx="4" data-color="accent"/>
</svg>"""
A_SMALL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<path id="av" data-glyphs="AV" data-x="50" data-baseline="68" data-cap="66" data-anchor="middle" data-color="primary"/>
<rect id="nivel-1" x="2" y="78" width="96" height="14" rx="7" data-color="accent"/>
</svg>"""

# ---------------------------------------------------------------- B · Grão
B_SYMBOL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<ellipse id="grao" cx="50" cy="50" rx="47" ry="38" data-color="primary"/>
<path id="av" data-glyphs="AV" data-x="50" data-baseline="66" data-cap="34" data-anchor="middle" data-op="subtract"/>
<rect id="hilo" x="40" y="74" width="20" height="5" rx="2.5" data-op="subtract"/>
</svg>"""

B_SMALL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<ellipse id="grao" cx="50" cy="50" rx="49" ry="42" data-color="primary"/>
<path id="av" data-glyphs="AV" data-x="50" data-baseline="72" data-cap="46" data-anchor="middle" data-op="subtract"/>
</svg>"""

# ---------------------------------------------------------------- C · Marca de ferro
# Λ monolinear e um V que cruza as pernas e sai para fora como chifres: AV numa marca de ferro de gado.
C_SYMBOL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<g id="ferro" data-color="primary">
<path id="a" d="M14 90 L50 14 L86 90" fill="none" stroke="#000" stroke-width="12" stroke-linejoin="miter" stroke-linecap="butt"/>
<path id="v" d="M28.63 39.88 L50 90 L71.37 39.88" fill="none" stroke="#000" stroke-width="12" stroke-linejoin="miter" stroke-linecap="butt"/>
</g>
</svg>"""

STATUS_NOTE = ("Cores de situação (pendência, inconclusivo, indício, sem pendência, não verificado) "
               "são definidas e medidas à parte, em docs/marca/status.json.")

sets = [
  {
    "identity": {
      "set": {"id": "A", "name": "Curva de nível", "recommended": True,
              "mechanism": "A planta de levantamento: o AV em grotesca técnica pousado sobre duas curvas de nível em terra, mata escura como tinta e papel de mapa como fundo.",
              "expression_move": "As duas barras de nível em terra roxa: a única forma repetida e a única cor quente da marca.",
              "differs_by": "Sem folha, sem gradiente e sem verde vivo: verde quase preto de mata e terra roxa sobre papel cinza-esverdeado, lido como mapa técnico e não como selo ESG."},
      "axes": {"warm_cool": 0, "classic_contemporary": 1, "quiet_loud": -1, "friend_authority": 1},
      "type": {"pairing_mode": "single-family",
               "display": face("Archivo", [700], {"wght": 700, "wdth": 88}, tracking=-10),
               "text": face("Archivo", [400, 600], {"wght": 400, "wdth": 100}, features=["tnum"]),
               "mono": None},
      "logo": logo("O monograma pousado sobre curvas de nível: o produto lê o terreno do imóvel antes de dizer qualquer coisa.",
                   {"av": "primary", "nivel-1": "accent", "nivel-2": "accent", "wordmark": "text"},
                   ["letterform"], -10),
      "palette_build": {"strategy": None, "accent": "#843729", "light_bg": "#eef0ec", "dark_bg": None,
                        "neutral_tint": "primary", "neutral_chroma": 0.014,
                        "extra": []},
      "defaults_used": [],
      "rationale": [
        {"claim": "Verde de mata quase preto e terra roxa vêm do pedido do briefing (terra, mata/cerrado) e ficam longe do verde neon e do azul de fintech.", "evidence": "judgement", "source": "briefing"},
        {"claim": "Archivo tem algarismos tabulares e eixo de largura; a carteira mostra área e contagem de pendências.", "evidence": "measured", "source": "fonts audit"},
        {"claim": STATUS_NOTE, "evidence": "measured", "source": "status.json"}]
    },
    "palette": {"schema": "brand-identity/palette@1", "name": "Curva de nível",
                "direction": "Mata escura e terra roxa sobre papel de levantamento.",
                "brand": [brand(1, "Mata", "#143321", "monograma, títulos, botão principal"),
                          brand(2, "Terra roxa", "#843729", "curvas de nível do símbolo, destaque pontual")],
                "feels": ["sóbrio", "técnico", "de campo"]},
    "symbol_svg": A_SYMBOL, "symbol_small_svg": A_SMALL, "wordmark_detail_svg": None
  },
  {
    "identity": {
      "set": {"id": "B", "name": "Grão", "recommended": False,
              "mechanism": "O grão de soja visto de cima: uma elipse cheia com o AV vazado e o hilo como traço, tipo humanista e paleta de cerrado e palha.",
              "expression_move": "O AV vazado no grão: a marca é uma única forma cheia.",
              "differs_by": "Verde oliva de cerrado em vez do verde folha; a palha aparece só como cor de apoio, nunca como fundo creme."},
      "axes": {"warm_cool": -2, "classic_contemporary": 0, "quiet_loud": 0, "friend_authority": -1},
      "type": {"pairing_mode": "single-family",
               "display": face("Fira Sans", [600], {"wght": 600}, tracking=-5),
               "text": face("Fira Sans", [400, 600], {"wght": 400}, features=["tnum"]),
               "mono": None},
      "logo": logo("Um grão de soja com o AV vazado: a commodity de mais volume na EUDR vira o recipiente da sigla.",
                   {"grao": "primary", "wordmark": "text"},
                   ["letterform", "negative-space", "literal-object"], -5),
      "palette_build": {"strategy": None, "accent": "#c79a3a", "light_bg": "white", "dark_bg": None,
                        "neutral_tint": "primary", "neutral_chroma": 0.018,
                        "extra": ["#6e4a2c:Couro:apoio, gráficos"]},
      "defaults_used": [
        {"id": "negative-space", "why": "O usuário pediu AV combinado a grão de soja; o vazado é a forma mais limpa de juntar os dois em 16 px."},
        {"id": "literal-object", "why": "Pedido do briefing (ícone de commodity). A soja é uma das commodities da EUDR citadas no README."},
        {"id": "gold-brass-accent", "why": "O briefing pede palha e grão; a palha fica como cor de apoio em áreas, nunca como texto nem como fundo creme."}],
      "rationale": [
        {"claim": "Oliva de cerrado (matiz amarelado, croma baixo) separa a marca do verde folha saturado.", "evidence": "judgement", "source": "briefing"},
        {"claim": STATUS_NOTE, "evidence": "measured", "source": "status.json"}]
    },
    "palette": {"schema": "brand-identity/palette@1", "name": "Grão",
                "direction": "Oliva de cerrado com palha de grão seco.",
                "brand": [brand(1, "Cerrado", "#475229", "símbolo, títulos, botão principal"),
                          brand(2, "Palha", "#c79a3a", "destaques, ilustração; nunca texto sobre branco")],
                "feels": ["próximo", "de lavoura", "claro"]},
    "symbol_svg": B_SYMBOL, "symbol_small_svg": B_SMALL, "wordmark_detail_svg": None
  },
  {
    "identity": {
      "set": {"id": "C", "name": "Marca de ferro", "recommended": False,
              "mechanism": "A marca de ferro do gado: AV monolinear de traço grosso, em que o V nasce na base e passa das pernas do A como chifres curtos; serifa grossa no nome e couro e brasa sobre fundo escuro.",
              "expression_move": "O fundo escuro de couro curtido: a marca vive em superfície escura.",
              "differs_by": "A única direção escura e pecuária; lê como ofício de fazenda, longe do visual de app."},
      "card": {"ground": "dark"},
      "axes": {"warm_cool": -1, "classic_contemporary": -2, "quiet_loud": 1, "friend_authority": 2},
      "type": {"pairing_mode": "contrast",
               "display": face("Zilla Slab", [700], {}, tracking=0, fallback="Rockwell, Georgia, serif"),
               "text": face("Source Sans 3", [400, 600], {"wght": 400}, features=["tnum"]),
               "mono": None},
      "logo": logo("O AV como marca de ferro: as pontas do V passam das pernas do A como chifres de boi.",
                   {"ferro": "primary", "wordmark": "text"},
                   ["letterform"], 0),
      "palette_build": {"strategy": None, "accent": "#d0632a", "light_bg": "white", "dark_bg": "#1d1714",
                        "neutral_tint": "primary", "neutral_chroma": 0.02,
                        "extra": ["#d9bd7e:Palha:texto de destaque no escuro"]},
      "defaults_used": [
        {"id": "terracotta-clay", "why": "A brasa é a cor do ferro de marcar em brasa, o material do conceito; o briefing pede couro e um acento de alerta."},
        {"id": "gold-brass-accent", "why": "Palha pedida no briefing; aqui só como texto de destaque sobre o fundo escuro."}],
      "rationale": [
        {"claim": "Couro e brasa vêm do briefing (couro, acento de alerta); o fundo escuro é escolha de estratégia, não de tendência.", "evidence": "judgement", "source": "briefing"},
        {"claim": STATUS_NOTE, "evidence": "measured", "source": "status.json"}]
    },
    "palette": {"schema": "brand-identity/palette@1", "name": "Marca de ferro",
                "direction": "Couro curtido e brasa de ferro sobre quase preto.",
                "brand": [brand(1, "Couro", "#5c3621", "símbolo no claro, títulos, superfícies"),
                          brand(2, "Brasa", "#d0632a", "símbolo e chamadas no escuro")],
                "feels": ["firme", "de ofício", "pecuário"]},
    "symbol_svg": C_SYMBOL, "symbol_small_svg": None, "wordmark_detail_svg": None
  },
]

DEFECTS = {"A": "em 16 px o monograma ocupava pouco do quadro",
           "B": "em 16 px o vazado do AV entupia e o hilo lia como sublinhado",
           "C": "o V cruzava alto e a marca lia como estrela"}
for st in sets:
    st["identity"]["logo"]["defect"] = DEFECTS[st["identity"]["set"]["id"]]

with open(OUT, "w") as fh:
    json.dump({"schema": "brand-identity/sets@1", "sets": sets}, fh, ensure_ascii=False, indent=1)
print("ok", OUT)
