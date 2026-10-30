"""Ficha do pré-diagnóstico em HTML: uma página só, sem dependência externa, com o mapa do imóvel em SVG."""

from html import escape

import pandas as pd
import shapely

from pipeline.fontes import sicar

COR_SITUACAO = {"pendência": "pend", "indício": "ind", "sem ocorrência": "ok", "não verificado": "nv",
                "inconclusivo": "inc", "com pendência": "pend", "com indício": "ind",
                "sem pendência nas fontes verificadas": "ok"}

EXPLICACAO = [
    ("pendência", "Encontrada numa fonte oficial e impede crédito rural ou venda sob a EUDR."),
    ("indício", "Algo foi encontrado, mas precisa de conferência antes de virar pendência."),
    ("sem ocorrência", "A fonte foi consultada e não há nada contra o imóvel."),
    ("não verificado", "Não há fonte aberta integrada; nunca é lido como “conforme”."),
    ("inconclusivo", "Falta uma entrada (por exemplo, o CAR não foi localizado)."),
]

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--tx:#1d1d1b;--mut:#66645e;--bd:#e2e0d8;--car:#2f7d4f;--carf:rgba(47,125,79,.08);
--emb:#c0392b;--alt:#d9822b;--prd:#7b4fb0;--pend:#b3261e;--pendb:#fbe9e7;--ind:#8a5a00;--indb:#fdf1d8;--ok:#1e6b3c;
--okb:#e3f2e8;--nv:#55575c;--nvb:#ecedef;--inc:#3b4a8a;--incb:#e6e9f6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161614;--card:#1f1f1c;--tx:#ecebe6;
--mut:#a3a199;--bd:#34332f;--car:#5fbf86;--carf:rgba(95,191,134,.10);--emb:#ff7b6b;--alt:#f3a75a;--prd:#b592e6;
--pend:#ff8a80;--pendb:#3a1f1c;--ind:#f2c46b;--indb:#352a14;--ok:#7fd3a0;--okb:#1a2e22;--nv:#b6b8bd;--nvb:#2a2b2e;
--inc:#9fb0f2;--incb:#1f2440}}
:root[data-theme="dark"]{--bg:#161614;--card:#1f1f1c;--tx:#ecebe6;--mut:#a3a199;--bd:#34332f;--car:#5fbf86;
--carf:rgba(95,191,134,.10);--emb:#ff7b6b;--alt:#f3a75a;--prd:#b592e6;--pend:#ff8a80;--pendb:#3a1f1c;--ind:#f2c46b;
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
a{color:var(--inc)}
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
    car = sicar.projetar(shapely.make_valid(shapely.from_wkt(ficha["geometria_car"])))
    x0, y0, x1, y1 = car.bounds
    margem = 0.12 * max(x1 - x0, y1 - y0)
    x0, y0, x1, y1 = x0 - margem, y0 - margem, x1 + margem, y1 + margem
    escala = largura / (x1 - x0)
    altura = (y1 - y0) * escala

    def transformar(x, y):
        return (x - x0) * escala, (y1 - y) * escala

    def desenhar(wkt):
        return _caminho(sicar.projetar(shapely.make_valid(shapely.from_wkt(wkt))), transformar)

    camadas, rotulos = [], []
    ev = ficha["evidencias"]
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
indício. De 2022 em diante, o desmatamento é posterior a 31/12/2020.</p></section>"""


def renderizar(ficha: dict) -> str:
    im, res = ficha["imovel"], ficha["resultado"]
    cod = im.get("cod_imovel") or ficha["consulta"].get("cod_imovel") or "imóvel não localizado"
    chips = "".join(f'<span class="badge {COR_SITUACAO[s]}">{n} {escape(s)}</span>'
                    for s, n in res["contagem"].items() if n)
    criterios = [[_td(escape(c["criterio"]) + (f'<div class="mut">AB+S nº {c["criterio_ab_s"]}</div>'
                                               if c["criterio_ab_s"] else '<div class="mut">EUDR</div>')),
                  _td(_badge(c["situacao"])), _td(escape(c["evidencia"])), _td(escape(c["encaminhamento"])),
                  _td(escape(c["fonte"]))] for c in ficha["criterios"]]
    procedencia = [[_td(escape(p["fonte"])), _td(escape(p["como"])), _td(escape(p["data"])),
                    _td(f'<span class="mono">{escape(str(p["sha256"])[:16])}…</span>'),
                    _td(f'<span class="mono">{escape(str(p.get("arquivo") or ""))}</span>')]
                   for p in ficha["procedencia"]]
    como_ler = "".join(f"<dt>{_badge(s)}</dt><dd>{escape(t)}</dd>" for s, t in EXPLICACAO)

    if ficha.get("geometria_car"):
        fatos = "".join(f'<div class="fato"><span>{r}</span><b>{v}</b></div>' for r, v in [
            ("Município", f"{escape(str(im['municipio']))}/{escape(str(im['uf']))}"),
            ("Área (geometria)", f"{_num(im['area_geom_ha'])} ha"),
            ("Status do CAR", escape(str(im["status_texto"]))),
            ("Módulos fiscais", _num(im["m_fiscal"], 2)),
            ("Atualizado no SICAR", _data(im["data_atualizacao"]))])
        topo = f"""<section class="card grid"><div><h2>Mapa do imóvel</h2>{mapa(ficha)}
<div class="legenda"><span><i style="border:2px solid var(--car);background:var(--carf)"></i>perímetro do CAR</span>
<span><i style="background:var(--emb)"></i>embargo IBAMA (E)</span><span><i style="background:var(--alt)"></i>alerta
DETER (A)</span><span><i style="background:var(--prd)"></i>PRODES após 2020 (P)</span><span class="mut">mais claro: na
divisa, não atribuído</span></div></div>
<div><h2>Como ler esta ficha</h2><dl class="como">{como_ler}</dl></div></section>"""
        evidencias = _evidencias(ficha["evidencias"])
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


def indice(fichas: list[tuple[dict, str, str]]) -> str:
    """Página da demonstração: um cartão por ficha gerada."""
    cartoes = []
    for ficha, descricao, arquivo in fichas:
        res, im = ficha["resultado"], ficha["imovel"]
        chips = "".join(f'<span class="badge {COR_SITUACAO[s]}">{n} {escape(s)}</span>'
                        for s, n in res["contagem"].items() if n)
        cartoes.append(f"""<a class="card" style="display:block;text-decoration:none;color:inherit" href="{escape(arquivo)}">
<div class="resultado">{_badge(res["situacao"])}<b>{escape(descricao)}</b></div>
<p class="mono mut">{escape(str(im.get("cod_imovel") or ""))}</p><div class="chips">{chips}</div></a>""")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Demonstração do pré-diagnóstico</title>
<style>{CSS}</style></head><body><main><div class="eyebrow">Demonstração</div><h1>Pré-diagnóstico de pendências</h1>
<p class="mut">CARs reais do recorte de café de MG, consultados no SICAR e cruzados com IBAMA, DETER, PRODES e Lista
Suja. O documento usado é um CPF fictício, para mostrar a Lista Suja verificada sem dado pessoal.</p>
{''.join(cartoes)}</main></body></html>"""
