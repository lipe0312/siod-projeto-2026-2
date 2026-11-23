"""Tela "Carteira" do console (issue #34): a página inicial do técnico, "quem atendo primeiro?".

Lê só o que a carteira já gravou (`carteira.csv` e as fichas JSON ao lado, em data/saidas/console/<pasta>/) e não
recalcula nada: a ordem é a coluna `prioridade`, "o que mudou" são as colunas `mudou`/`o_que_mudou` que
`pipeline.carteira.comparar` preencheu, e a data de cada fonte vem da `procedencia` gravada em cada ficha.
Todo texto passa por html.escape e pela máscara de CPF/CNPJ (`ficha._t`).
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from console.telas.ficha import NOME, SITUACAO, _datas_br, _ico, _num, _plural, _t

PASTAS = ("demonstracao",)  # subpastas de data/saidas/console/ com uma carteira gravada, na ordem de preferência
BRASILIA = ZoneInfo("America/Sao_Paulo")
COMANDO_DEMO = ".venv/bin/python docs/evidencias/entrega-final/01_cooperativa_demonstracao.py"
# Faixa de resumo, na ordem da carteira (pendência > inconclusivo > indício > sem pendência).
GRUPOS = (("com pendência", "pend", "Pendência"), ("inconclusivo", "inco", "Inconclusivo"),
          ("com indício", "indi", "Indício"), ("sem pendência nas fontes verificadas", "sem", "Sem pendência"))
# Faixa "Fontes": grupo → prefixos do nome da fonte na procedência da ficha.
FONTES = (("IBAMA, embargos", ("IBAMA",)), ("DETER", ("INPE DETER",)), ("PRODES", ("INPE PRODES",)),
          ("Lista Suja", ("MTE",)), ("Áreas protegidas", ("FUNAI", "MMA", "INCRA", "IBGE")))


def pasta_da_carteira(base: Path) -> Path | None:
    """Primeira subpasta de `base` que tem um carteira.csv; None se nenhuma tem (carteira vazia)."""
    for nome in PASTAS:
        if (base / nome / "carteira.csv").is_file():
            return base / nome
    return None


def pastas_de_fichas(base: Path) -> list[Path]:
    """Onde a rota /ficha/<nome> procura, depois de `base`: as fichas de cada carteira gravada."""
    return [base / nome / "fichas" for nome in PASTAS]


def _ler_ficha(pasta: Path, relativo: str) -> tuple[str | None, dict | None]:
    """(nome, ficha) a partir da coluna `ficha` do CSV ("fichas/<nome>.html"); nome None se não for um nome seguro."""
    nome = Path(relativo or "").stem
    if not NOME.fullmatch(nome) or Path(relativo).parent.name != "fichas":
        return None, None
    caminho = pasta / "fichas" / f"{nome}.json"
    try:
        ficha = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return nome, None
    return nome, ficha if isinstance(ficha, dict) and isinstance(ficha.get("resultado"), dict) else None


def _faltam(ficha: dict | None) -> int:
    cont = ((ficha or {}).get("resultado") or {}).get("contagem") or {}
    return int(cont.get("não verificado", 0)) + int(cont.get("inconclusivo", 0))


def _primeiro_passo(linha: dict, ficha: dict | None) -> str:
    if linha.get("primeiro_encaminhamento"):
        return linha["primeiro_encaminhamento"]
    for cartao in (ficha or {}).get("plano_de_acao") or []:
        for passo in cartao.get("passos") or []:
            if passo.get("acao"):
                return f"{passo['acao']} ({passo.get('quem') or 'técnico'})"
    if linha.get("resultado") == "inconclusivo":
        return "Corrigir a linha da planilha e rodar a carteira de novo."
    return ""


def ler(base: Path) -> dict | None:
    """Linhas da carteira (na ordem de `prioridade`) com o que a tela mostra; None se não há carteira gravada."""
    pasta = pasta_da_carteira(base)
    if pasta is None:
        return None
    with (pasta / "carteira.csv").open(encoding="utf-8", newline="") as f:
        brutas = list(csv.DictReader(f))
    linhas, fichas = [], []
    for b in sorted(brutas, key=lambda r: int(r.get("prioridade") or 10**9) if (r.get("prioridade") or "").isdigit()
                    else 10**9):
        nome, ficha = _ler_ficha(pasta, b.get("ficha") or "")
        if ficha:
            fichas.append(ficha)
        sit = b.get("resultado") or "inconclusivo"
        linhas.append({
            **b, "situacao": sit if sit in dict((g[0], 1) for g in GRUPOS) else "inconclusivo",
            "nome": nome if ficha else None, "faltam": _faltam(ficha) if ficha else None,
            "a_tratar": len((ficha or {}).get("plano_de_acao") or []) if ficha else None,
            "passo": _primeiro_passo(b, ficha), "gerado_em": ((ficha or {}).get("consulta") or {}).get("gerado_em")})
    return {"pasta": pasta.name, "linhas": linhas, "fichas": fichas}


# --- partes da tela -------------------------------------------------------------------------------------------------

def _hoje() -> date:
    return datetime.now(BRASILIA).date()


def _idade(texto: str, hoje: date) -> str:
    """'há N dias' da primeira data ISO do texto."""
    m = re.search(r"\d{4}-\d{2}-\d{2}", texto or "")
    if not m:
        return ""
    dias = (hoje - date.fromisoformat(m[0])).days
    return "hoje" if dias <= 0 else "ontem" if dias == 1 else f"há {dias} dias"


def _fontes(fichas: list[dict], hoje: date) -> str:
    datas: dict[str, set[str]] = {g: set() for g, _ in FONTES}
    sicar: set[str] = set()
    for ficha in fichas:
        for p in ficha.get("procedencia") or []:
            fonte, dt = str(p.get("fonte") or ""), str(p.get("data") or "")
            if fonte.startswith("SICAR"):
                sicar.add(dt)
            for grupo, prefixos in FONTES:
                if dt and fonte.startswith(prefixos):
                    datas[grupo].add(dt)
    itens = []
    for grupo, _ in FONTES:
        ds = sorted(datas[grupo])
        if not ds:
            valor = '<span class="st-txt-nao">não consta nas fichas</span>'
        else:
            mais_antiga = ds[0]
            valor = (f"<b>{_t(_datas_br(mais_antiga.replace('verificado em ', '')))}</b>"
                     f' <span class="mu">{escape(_idade(mais_antiga, hoje))}</span>')
            if len(ds) > 1:
                valor += f' <span class="mu">(a mais antiga de {len(ds)} datas)</span>'
        itens.append(f"<div><dt>{escape(grupo)}</dt><dd>{valor}</dd></div>")
    s = sorted(d for d in sicar if d)
    extra = (f' <span class="mu">nesta carteira, de {_t(_datas_br(s[0]))} a {_t(_datas_br(s[-1]))}</span>'
             if len(s) > 1 else f' <span class="mu">nesta carteira, {_t(_datas_br(s[0]))}</span>' if s else "")
    itens.append(f"<div><dt>SICAR</dt><dd><b>na hora</b>, a cada consulta{extra}</dd></div>")
    return (f'<section class="fontes-faixa" aria-labelledby="t-fontes"><h2 id="t-fontes">Fontes</h2>'
            f'<p class="mu">Data do dado que entrou nesta execução (da procedência gravada em cada ficha).</p>'
            f'<dl>{"".join(itens)}</dl></section>')


def _mudancas(linhas: list[dict]) -> str:
    sim = [r for r in linhas if r.get("mudou") == "sim"]
    comparados = [r for r in linhas if r.get("mudou") in ("sim", "não")]
    if not comparados:
        texto = "Primeira execução, sem comparação: na próxima execução esta faixa mostra o que mudou."
    elif not sim:
        texto = f"<b>Nenhum imóvel mudou desde a execução anterior</b>, entre {len(comparados)} comparados."
    else:
        itens = "".join(f"<li><b>{_t(r.get('id_produtor'))}</b> {_t(r.get('nome_area'))}: "
                        f"{_t(_datas_br(r.get('o_que_mudou')))}</li>" for r in sim)
        texto = (f"<b>{_plural(len(sim), 'imóvel mudou', 'imóveis mudaram')} desde a execução anterior</b>, entre "
                 f"{len(comparados)} comparados. Linhas marcadas com ↻.<ul>{itens}</ul>")
    return (f'<section class="mudancas" aria-labelledby="t-mudou"><h2 id="t-mudou">O que mudou</h2>'
            f"<p>{texto}</p></section>")


def _selo_linha(r: dict) -> str:
    """Selo da situação; "sem pendência" com critério sem verificação fica neutro, nunca verde (ADR 0013)."""
    sit = r["situacao"]
    if sit == "sem pendência nas fontes verificadas" and (r["faltam"] or r["faltam"] is None):
        icone, classe, rotulo = "nao", "st-nao", "Sem pendência nas fontes verificadas"
    else:
        icone, classe, rotulo = SITUACAO.get(sit, ("inco", "st-inco", "Inconclusivo"))
    return f'<span class="selo {classe}">{_ico(icone)}<span>{escape(rotulo)}</span></span>'


def _o_que_apareceu(r: dict) -> str:
    partes = []
    if r.get("pendencias"):
        partes.append(f"<b>Pendência:</b> {_t(r['pendencias'])}")
    if r.get("indicios"):
        partes.append(f"<b>Indício:</b> {_t(r['indicios'])}")
    if r.get("inconclusivos"):
        partes.append(f"<b>Inconclusivo:</b> {_t(r['inconclusivos'])}")
    if r["situacao"] == "inconclusivo" and not r.get("inconclusivos"):
        motivo = r.get("problema_na_linha") or "a ficha não foi gerada"
        partes.append(f"<b>Inconclusivo:</b> {_t(motivo)}")
    if not partes:
        partes.append("Nada encontrado nas fontes verificadas.")
    if r.get("mudou") == "sim":
        partes.append(f'<span class="mudou">↻ mudou: {_t(_datas_br(r.get("o_que_mudou")))}</span>')
    return "<br>".join(partes)


def _contas(r: dict) -> str:
    if r["nome"] is None:
        return '<span class="mu">sem ficha</span>'
    faltam = (f"{_plural(r['faltam'], 'critério falta', 'critérios faltam')}" if r["faltam"]
              else "nenhum critério falta")
    return f"{_plural(r['a_tratar'], 'item a tratar', 'itens a tratar')}<br><span class=\"mu\">{faltam}</span>"


def _linha(r: dict) -> str:
    gado = "gado" in (r.get("commodity") or "").lower()
    commodity = "cafe" if "café" in (r.get("commodity") or "").lower() else "gado" if gado else "outra"
    falta = "sim" if (r["faltam"] or r["nome"] is None or r["situacao"] == "inconclusivo") else "nao"
    busca = f"{r.get('id_produtor') or ''} {r.get('nome_area') or ''}".lower()
    grupo = next((g[1] for g in GRUPOS if g[0] == r["situacao"]), "inco")
    local = " · ".join(x for x in (r.get("municipio"), r.get("uf")) if x)
    area = f"{_num(r.get('area_ha'))} ha" if r.get("area_ha") else ""
    ficha = (f'<a class="leva" href="/ficha/{escape(r["nome"])}"><span>Abrir ficha</span>{_ico("arrow", "ico seta")}'
             f'<span class="sr"> de {_t(r.get("id_produtor"))}</span></a>' if r["nome"]
             else '<span class="mu">sem ficha</span>')
    return (f'<tr data-grupo="{grupo}" data-commodity="{commodity}" data-falta="{falta}" data-busca="{_t(busca)}"'
            f'{" class=\"mudou\"" if r.get("mudou") == "sim" else ""}>'
            f'<td class="n" data-rot="Prioridade">{_t(r.get("prioridade"))}</td>'
            f'<td data-rot="Imóvel"><b>{_t(r.get("id_produtor"))}</b> {_t(r.get("nome_area"))}'
            f'<div class="mu">{_t(r.get("commodity") or "commodity não informada")}'
            f'{" · " + _t(local) if local else ""}{" · " + area if area else ""}</div></td>'
            f'<td data-rot="Situação">{_selo_linha(r)}</td>'
            f'<td data-rot="O que apareceu">{_o_que_apareceu(r)}</td>'
            f'<td data-rot="Primeiro passo">{_t(r["passo"]) or "—"}</td>'
            f'<td data-rot="A tratar">{_contas(r)}</td>'
            f'<td data-rot="Ficha">{ficha}</td></tr>')


def _resumo(linhas: list[dict]) -> str:
    botoes = []
    for sit, grupo, rotulo in GRUPOS:
        membros = [r for r in linhas if r["situacao"] == sit]
        area = sum(float(r["area_ha"]) for r in membros if (r.get("area_ha") or "").replace(".", "", 1).isdigit())
        icone, classe = grupo, f"st-{grupo}"
        if grupo == "sem" and any(r["faltam"] or r["faltam"] is None for r in membros):
            icone, classe = "nao", "st-nao"  # nunca verde com critério sem verificação
        botoes.append(
            f'<button class="cont {classe}" type="button" data-filtro-grupo="{grupo}" aria-pressed="false">'
            f'{_ico(icone)}<span class="cont-n" data-contar="{len(membros)}">{len(membros)}</span>'
            f'<span class="cont-r">{escape(rotulo)}</span><span class="mu">{_num(area) + " ha" if area else "área não informada"}</span></button>')
    return f'<div class="resumo" role="group" aria-label="Filtrar por situação">{"".join(botoes)}</div>'


def _execucao(linhas: list[dict]) -> str:
    datas = sorted(r["gerado_em"] for r in linhas if r.get("gerado_em"))
    return f"execução de {_t(_datas_br(datas[-1]))}" if datas else "execução sem data nas fichas"


def renderizar(dados: dict, hoje: date | None = None) -> str:
    linhas = dados["linhas"]
    filtros = (
        '<div class="filtros">'
        '<label class="campo-busca"><span class="sr">Buscar por id do produtor ou nome da área</span>'
        f'{_ico("search")}<input type="search" id="busca-carteira" placeholder="Id do produtor ou nome da área" '
        'autocomplete="off"></label>'
        '<div class="chips" role="group" aria-label="Filtros">'
        '<button class="chip" type="button" data-filtro-commodity="cafe" aria-pressed="false">Café</button>'
        '<button class="chip" type="button" data-filtro-commodity="gado" aria-pressed="false">Gado</button>'
        '<button class="chip" type="button" data-filtro-falta aria-pressed="false">Falta dado</button>'
        '<button class="chip limpar" type="button" data-filtro-limpar>Limpar filtros</button></div></div>')
    cab = "".join(f"<th scope=\"col\">{t}</th>" for t in ("#", "Imóvel", "Situação", "O que apareceu",
                                                          "Primeiro passo", "A tratar", "Ficha"))
    return f"""
<div class="carteira">
<header class="cart-topo">
  <h1 id="t-carteira">Carteira</h1>
  <p class="mu">{_plural(len(linhas), "imóvel", "imóveis")} na ordem de quem atender primeiro
  (pendência, inconclusivo, indício, sem pendência) · {_execucao(linhas)} · pasta <span class="mono">{escape(dados["pasta"])}</span></p>
</header>
{_resumo(linhas)}
{filtros}
<p class="mu contagem-filtro" id="contagem-filtro" aria-live="polite">Mostrando {len(linhas)} de {len(linhas)}.</p>
<table class="lista-carteira" aria-labelledby="t-carteira">
<thead><tr>{cab}</tr></thead>
<tbody>{"".join(_linha(r) for r in linhas)}</tbody>
</table>
<p class="mu" id="nenhum" hidden>Nenhum imóvel com esses filtros.</p>
<div class="cart-pe">
{_mudancas(linhas)}
{_fontes(dados["fichas"], hoje or _hoje())}
</div>
</div>"""


def vazia() -> str:
    return f"""
<section class="vazia" aria-labelledby="t-carteira">
  <h1 id="t-carteira">Carteira</h1>
  <p class="mu">Ainda não há carteira gravada neste computador. Consulte um imóvel agora ou rode a carteira de
  demonstração (uma cooperativa de café e gado, sem rede) e volte aqui.</p>
  <a class="btn b-pri leva" href="/consulta"><span>Nova consulta</span>{_ico("arrow", "ico seta")}</a>
  <p class="mu">Para a demonstração, na raiz do projeto:</p>
  <pre class="mono comando">{escape(COMANDO_DEMO)}</pre>
</section>"""
