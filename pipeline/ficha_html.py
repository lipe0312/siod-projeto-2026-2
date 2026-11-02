"""Ficha do pré-diagnóstico em HTML: uma página só, sem dependência externa, com o mapa do imóvel em SVG."""

from html import escape

import pandas as pd
import shapely

from pipeline import config, vetor
from pipeline.fontes import sicar

COR_SITUACAO = {"pendência": "pend", "indício": "ind", "sem ocorrência": "ok", "não verificado": "nv",
                "inconclusivo": "inc", "com pendência": "pend", "com indício": "ind",
                "sem pendência nas fontes verificadas": "ok"}

SIMBOLO = {"pendência": "✕", "indício": "!", "sem ocorrência": "✓", "não verificado": "?", "inconclusivo": "…"}
NOME_BIOMA = {"amazonia": "Amazônia", "caatinga": "Caatinga", "cerrado": "Cerrado", "mata_atlantica": "Mata Atlântica",
              "pampa": "Pampa", "pantanal": "Pantanal"}
VERIFICADOS = ("car", "embargo", "desmatamento", "lista_suja", "terra_indigena", "quilombola", "unidade_conservacao")
NOME_CURTO = {"car": "CAR", "embargo": "Embargo IBAMA", "desmatamento": "Desmatamento pós-2020",
              "lista_suja": "Lista Suja", "terra_indigena": "Terra indígena", "quilombola": "Quilombola",
              "unidade_conservacao": "Unidade de conservação"}
# Áreas protegidas no mapa: (chave da evidência, letra, cor).
PROTEGIDAS = (("terra_indigena", "T", "var(--ti)"), ("quilombola", "Q", "var(--tq)"),
              ("unidade_conservacao", "U", "var(--uc)"))

EXPLICACAO = [
    ("pendência", "Encontrada numa fonte oficial e impede crédito rural ou venda sob a EUDR."),
    ("indício", "Algo foi encontrado, mas precisa de conferência antes de virar pendência."),
    ("sem ocorrência", "A fonte foi consultada e não há nada contra o imóvel."),
    ("não verificado", "Não há fonte aberta integrada; nunca é lido como “conforme”."),
    ("inconclusivo", "Falta uma entrada (o CAR não foi localizado) ou a fonte não respondeu; nunca é lido como "
                     "“sem ocorrência”."),
]

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--tx:#1d1d1b;--mut:#66645e;--bd:#e2e0d8;--car:#2f7d4f;--carf:rgba(47,125,79,.08);
--emb:#c0392b;--alt:#d9822b;--prd:#7b4fb0;--ti:#8d5524;--tq:#0f6e78;--uc:#3d7a1f;--pend:#b3261e;--pendb:#fbe9e7;--ind:#8a5a00;--indb:#fdf1d8;--ok:#1e6b3c;
--okb:#e3f2e8;--nv:#55575c;--nvb:#ecedef;--inc:#3b4a8a;--incb:#e6e9f6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161614;--card:#1f1f1c;--tx:#ecebe6;
--mut:#a3a199;--bd:#34332f;--car:#5fbf86;--carf:rgba(95,191,134,.10);--emb:#ff7b6b;--alt:#f3a75a;--prd:#b592e6;
--ti:#d9a066;--tq:#5cc6d0;--uc:#8fd16a;--pend:#ff8a80;--pendb:#3a1f1c;--ind:#f2c46b;--indb:#352a14;--ok:#7fd3a0;--okb:#1a2e22;--nv:#b6b8bd;--nvb:#2a2b2e;
--inc:#9fb0f2;--incb:#1f2440}}
:root[data-theme="dark"]{--bg:#161614;--card:#1f1f1c;--tx:#ecebe6;--mut:#a3a199;--bd:#34332f;--car:#5fbf86;
--carf:rgba(95,191,134,.10);--emb:#ff7b6b;--alt:#f3a75a;--prd:#b592e6;--ti:#d9a066;--tq:#5cc6d0;--uc:#8fd16a;--pend:#ff8a80;--pendb:#3a1f1c;--ind:#f2c46b;
--indb:#352a14;--ok:#7fd3a0;--okb:#1a2e22;--nv:#b6b8bd;--nvb:#2a2b2e;--inc:#9fb0f2;--incb:#1f2440}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
main{max-width:1120px;margin:0 auto;padding:28px 16px 60px}
h1{font:600 26px/1.2 Georgia,serif;margin:4px 0 6px}h2{font:600 18px/1.3 Georgia,serif;margin:0 0 12px}
.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:var(--mut)}
.mut{color:var(--mut)}.mono{font-family:Menlo,Consolas,monospace;font-size:13px;word-break:break-all}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:20px;margin-top:18px}
.grid{display:grid;grid-template-columns:1.1fr .9fr;gap:18px}@media(max-width:860px){.grid{grid-template-columns:1fr}}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:13px;font-weight:600;white-space:nowrap}
.pend{color:var(--pend);background:var(--pendb)}.ind{color:var(--ind);background:var(--indb)}
.ok{color:var(--ok);background:var(--okb)}.nv{color:var(--nv);background:var(--nvb)}.inc{color:var(--inc);background:var(--incb)}
.resultado{display:flex;gap:16px;align-items:center;flex-wrap:wrap}.resultado .badge{font-size:16px;padding:6px 16px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.fatos{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:14px}
.fato b{display:block;font-size:18px}.fato span{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.tabela{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--bd);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
svg.mapa{width:100%;height:auto;background:var(--bg);border-radius:8px;border:1px solid var(--bd)}
.legenda{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin-top:10px}
.legenda i{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:6px}
.como dt{margin-top:8px}.como dd{margin:2px 0 0;color:var(--mut)}
.aviso{border-left:4px solid var(--ind);padding:10px 14px;background:var(--indb);border-radius:6px;margin-top:18px}
.cobertura{font-size:12.5px;color:var(--ind);margin-top:6px}
a{color:var(--inc)}
.fluxo{display:grid;grid-template-columns:1fr 28px 230px;gap:10px;align-items:stretch;margin-top:6px}
.passos{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
@media(max-width:860px){.fluxo{grid-template-columns:1fr}.fluxo .seta{transform:rotate(90deg)}}
.passo{border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:4px;min-height:96px}
.passo .ico{font-size:22px;font-weight:800;line-height:1}.passo b{font-size:14px;color:var(--tx)}
.passo small{font-size:12.5px;color:var(--mut);line-height:1.35}
.seta{display:flex;align-items:center;justify-content:center;font-size:24px;color:var(--mut)}
.veredito{border-radius:10px;padding:12px;display:flex;flex-direction:column;justify-content:center;gap:4px;
border:2px solid currentColor}.veredito b{font-size:18px}.veredito small{color:var(--mut);font-size:12.5px}
.regras{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;font-size:13px}
.regras span{padding:3px 10px;border-radius:999px;border:1px solid var(--bd);color:var(--mut)}
.regras span.vale{border-color:currentColor;font-weight:600}
.nvlinha{margin-top:10px;padding:8px 12px;border-radius:8px;font-size:13px}
svg.tempo{width:100%;height:auto;margin-top:6px}
.matriz td,.matriz th{text-align:center;padding:7px 5px}.matriz th{font-size:10.5px;letter-spacing:.03em}
.matriz td:first-child,.matriz th:first-child{text-align:left;min-width:210px}.matriz td{font-size:13.5px}
.matriz .badge{white-space:normal;max-width:140px;line-height:1.25}.matriz .confere{white-space:nowrap}
.ponto{display:inline-flex;width:26px;height:26px;border-radius:50%;align-items:center;justify-content:center;
font-weight:800;font-size:13px}
.confere{font-size:13px;font-weight:700}.confere.sim{color:var(--ok)}.confere.nao{color:var(--pend)}
.placar{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin:4px 0 14px}
.placar b{font:600 32px/1 Georgia,serif}
.anos{display:flex;gap:4px;flex-wrap:wrap}.anos span{font-size:12px;padding:2px 7px;border-radius:6px;
background:var(--nvb);color:var(--nv)}.anos span.pub{background:var(--okb);color:var(--ok)}
.anos span.novo{outline:2px solid var(--ok)}
"""


def _badge(situacao: str) -> str:
    return f'<span class="badge {COR_SITUACAO.get(situacao, "nv")}">{escape(situacao)}</span>'


def _num(v, casas=1) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data(v) -> str:
    return "—" if v is None or pd.isna(v) else pd.Timestamp(v).strftime("%d/%m/%Y")


def _caminho(geom, transformar) -> str:
    partes = []
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type == "Polygon":
            for anel in [g.exterior, *g.interiors]:
                pts = [transformar(x, y) for x, y in anel.coords]
                partes.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        elif hasattr(g, "geoms"):
            partes.append(_caminho(g, transformar))
    return "".join(partes)


def mapa(ficha: dict, largura: int = 640) -> str:
    """CAR, embargos, alertas DETER e polígonos PRODES em SVG, com o número de cada evidência das tabelas."""
    car = sicar.projetar(vetor.tornar_valida(shapely.from_wkt(ficha["geometria_car"])))
    x0, y0, x1, y1 = car.bounds
    margem = 0.12 * max(x1 - x0, y1 - y0)
    x0, y0, x1, y1 = x0 - margem, y0 - margem, x1 + margem, y1 + margem
    escala = largura / (x1 - x0)
    altura = (y1 - y0) * escala

    def transformar(x, y):
        return (x - x0) * escala, (y1 - y) * escala

    def desenhar(wkt):
        return _caminho(sicar.projetar(vetor.tornar_valida(shapely.from_wkt(wkt))), transformar)

    camadas, rotulos = [], []
    ev = ficha["evidencias"]
    for chave, letra, cor in PROTEGIDAS:  # embaixo de tudo: são grandes; recortadas à vista para o SVG ficar leve
        df = ev.get(chave, pd.DataFrame())
        for i, r in enumerate(df.itertuples(), 1):
            g = sicar.projetar(vetor.tornar_valida(shapely.from_wkt(r.geometria_wkt)))
            fraco = ' opacity=".45"' if getattr(r, "classe", "") == "tangente" else ""
            if g.geom_type in ("Point", "MultiPoint"):
                p = g.centroid
            else:
                g = shapely.clip_by_rect(g, x0, y0, x1, y1)
                if g.is_empty:
                    continue
                camadas.append(f'<path d="{_caminho(g, transformar)}" fill="{cor}" fill-opacity=".12" stroke="{cor}" '
                               f'stroke-width="2" stroke-dasharray="8 4" fill-rule="evenodd"{fraco}/>')
                p = g.representative_point()
            px, py = transformar(p.x, p.y)
            rotulos.append(f'<g{fraco}><rect x="{px - 13:.1f}" y="{py - 10:.1f}" width="26" height="20" rx="4" '
                           f'fill="var(--card)" stroke="{cor}" stroke-width="2"/><text x="{px:.1f}" y="{py + 4:.1f}" '
                           f'text-anchor="middle" font-size="11" font-weight="700" fill="{cor}">{letra}{i}</text></g>')
    estilos = [("prodes", "P", "var(--prd)", "var(--prd)", 'stroke-dasharray="5 3" fill-opacity=".22"'),
               ("alertas", "A", "var(--alt)", "var(--alt)", 'fill-opacity=".35"'),
               ("embargos", "E", "var(--emb)", "url(#hach)", "")]
    for chave, letra, cor, preenchimento, extra in estilos:
        df = ev.get(chave, pd.DataFrame())
        for i, r in enumerate(df.itertuples(), 1):
            wkt = getattr(r, "geometria_wkt", None)
            if not isinstance(wkt, str):
                continue
            fraco = ' opacity=".45"' if getattr(r, "classe", "") == "tangente" else ""
            camadas.append(f'<path d="{desenhar(wkt)}" fill="{preenchimento}" stroke="{cor}" stroke-width="1.5" '
                           f'fill-rule="evenodd" {extra}{fraco}/>')
            p = sicar.projetar(shapely.from_wkt(wkt)).representative_point()
            x, y = transformar(p.x, p.y)
            rotulos.append(f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="var(--card)" stroke="{cor}" '
                           f'stroke-width="2"/><text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11" '
                           f'font-weight="700" fill="{cor}">{letra}{i}</text></g>')
    # Barra de escala: 10% da largura, arredondada para um valor redondo em metros.
    alvo = (x1 - x0) * 0.2
    passo = next(v for v in (50, 100, 200, 250, 500, 1000, 2000, 5000, 10000, 20000) if v >= alvo * 0.5)
    barra = passo * escala
    rotulo_escala = f"{passo // 1000} km" if passo >= 1000 else f"{passo} m"
    return f"""<svg class="mapa" viewBox="0 0 {largura} {altura:.0f}" role="img"
aria-label="Mapa do imóvel com as evidências encontradas">
<defs><pattern id="hach" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
<rect width="7" height="7" fill="var(--emb)" fill-opacity=".18"/><line x1="0" y1="0" x2="0" y2="7" stroke="var(--emb)"
stroke-width="2.5"/></pattern><clipPath id="vista"><rect width="{largura}" height="{altura:.0f}"/></clipPath></defs>
<g clip-path="url(#vista)">
<path d="{_caminho(car, transformar)}" fill="var(--carf)" stroke="var(--car)" stroke-width="2.5" fill-rule="evenodd"/>
{''.join(camadas)}{''.join(rotulos)}</g>
<g transform="translate(16,{altura - 18:.0f})"><rect width="{barra:.1f}" height="5" fill="var(--tx)"/>
<text y="-6" font-size="12" fill="var(--tx)">{rotulo_escala}</text></g>
<text x="{largura - 16}" y="26" text-anchor="end" font-size="14" font-weight="700" fill="var(--tx)">N ↑</text>
</svg>"""


def _tabela(cabecalho: list[str], linhas: list[list[str]], vazio: str) -> str:
    if not linhas:
        return f'<p class="mut">{escape(vazio)}</p>'
    th = "".join(f"<th>{escape(c)}</th>" for c in cabecalho)
    corpo = "".join("<tr>" + "".join(linha) + "</tr>" for linha in linhas)
    return f'<div class="tabela"><table><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table></div>'


def _td(v, n=False) -> str:
    return f'<td class="n">{v}</td>' if n else f"<td>{v}</td>"


def _evidencias(ev: dict) -> str:
    emb = [[_td(f"<b>E{i}</b>"), _td("TAD " + escape(f"{r.num_tad}-{r.ser_tad}" if pd.notna(r.ser_tad) else str(r.num_tad))), _td(_data(r.data_embargo)),
            _td(escape(str(r.como))), _td(escape(str(r.classe))),
            _td(_num(r.fracao_objeto * 100, 0) + "%" if pd.notna(r.fracao_objeto) else "—", True),
            _td(escape(str(r.descricao_infracao)) if pd.notna(r.descricao_infracao) else "—")]
           for i, r in enumerate(ev["embargos"].itertuples(), 1)]
    alt = [[_td(f"<b>A{i}</b>"), _td(_data(r.data_imagem)), _td(escape(str(r.classe_deter))),
            _td(_num(r.inter_ha), True), _td(_num(r.fracao_objeto * 100, 0) + "%", True), _td(escape(str(r.classe))),
            _td(escape(str(r.situacao_prodes)) + (f" ({escape(r.anos_prodes)})" if r.anos_prodes else ""))]
           for i, r in enumerate(ev["alertas"].itertuples(), 1)]
    prd = [[_td(f"<b>P{i}</b>"), _td(str(r.ano_prodes)), _td(_data(r.data_imagem)), _td(escape(str(r.bioma))),
            _td(_num(r.inter_ha), True), _td(_num(r.fracao_objeto * 100, 0) + "%", True), _td(escape(str(r.classe)))]
           for i, r in enumerate(ev["prodes"].itertuples(), 1)]
    return f"""
<section class="card"><h2>Embargos do IBAMA</h2>{_tabela(
        ["#", "Termo", "Data", "Encontrado por", "Classe", "% no imóvel", "Infração"], emb,
        "Nenhum embargo encontrado pelo polígono, pela coordenada ou pelo documento.")}</section>
<section class="card"><h2>Alertas DETER (desde 01/01/2021)</h2>{_tabela(
        ["#", "Data da imagem", "Classe DETER", "ha no imóvel", "% do alerta", "Classe", "PRODES"], alt,
        "Nenhum alerta DETER toca o imóvel.")}</section>
<section class="card"><h2>PRODES após 2020</h2>{_tabela(
        ["#", "Ano PRODES", "Data da imagem", "Bioma", "ha no imóvel", "% do polígono", "Classe"], prd,
        "Nenhum polígono PRODES de 2021 em diante toca o imóvel.")}
<p class="mut">O ano PRODES 2021 vai de 01/08/2020 a 31/07/2021 e começa antes da data de corte: sozinho, conta como
indício. De 2022 em diante, o desmatamento é posterior a 31/12/2020.</p></section>
{_evidencias_protegidas(ev)}"""


def _onde(r) -> list[str]:
    if r.classe == "ponto dentro":
        return [_td("—", True), _td("—", True), _td("ponto dentro")]
    return [_td(_num(r.inter_ha), True), _td(_num(r.fracao_car * 100, 1) + "%", True), _td(escape(str(r.classe)))]


def _evidencias_protegidas(ev: dict) -> str:
    vazio = pd.DataFrame()
    ti = [[_td(f"<b>T{i}</b>"), _td(escape(str(r.nome))), _td(escape(str(r.fase))), _td(escape(str(r.etnia))),
           *_onde(r), _td(_data(r.data_atualizacao))] for i, r in enumerate(ev.get("terra_indigena", vazio).itertuples(), 1)]
    tq = [[_td(f"<b>Q{i}</b>"), _td(escape(str(r.nome))), _td(escape(str(r.situacao).capitalize())),
           _td(escape(str(getattr(r, "base", "IBGE 2022")))), *_onde(r)]
          for i, r in enumerate(ev.get("quilombola", vazio).itertuples(), 1)]
    uc = [[_td(f"<b>U{i}</b>"), _td(escape(str(r.nome))), _td(escape(str(r.categoria))), _td(escape(str(r.grupo))),
           _td(escape(str(r.esfera))), *_onde(r)] for i, r in enumerate(ev.get("unidade_conservacao", vazio).itertuples(), 1)]
    cab = ["ha no imóvel", "% do imóvel", "Classe"]
    return f"""<section class="card"><h2>Áreas protegidas</h2>
<h3 style="font-size:15px;margin:4px 0 8px">Terras indígenas (FUNAI)</h3>{_tabela(
        ["#", "Terra indígena", "Fase", "Etnia", *cab, "Atualizada em"], ti, "Nenhuma terra indígena toca o imóvel.")}
<h3 style="font-size:15px;margin:16px 0 8px">Territórios quilombolas (INCRA e IBGE 2022)</h3>{_tabela(
        ["#", "Território", "Situação", "Base", *cab], tq, "Nenhum território quilombola delimitado toca o imóvel.")}
<h3 style="font-size:15px;margin:16px 0 8px">Unidades de conservação (CNUC/MMA)</h3>{_tabela(
        ["#", "Unidade", "Categoria", "Grupo", "Esfera", *cab], uc, "Nenhuma unidade de conservação toca o imóvel.")}
<p class="mut">Classe: sobreposição atinge ao menos 5% do imóvel ou uma faixa mais larga que 30 m; tangente é contato de
borda (diferença de desenho) e não conta. APA, ARIE e RPPN admitem propriedade privada: a sobreposição é indício.</p>
</section>"""


def _curto(texto: str, limite: int = 70) -> str:
    """Primeiro trecho da evidência (antes de ':' ou ';'), para caber num cartão."""
    trecho = texto.split(":")[0].split(";")[0].split(" · ")[0].strip()
    return trecho if len(trecho) <= limite else trecho[:limite - 1] + "…"


def como_se_formou(ficha: dict) -> str:
    """Os quatro critérios verificados viram o resultado: um cartão por critério, uma seta e o veredito."""
    por_chave = {c["chave"]: c for c in ficha["criterios"]}
    res = ficha["resultado"]
    passos = []
    for chave in VERIFICADOS:
        c = por_chave.get(chave)
        if not c:
            continue
        cls = COR_SITUACAO[c["situacao"]]
        aviso = '<small class="cobertura">⚠ sem cobertura recente</small>' if c.get("aviso") else ""
        passos.append(f'<div class="passo {cls}"><span class="ico">{SIMBOLO[c["situacao"]]}</span>'
                      f'<b>{NOME_CURTO[chave]}</b><small>{escape(c["situacao"])} · {escape(_curto(c["evidencia"]))}'
                      f'</small>{aviso}</div>')
    cls = COR_SITUACAO.get(res["situacao"], "nv")
    regras = [("com pendência", "1 pendência basta"), ("inconclusivo", "sem pendência, 1 inconclusivo"),
              ("com indício", "sem pendência, 1 indício"), ("sem pendência nas fontes verificadas", "nada encontrado")]
    chips = "".join(f'<span class="{COR_SITUACAO[r] + " vale" if r == res["situacao"] else ""}">{escape(t)} → '
                    f'{escape(r)}</span>' for r, t in regras)
    n_nv = sum(c["situacao"] == "não verificado" and c["chave"] not in VERIFICADOS for c in ficha["criterios"])
    return f"""<section class="card"><h2>Como o resultado foi formado</h2>
<div class="fluxo"><div class="passos">{''.join(passos)}</div><div class="seta">→</div>
<div class="veredito {cls}"><span class="mut" style="font-size:12px">RESULTADO</span><b>{escape(res["situacao"])}</b>
<small>{escape(res["resumo"])}</small></div></div>
<div class="regras">{chips}</div>
<div class="nvlinha nv">? {n_nv} critérios do AB+S sem fonte aberta: <b>não verificados</b>, nunca lidos como conformes</div>
</section>"""


def linha_do_tempo(ficha: dict, largura: int = 1040) -> str:
    """Datas das evidências diante da data de corte da EUDR e do último ano PRODES publicado."""
    ev = ficha["evidencias"]
    gerado = pd.Timestamp(ficha["consulta"]["gerado_em"])
    inicio, fim = pd.Timestamp(f"{config.PRODES_DESDE}-01-01"), pd.Timestamp(f"{gerado.year + 1}-01-01")
    esq, dir_, topo, faixa = 128, 16, 46, 46
    faixas = [("Embargos IBAMA", "embargos", "E", "data_embargo", "var(--emb)"),
              ("Alertas DETER", "alertas", "A", "data_imagem", "var(--alt)"),
              ("PRODES", "prodes", "P", "data_imagem", "var(--prd)")]
    altura = topo + faixa * len(faixas) + 34

    def x(d):
        return esq + (pd.Timestamp(d) - inicio) / (fim - inicio) * (largura - esq - dir_)

    corte = x(config.DATA_CORTE_EUDR)
    partes = [f'<rect x="{esq}" y="{topo - 8}" width="{corte - esq:.1f}" height="{faixa * 3 + 8}" fill="var(--nvb)" '
              f'opacity=".6"/>',
              f'<rect x="{corte:.1f}" y="{topo - 8}" width="{largura - dir_ - corte:.1f}" height="{faixa * 3 + 8}" '
              f'fill="var(--pendb)" opacity=".55"/>',
              f'<text x="{(esq + corte) / 2:.0f}" y="{topo - 16}" text-anchor="middle" font-size="12" '
              f'fill="var(--mut)">antes do corte: não conta</text>',
              f'<text x="{(corte + largura) / 2:.0f}" y="{topo - 16}" text-anchor="middle" font-size="12" '
              f'fill="var(--pend)" font-weight="600">depois de 31/12/2020: conta para a EUDR</text>']
    ultimo = (ficha["consulta"].get("prodes") or {}).get("ultimo_ano_do_imovel")
    if ultimo:
        xu = x(f"{ultimo}-07-31")
        if xu < largura - dir_:
            partes.append(f'<rect x="{xu:.1f}" y="{topo + faixa * 2 - 4}" width="{largura - dir_ - xu:.1f}" '
                          f'height="{faixa}" fill="url(#aguarda)"/>'
                          f'<line x1="{xu:.1f}" x2="{xu:.1f}" y1="{topo - 8}" y2="{topo + faixa * 3}" stroke="var(--prd)" '
                          f'stroke-dasharray="3 3"/><text x="{xu - 4:.1f}" y="{topo + faixa * 3 + 30}" '
                          f'text-anchor="end" font-size="11" fill="var(--prd)">PRODES publicado até 31/07/{ultimo}'
                          f'</text>')
    for ano in range(inicio.year, fim.year + 1):
        xa = x(f"{ano}-01-01")
        partes.append(f'<line x1="{xa:.1f}" x2="{xa:.1f}" y1="{topo + faixa * 3}" y2="{topo + faixa * 3 + 5}" '
                      f'stroke="var(--mut)"/>')
        if ano < fim.year:
            partes.append(f'<text x="{x(f"{ano}-07-01"):.1f}" y="{topo + faixa * 3 + 17}" text-anchor="middle" '
                          f'font-size="11" fill="var(--mut)">{ano}</text>')
    partes.append(f'<line x1="{esq}" x2="{largura - dir_}" y1="{topo + faixa * 3}" y2="{topo + faixa * 3}" '
                  f'stroke="var(--bd)"/>')
    for k, (nome, chave, letra, coluna, cor) in enumerate(faixas):
        y = topo + faixa * k + faixa / 2 - 4
        partes.append(f'<text x="{esq - 10}" y="{y + 4:.0f}" text-anchor="end" font-size="12.5" fill="var(--tx)" '
                      f'font-weight="600">{nome}</text>')
        df = ev.get(chave, pd.DataFrame())
        pontos = sorted((x(d), i, getattr(r, "classe", "") == "tangente")
                        for i, (r, d) in enumerate(zip(df.itertuples(), df.get(coluna, [])), 1) if pd.notna(d))
        grupos = []
        for px, i, fraco in pontos:  # marcadores a menos de 26 px viram um só ("A1–A8")
            if grupos and px - grupos[-1][-1][0] < 26:
                grupos[-1].append((px, i, fraco))
            else:
                grupos.append([(px, i, fraco)])
        for g in grupos:
            ids = [i for _, i, _ in g]
            rotulo = f"{letra}{ids[0]}" if len(ids) == 1 else f"{letra}{min(ids)}–{letra}{max(ids)}"
            cx = sum(p for p, _, _ in g) / len(g)
            w = 10 + 7.2 * len(rotulo)
            op = ' opacity=".45"' if all(f for _, _, f in g) else ""
            partes.append(f'<g{op}><rect x="{cx - w / 2:.1f}" y="{y - 11:.1f}" width="{w:.1f}" height="22" rx="11" '
                          f'fill="var(--card)" stroke="{cor}" stroke-width="2"/><text x="{cx:.1f}" y="{y + 4:.1f}" '
                          f'text-anchor="middle" font-size="11.5" font-weight="700" fill="{cor}">{rotulo}</text></g>')
    partes.append(f'<line x1="{corte:.1f}" x2="{corte:.1f}" y1="{topo - 8}" y2="{topo + faixa * 3 + 5}" '
                  f'stroke="var(--pend)" stroke-width="2.5"/><text x="{corte + 4:.1f}" y="{topo + faixa * 3 + 30}" '
                  f'font-size="11" font-weight="700" fill="var(--pend)">corte EUDR</text>')
    return f"""<section class="card"><h2>Linha do tempo</h2>
<svg class="tempo" viewBox="0 0 {largura} {altura}" role="img" aria-label="Datas das evidências e data de corte">
<defs><pattern id="aguarda" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
<line x1="0" y1="0" x2="0" y2="8" stroke="var(--prd)" stroke-opacity=".25" stroke-width="3"/></pattern></defs>
{''.join(partes)}</svg>
<div class="legenda"><span><i style="background:var(--nvb)"></i>antes do corte</span><span><i
style="background:var(--pendb)"></i>depois do corte</span><span><i style="background:repeating-linear-gradient(45deg,
var(--prd) 0 2px,transparent 2px 6px);opacity:.5"></i>alerta ainda sem PRODES publicado: só indício</span></div>
</section>"""


def renderizar(ficha: dict) -> str:
    im, res = ficha["imovel"], ficha["resultado"]
    cod = im.get("cod_imovel") or ficha["consulta"].get("cod_imovel") or "imóvel não localizado"
    chips = "".join(f'<span class="badge {COR_SITUACAO[s]}">{n} {escape(s)}</span>'
                    for s, n in res["contagem"].items() if n)
    criterios = [[_td(escape(c["criterio"]) + (f'<div class="mut">AB+S nº {c["criterio_ab_s"]}</div>'
                                               if c["criterio_ab_s"] else '<div class="mut">EUDR</div>')),
                  _td(_badge(c["situacao"])), _td(escape(c["evidencia"]) + (
                      f'<div class="cobertura">⚠ {escape(c["aviso"])}</div>' if c.get("aviso") else "")),
                  _td(escape(c["encaminhamento"])),
                  _td(escape(c["fonte"]))] for c in ficha["criterios"]]
    procedencia = [[_td(escape(p["fonte"])), _td(escape(p["como"])), _td(escape(p["data"])),
                    _td(f'<span class="mono">{escape(str(p["sha256"])[:16])}…</span>'),
                    _td(f'<span class="mono">{escape(str(p.get("arquivo") or ""))}</span>')]
                   for p in ficha["procedencia"]]
    como_ler = "".join(f"<dt>{_badge(s)}</dt><dd>{escape(t)}</dd>" for s, t in EXPLICACAO)

    pr = ficha["consulta"].get("prodes")
    if ficha.get("geometria_car"):
        fatos = "".join(f'<div class="fato"><span>{r}</span><b>{v}</b></div>' for r, v in [
            ("Município", f"{escape(str(im['municipio']))}/{escape(str(im['uf']))}"),
            ("Área (geometria)", f"{_num(im['area_geom_ha'])} ha"),
            ("Status do CAR", escape(str(im["status_texto"]))),
            ("Módulos fiscais", _num(im["m_fiscal"], 2)),
            ("Atualizado no SICAR", _data(im["data_atualizacao"])),
            ("Bioma", escape(", ".join(NOME_BIOMA.get(b, b) for b in ficha["consulta"].get("biomas", [])) or "—")),
            *([("PRODES publicado até", f'{pr["ultimo_ano_do_imovel"]} <small class="mut">({escape(pr["origem"])}, '
                f'{_data(pr["verificado_em"])})</small>')] if pr and pr.get("ultimo_ano_do_imovel") else [])])
        topo = f"""<section class="card grid"><div><h2>Mapa do imóvel</h2>{mapa(ficha)}
<div class="legenda"><span><i style="border:2px solid var(--car);background:var(--carf)"></i>perímetro do CAR</span>
<span><i style="background:var(--emb)"></i>embargo IBAMA (E)</span><span><i style="background:var(--alt)"></i>alerta
DETER (A)</span><span><i style="background:var(--prd)"></i>PRODES após 2020 (P)</span><span><i
style="border:2px dashed var(--ti)"></i>terra indígena (T)</span><span><i style="border:2px dashed var(--tq)"></i>quilombola
(Q)</span><span><i style="border:2px dashed var(--uc)"></i>unidade de conservação (U)</span><span class="mut">mais
claro: na divisa, não atribuído</span></div></div>
<div><h2>Como ler esta ficha</h2><dl class="como">{como_ler}</dl></div></section>"""
        evidencias = _evidencias(ficha["evidencias"])
        topo += linha_do_tempo(ficha)
        condicao = f'<p class="mut">{escape(str(im["condicao"]))}</p>'
    else:
        fatos, condicao, evidencias = "", "", ""
        candidatos = im.get("candidatos") or []
        topo = (f'<section class="card"><h2>CARs candidatos</h2><p class="mono">{"<br>".join(map(escape, candidatos))}'
                f'</p></section>' if candidatos else "")

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Pré-diagnóstico do imóvel</title>
<style>{CSS}</style></head><body><main>
<div class="eyebrow">Pré-diagnóstico de pendências socioambientais</div>
<h1 class="mono" style="font-size:20px">{escape(cod)}</h1>{condicao}
<section class="card"><div class="resultado">{_badge(res["situacao"])}<div><b>{escape(res["resumo"])}.</b>
<div class="mut">Gerado em {escape(ficha["consulta"]["gerado_em"])} · documento do proprietário
{"informado (pseudonimizado)" if ficha["consulta"]["documento_informado"] else "não informado"}</div></div></div>
<div class="chips">{chips}</div><div class="fatos">{fatos}</div></section>
{como_se_formou(ficha)}
{topo}
<section class="card"><h2>Critérios</h2>{_tabela(["Critério", "Situação", "Evidência", "Encaminhamento", "Fonte"],
                                                  criterios, "")}</section>
{evidencias}
<section class="card"><h2>Procedência das evidências</h2>{_tabela(["Fonte", "Como", "Data", "SHA-256", "Arquivo"],
                                                                     procedencia, "")}</section>
<div class="aviso">Pré-diagnóstico feito só com bases públicas, com a evidência de cada pendência. Não é atestado de
conformidade: critério sem fonte aberta aparece como &ldquo;não verificado&rdquo;, e o encaminhamento é uma orientação
para o técnico.</div>
</main></body></html>"""


def _ponto(situacao: str) -> str:
    return (f'<span class="ponto {COR_SITUACAO.get(situacao, "nv")}" title="{escape(situacao)}">'
            f'{SIMBOLO.get(situacao, "·")}</span>')


def _situacao_prodes(publicacao: dict | None) -> str:
    """Cartão com a situação do PRODES em lote: anos publicados por bioma, verificação e próxima verificação."""
    if not publicacao:
        return ('<section class="card"><h2>PRODES</h2><p class="mut">Sem o lote do PRODES (rode <span class="mono">'
                'python -m pipeline --fontes prodes</span>).</p></section>')
    novos = {m["bioma"]: m["ano"] for h in publicacao["historico"][-1:] for m in h["mudancas"]
             if m["tipo"] == "novo ano publicado"}
    linhas = []
    for bioma, ultimo in publicacao["ultimo_ano_publicado"].items():
        anos = "".join(f'<span class="{"pub" if a <= ultimo else ""}{" novo" if novos.get(bioma) == a else ""}">{a}'
                       f'</span>' for a in range(publicacao["desde"], pd.Timestamp(publicacao["verificado_em_utc"][:10])
                                                 .year + 1))
        imagem = (publicacao.get("ultima_imagem") or {}).get(bioma)
        linhas.append(f'<tr><td><b>{escape(NOME_BIOMA.get(bioma, bioma))}</b></td><td><div class="anos">{anos}</div>'
                      f'</td><td class="n">até {ultimo}</td><td class="n mut">última imagem {_data(imagem)}'
                      f'{"" if bioma in config.BIOMAS_COM_DETER else " · sem DETER"}</td></tr>')
    origem = ("arquivo de cada bioma (TerraBrasilis), 27 UFs" if publicacao.get("origem", "").startswith("arquivo")
              else "WFS, UF por UF")
    versoes = "; ".join(f'{escape(NOME_BIOMA.get(b, b))} {_data(a.get("versao"))}'
                        for b, a in (publicacao.get("arquivos") or {}).items())
    return f"""<section class="card"><h2>PRODES: fonte em lote por UF, conferida todo mês</h2>
<p class="mut" style="font-size:13px">Origem: {origem}.{f" Versão de cada arquivo: {versoes}." if versoes else ""}</p>
<div class="placar"><div><span class="eyebrow">verificado em</span><br><b>{_data(publicacao["verificado_em_utc"])}</b></div>
<div><span class="eyebrow">próxima verificação</span><br><b>{_data(publicacao["proxima_verificacao"])}</b></div>
<div><span class="eyebrow">UFs no lote</span><br><b>{escape(", ".join(publicacao["ufs"]))}</b></div></div>
<div class="tabela"><table><tbody>{''.join(linhas)}</tbody></table></div>
<p class="mut" style="font-size:13px">Verde: ano publicado. Contorno: ano que apareceu na última verificação. A verificação
compara a versão de cada arquivo no catálogo do TerraBrasilis e trata de novo só o bioma que mudou. Em bioma sem DETER, depois da última imagem não há cobertura até
o próximo PRODES.</p>
</section>"""


def indice(fichas: list[tuple[dict, dict, str]], publicacao: dict | None = None) -> str:
    """Página da demonstração: avaliação (esperado x obtido), situação do PRODES e um cartão por ficha.

    `fichas`: (ficha, caso, arquivo), com caso = {"caso": descrição, "esperado": {critério ou "resultado": situação}}.
    """
    linhas, cartoes, conferem = [], [], 0
    for ficha, caso, arquivo in fichas:
        res, im = ficha["resultado"], ficha["imovel"]
        obtido = {c["chave"]: c["situacao"] for c in ficha["criterios"]} | {"resultado": res["situacao"]}
        esperado = caso.get("esperado", {})
        diferentes = [k for k, v in esperado.items() if obtido.get(k) != v]
        conferem += not diferentes
        marca = ('<span class="confere sim">✓ confere</span>' if not diferentes else
                 '<span class="confere nao">✕ ' + escape(", ".join(diferentes)) + "</span>")
        linhas.append("<tr>" + _td(f'<a href="{escape(arquivo)}">{escape(caso["caso"])}</a>') +
                      "".join(_td(_ponto(obtido.get(k, "não verificado"))) for k in VERIFICADOS) +
                      _td(_badge(res["situacao"])) + _td(marca) + "</tr>")
        chips = "".join(f'<span class="badge {COR_SITUACAO[s]}">{n} {escape(s)}</span>'
                        for s, n in res["contagem"].items() if n)
        cartoes.append(f"""<a class="card" style="display:block;text-decoration:none;color:inherit" href="{escape(arquivo)}">
<div class="resultado">{_badge(res["situacao"])}<b>{escape(caso["caso"])}</b></div>
<p class="mono mut">{escape(str(im.get("cod_imovel") or ""))}</p><div class="chips">{chips}</div></a>""")
    cab = "".join(f"<th>{NOME_CURTO[k]}</th>" for k in VERIFICADOS)
    legenda = " ".join(f"{_ponto(s)} {escape(s)}" for s in ("pendência", "indício", "sem ocorrência", "inconclusivo",
                                                             "não verificado"))
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Demonstração do pré-diagnóstico</title>
<style>{CSS}</style></head><body><main><div class="eyebrow">Demonstração</div><h1>Pré-diagnóstico de pendências</h1>
<p class="mut">CARs reais: 6 do café de MG, 1 por bioma no resto do país e 4 com sobreposição a área protegida, cruzados com IBAMA, DETER, PRODES, Lista Suja,
terras indígenas, territórios quilombolas e unidades de conservação. CPF fictício.</p>
<section class="card"><h2>Avaliação: o pipeline acertou cada caso?</h2>
<div class="placar"><div><b>{conferem} de {len(fichas)}</b><br><span class="mut">casos com o resultado esperado em
todos os critérios</span></div></div>
<div class="tabela"><table class="matriz"><thead><tr><th>Caso</th>{cab}<th>Resultado</th><th>Esperado?</th></tr>
</thead><tbody>{''.join(linhas)}</tbody></table></div>
<p class="mut" style="font-size:13px;margin-top:10px">{legenda}</p></section>
{_situacao_prodes(publicacao)}
<h2 style="margin-top:28px">Fichas</h2>
{''.join(cartoes)}</main></body></html>"""
