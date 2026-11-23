"""Tela "Ficha do imóvel" do console (issue #33): veredito, plano de ação, o que falta, mapa e rastreabilidade.

Lê só o JSON que o pré-diagnóstico gravou (`prediagnostico.escrever`: `plano_de_acao` e `o_que_falta` já vêm prontos
de `plano_de_acao.montar`) e não recalcula nada. O mapa e a linha do tempo são os SVGs que a ficha já desenhou no
HTML gravado ao lado do JSON (o JSON não guarda as geometrias das evidências). Todo texto passa por html.escape e pela
máscara de CPF/CNPJ: a tela nunca mostra documento, nem que algum texto livre o traga.
"""

from __future__ import annotations

import json
import re
import shlex
from html import escape
from pathlib import Path
from urllib.parse import urlencode

from pipeline.documentos import FORMATO_CPF_CNPJ, OMITIDO

NOME = re.compile(r"[A-Za-z0-9_-]{1,80}")
COMANDO = ".venv/bin/python -m pipeline.prediagnostico"

# situação → (ícone, classe do selo, nome escrito). Cor nunca sozinha (DESIGN.md §2).
SITUACAO = {
    "pendência": ("pend", "st-pend", "Pendência"), "indício": ("indi", "st-indi", "Indício"),
    "sem ocorrência": ("sem", "st-sem", "Sem ocorrência"), "não verificado": ("nao", "st-nao", "Não verificado"),
    "inconclusivo": ("inco", "st-inco", "Inconclusivo"), "com pendência": ("pend", "st-pend", "Com pendência"),
    "com indício": ("indi", "st-indi", "Com indício"),
    "sem pendência nas fontes verificadas": ("sem", "st-sem", "Sem pendência nas fontes verificadas"),
}
BLOQUEIA = {"sim": ("sim", "bloqueia"), "talvez": ("talvez", "pode bloquear"), "não": ("nao", "não bloqueia")}
# Rótulos do mapa por critério (as letras que o SVG da ficha escreve sobre cada evidência).
LETRAS = {"embargo": (("embargos", "E"),), "desmatamento": (("alertas", "A"), ("prodes", "P")),
          "desmatamento_resto": (("alertas_resto", "AR"), ("prodes_resto", "PR")),
          "terra_indigena": (("terra_indigena", "T"),), "quilombola": (("quilombola", "Q"),),
          "unidade_conservacao": (("unidade_conservacao", "U"),)}
SEM_MAPA = {"lista_suja": "evidência documental, sem polígono", "car": "o perímetro do CAR no mapa"}
# Entradas que a tela de consulta recebe: "Informar agora" volta para ela com o CAR preenchido e o campo aberto.
INFORMAR = (("Documento", "documento"), ("Área de produção", "area"), ("Localização do imóvel", "car"))
SUBFONTES = {"deter", "prodes"}
PERIGOSO = re.compile(r"<\s*(script|style|foreignobject|iframe|object|embed|image|animate|set\b|a\b)|javascript:|"
                      r"[\s\"'/]on[a-z]+\s*=|href\s*=\s*[\"'](?!#)", re.IGNORECASE)
BLOCO_SVG = {"mapa": re.compile(r'<svg class="mapa".*?</svg>\s*<div class="legenda">.*?</div>', re.DOTALL),
             "tempo": re.compile(r'<svg class="tempo".*?</svg>\s*<div class="legenda">.*?</div>', re.DOTALL)}
# Mapa de satélite (issue #35): fundo EOX Sentinel-2 cloudless (CC BY 4.0), 2020 = corte da EUDR (31/12/2020) e o
# mosaico mais recente publicado (conferido em 23/11/2026). As camadas vêm do <nome>.camadas.geojson (#31).
ANO_ANTES, ANO_DEPOIS = 2020, 2025
LIMITE_CAMADAS = 2_000_000  # bytes; a #31 grava no máximo 1 MB
CAMADAS_MAPA = {  # camada do GeoJSON → nome na legenda (ordem da legenda)
    "car": "Perímetro do CAR", "area_de_producao": "Área de produção", "alerta_deter": "Alerta DETER",
    "alerta_deter_resto": "Alerta DETER (resto do imóvel)", "prodes": "Desmatamento PRODES",
    "prodes_resto": "PRODES (resto do imóvel)", "embargo": "Embargo IBAMA", "terra_indigena": "Terra indígena",
    "quilombola": "Território quilombola", "unidade_conservacao": "Unidade de conservação"}


class FichaIlegivel(ValueError):
    """O JSON existe, mas não é uma ficha que a tela consiga ler."""


# --- texto ----------------------------------------------------------------------------------------------------------

def _sem_doc(valor) -> str:
    return FORMATO_CPF_CNPJ.sub(OMITIDO, "" if valor is None else str(valor))


def _t(valor) -> str:
    """Texto seguro: sem documento (máscara de CPF/CNPJ) e escapado."""
    return escape(_sem_doc(valor))


def _faltam(ficha: dict) -> int:
    cont = ficha["resultado"].get("contagem") or {}
    return cont.get("não verificado", 0) + cont.get("inconclusivo", 0)


def _ressalva(n: int) -> str:
    return f"nas fontes verificadas; {_plural(n, 'critério sem verificação', 'critérios sem verificação')}"


def _ico(nome: str, classe: str = "ico") -> str:
    return f'<svg class="{classe}" aria-hidden="true"><use href="#i-{nome}"/></svg>'


def _datas_br(texto) -> str:
    """Datas ISO dentro de um texto viram dd/mm/aaaa (com hh:mm quando houver hora). Devolve texto cru (sem escape)."""
    def troca(m):
        d = f"{m[3]}/{m[2]}/{m[1]}"
        return f"{d} {m[4]}:{m[5]}" if m[4] else d
    return re.sub(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?)?", troca, str(texto or ""))


def _num(v, casas: int = 1) -> str:
    try:
        return f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def _link(texto, url, classe: str = "") -> str:
    """Só http/https viram link (abre em outra aba); o resto sai como texto."""
    if not (url and re.match(r"https?://", str(url), re.IGNORECASE)):
        return _t(texto)
    cl = f' class="{classe}"' if classe else ""
    return (f'<a{cl} href="{escape(str(url))}" target="_blank" rel="noopener noreferrer">{_t(texto or url)}'
            f'<span class="sr"> (abre em outra aba)</span></a>')


def _selo(situacao: str, extra: str = "", rotulo: str | None = None) -> str:
    icone, classe, nome = SITUACAO.get(situacao, ("nao", "st-nao", situacao.capitalize() if situacao else "—"))
    return f'<span class="selo {classe}">{_ico(icone)}<span>{_t(rotulo or nome)}</span>{extra}</span>'


def car_curto(cod: str | None) -> str:
    """MG-3166808-A726F93D…B1F4: UF, município e as pontas do hash do CAR (o código inteiro vai no botão copiar)."""
    if not cod:
        return "—"
    partes = cod.split("-")
    if len(partes) == 3 and len(partes[2]) > 12:
        return f"{partes[0]}-{partes[1]}-{partes[2][:8]}…{partes[2][-4:]}"
    return cod


def _copiar(valor: str, rotulo: str) -> str:
    return (f'<button class="copiar" type="button" data-copiar="{_t(valor)}" aria-label="{escape(rotulo)}">'
            f'{_ico("copy")}<span data-copiar-txt>Copiar</span></button>')


# --- leitura --------------------------------------------------------------------------------------------------------

def svgs_da_ficha(html: str) -> dict[str, str]:
    """Mapa e linha do tempo (com as legendas) do HTML da ficha. Bloco com script, evento ou link externo é
    descartado: a tela mostra "indisponível" em vez de confiar nele."""
    saida = {}
    for chave, padrao in BLOCO_SVG.items():
        m = padrao.search(html or "")
        if m and not PERIGOSO.search(m[0]):
            saida[chave] = _sem_doc(m[0])
    return saida


def ler(pasta: Path, nome: str) -> tuple[dict, dict[str, str]]:
    """(ficha, svgs) de <pasta>/<nome>.json e do .html ao lado. FileNotFoundError se não há ficha com esse nome;
    FichaIlegivel se o JSON não é uma ficha."""
    if not NOME.fullmatch(nome or ""):
        raise FileNotFoundError(nome)
    pasta = pasta.resolve()
    caminho = (pasta / f"{nome}.json").resolve()
    if not caminho.is_relative_to(pasta) or not caminho.is_file():
        raise FileNotFoundError(nome)
    try:
        ficha = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise FichaIlegivel("o arquivo da ficha não é um JSON válido") from e
    if not isinstance(ficha, dict) or not isinstance(ficha.get("resultado"), dict) \
            or not isinstance(ficha.get("criterios"), list):
        raise FichaIlegivel("o arquivo não tem o resultado e os critérios de uma ficha")
    html = caminho.with_suffix(".html")
    svgs = svgs_da_ficha(html.read_text(encoding="utf-8") if html.is_file() else "")
    geojson = caminho.with_name(f"{nome}.camadas.geojson")
    if geojson.is_file() and geojson.stat().st_size <= LIMITE_CAMADAS:
        camadas = camadas_da_ficha(geojson.read_text(encoding="utf-8", errors="replace"))
        if camadas:
            svgs["camadas"] = camadas
    return ficha, svgs


def _mascarar(valor):
    if isinstance(valor, str):
        return _sem_doc(valor)
    if isinstance(valor, list):
        return [_mascarar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _mascarar(v) for k, v in valor.items()}
    return valor


def camadas_da_ficha(texto: str) -> str | None:
    """JSON das camadas (#31) pronto para embutir na página: só FeatureCollection com feições, texto sem documento
    (máscara de CPF/CNPJ em toda string) e `<`, `>`, `&` como \\u003c etc., para nada fechar o <script>. None se o
    arquivo não é uma FeatureCollection legível (a tela fica no SVG)."""
    try:
        dados = json.loads(texto or "")
    except json.JSONDecodeError:
        return None
    if not isinstance(dados, dict) or dados.get("type") != "FeatureCollection" \
            or not isinstance(dados.get("features"), list):
        return None
    feicoes = [f for f in dados["features"] if isinstance(f, dict) and isinstance(f.get("geometry"), dict)
               and isinstance(f.get("properties"), dict)]
    if not feicoes:
        return None
    nao = [c for c in dados.get("camadas_nao_verificadas") or [] if isinstance(c, dict)]
    saida = json.dumps(_mascarar({"type": "FeatureCollection", "camadas_nao_verificadas": nao, "features": feicoes}),
                       ensure_ascii=False, separators=(",", ":"))
    return saida.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


# --- partes da tela -------------------------------------------------------------------------------------------------

def motivo_inconclusivo(ficha: dict) -> str | None:
    if ficha["resultado"].get("situacao") != "inconclusivo":
        return None
    c = next((c for c in ficha["criterios"] if c.get("situacao") == "inconclusivo"), None)
    return (c or {}).get("evidencia") or ficha["resultado"].get("resumo") or "o motivo não veio na ficha"


def veredito(ficha: dict) -> str:
    """Uma frase: quantas pendências, o que elas impedem (do `bloqueia` do plano) e o que ainda não foi verificado."""
    res = ficha["resultado"]
    cont = res.get("contagem") or {}
    pend, indi = cont.get("pendência", 0), cont.get("indício", 0)
    faltam = cont.get("não verificado", 0) + cont.get("inconclusivo", 0)
    if res.get("situacao") == "inconclusivo":
        return (f"Inconclusivo: {_datas_br(motivo_inconclusivo(ficha)).rstrip('.')}. Nada foi concluído sobre o "
                "crédito rural nem sobre a venda sob a EUDR.")
    if pend:
        cartoes = [c for c in ficha.get("plano_de_acao") or [] if c.get("situacao") == "pendência"]
        cred = any((c.get("bloqueia") or {}).get("credito") == "sim" for c in cartoes)
        eudr = any((c.get("bloqueia") or {}).get("eudr") == "sim" for c in cartoes)
        alvo = ("o crédito rural e a venda sob a EUDR" if cred and eudr else "o crédito rural" if cred
                else "a venda sob a EUDR" if eudr else None)
        frase = (f"{_plural(pend, 'pendência', 'pendências')} {'impede' if pend == 1 else 'impedem'} {alvo}" if alvo
                 else f"{_plural(pend, 'pendência', 'pendências')} {'pode' if pend == 1 else 'podem'} impedir o "
                      "crédito rural ou a venda sob a EUDR")
        if indi:
            frase += f"; {_plural(indi, 'indício', 'indícios')} a conferir"
        frase += "."
    elif indi:
        frase = f"Nenhuma pendência; {_plural(indi, 'indício', 'indícios')} a conferir antes de virar pendência."
    else:
        frase = "Sem pendência nas fontes verificadas."
    if faltam:
        frase += f" {_plural(faltam, 'critério ainda sem verificação', 'critérios ainda sem verificação')}: veja o que falta."
    return frase


def _selo_geral(ficha: dict) -> str:
    """Selo do resultado; "sem pendência" com critério sem verificação fica neutro, nunca verde (ADR 0013)."""
    sit = ficha["resultado"].get("situacao", "")
    if sit == "sem pendência nas fontes verificadas" and _faltam(ficha):
        return _selo("não verificado", rotulo=f"Sem pendência {_ressalva(_faltam(ficha))}")
    return _selo(sit)


def _carimbo(ficha: dict) -> str:
    res = ficha["resultado"]
    cont = res.get("contagem") or {}
    sit = res.get("situacao", "")
    _, classe, _ = SITUACAO.get(sit, ("nao", "st-nao", ""))
    pend, indi = cont.get("pendência", 0), cont.get("indício", 0)
    if sit == "inconclusivo":
        miolo = "<b>inconclusivo</b>"
    elif pend:
        miolo = f"<big>{pend}</big>{'pendência' if pend == 1 else 'pendências'}"
    elif indi:
        miolo = f"<big>{indi}</big>{'indício' if indi == 1 else 'indícios'}"
    elif _faltam(ficha):
        classe = "st-nao"
        miolo = f"<b>sem pendência</b>{_ressalva(_faltam(ficha))}"
    else:
        miolo = "<b>sem pendência</b>nas fontes verificadas"
    return f'<div class="carimbo {classe}" aria-hidden="true">{miolo}</div>'


def _eixo(ficha: dict, chave: str, titulo: str, feminino: bool) -> str:
    plano = ficha.get("plano_de_acao")
    if ficha["resultado"].get("situacao") == "inconclusivo":
        icone, cor, texto = "inco", "st-inco", "Não avaliado: falta uma entrada"
    elif plano is None:
        icone, cor, texto = "nao", "st-nao", "Sem plano nesta ficha"
    else:
        sim = [c for c in plano if (c.get("bloqueia") or {}).get(chave) == "sim"]
        talvez = [c for c in plano if (c.get("bloqueia") or {}).get(chave) == "talvez"]
        if sim:
            icone, cor = "pend", "st-pend"
            texto = f"{'Bloqueada' if feminino else 'Bloqueado'}: {_plural(len(sim), 'motivo', 'motivos')}"
        elif talvez:
            icone, cor, texto = "indi", "st-indi", f"Conferir: {_plural(len(talvez), 'ponto', 'pontos')}"
        elif _faltam(ficha):
            icone, cor, texto = "nao", "st-nao", f"Sem bloqueio {_ressalva(_faltam(ficha))}"
        else:
            icone, cor, texto = "sem", "st-sem", "Sem bloqueio nas fontes verificadas"
    return (f'<div class="eixo {cor}">{_ico(icone)}<div><small>{_t(titulo)}</small><b>{_t(texto)}</b></div></div>')


def _url_consulta(ficha: dict, informar: str | None = None) -> str:
    c = ficha.get("consulta") or {}
    cod = (ficha.get("imovel") or {}).get("cod_imovel") or c.get("cod_imovel")
    params = {"car": cod} if cod else {k: c[k] for k in ("lat", "lon") if c.get(k) is not None}
    if informar:
        params["informar"] = informar
    return "/consulta" + (f"?{urlencode(params)}" if params else "")


def _topo(ficha: dict, nome: str) -> str:
    im, c, res = ficha.get("imovel") or {}, ficha.get("consulta") or {}, ficha["resultado"]
    cod = im.get("cod_imovel") or c.get("cod_imovel")
    nome_area = c.get("nome_area") or im.get("nome_area")
    lugar = f"{im['municipio']}/{im.get('uf') or ''}" if im.get("municipio") else None
    titulo = nome_area or (f"Imóvel em {lugar}" if lugar else "Imóvel não localizado")
    id_produtor = c.get("id_produtor") or im.get("id_produtor")
    status = im.get("status_texto")
    fatos = [
        ("CAR", (f'<span class="mono" title="{_t(cod)}">{_t(car_curto(cod))}</span>'
                 f'{_copiar(cod, "Copiar o código do CAR inteiro")}') if cod else '<span class="mu">não localizado</span>'),
        ("Produtor", _t(id_produtor) if id_produtor else '<span class="mu">não informado (consulta avulsa)</span>'),
        ("Área", _t(nome_area) if nome_area else '<span class="mu">não informada</span>'),
        ("Commodity", _t(c.get("commodity")) if c.get("commodity") else '<span class="mu">não informada</span>'),
        ("Tamanho", f"{_num(im['area_geom_ha'])} ha" if im.get("area_geom_ha") is not None else "—"),
        ("Status do CAR", (f"{_t(status)}" + (f' <span class="mu">· {_t(im["condicao"])}</span>' if im.get("condicao")
                                                else "")) if status else '<span class="mu">sem status</span>'),
    ]
    fatos_html = "".join(f'<div{" class=\"f-car\"" if r == "CAR" else ""}><dt>{escape(r)}</dt><dd>{v}</dd></div>'
                         for r, v in fatos)
    gerado = _datas_br(c.get("gerado_em")) or "data não registrada"
    motivo = motivo_inconclusivo(ficha)
    alerta = ""
    if motivo:
        alerta = (f'<div class="motivo" role="note"><b>Por que ficou inconclusivo:</b> {_t(_datas_br(motivo))}'
                  f'<a class="btn b-pri leva" href="{escape(_url_consulta(ficha, "car"))}"><span>Informar agora</span>'
                  f'{_ico("arrow", "ico seta")}</a></div>')
    return f"""<header class="f-topo" aria-labelledby="t-ficha">
  <div class="f-id">
    <p class="sobre">Ficha do imóvel{f' · {_t(lugar)}' if lugar and nome_area else ''}</p>
    <h1 id="t-ficha">{_t(titulo)}</h1>
    <dl class="fatos">{fatos_html}</dl>
  </div>
  <div class="f-veredito">
    {_carimbo(ficha)}
    <div class="frase">
      {_selo_geral(ficha)}
      <p class="veredito">{_t(veredito(ficha))}</p>
      <p class="ressalva">Pré-diagnóstico com fonte e data (gerado em {_t(gerado)}, horário de Brasília); não é
        atestado de conformidade.</p>
    </div>
  </div>
  <div class="eixos">{_eixo(ficha, "credito", "Crédito rural (MCR 2-9)", False)}{_eixo(ficha, "eudr", "Venda sob a EUDR", True)}</div>
  {alerta}
  <div class="f-acoes">
    <button class="btn b-sec acao" type="button" data-imprimir>{_ico("printer")}<span>Imprimir</span></button>
    <a class="btn b-sec leva" href="{escape(_url_consulta(ficha))}"><span>Refazer a consulta</span>{_ico("arrow", "ico seta")}</a>
  </div>
</header>"""


def _no_mapa(ficha: dict, chave: str) -> str:
    if chave in SEM_MAPA:
        return f'<span class="mu">{_t(SEM_MAPA[chave])}</span>' if chave == "lista_suja" else ""
    rotulos = []
    for ev, letra in LETRAS.get(chave, ()):
        n = len((ficha.get("evidencias") or {}).get(ev) or [])
        if n:
            rotulos.append(f"{letra}1" if n == 1 else f"{letra}1–{letra}{n}")
    return f'<span class="mono rot">{_t(" · ".join(rotulos))}</span>' if rotulos else ""


def _cartao(ficha: dict, i: int, c: dict) -> str:
    situacao = c.get("situacao", "")
    bloq = c.get("bloqueia") or {}
    chips = "".join(f"<span>{_t(n)}</span>" for k, n in (("credito", "crédito"), ("eudr", "EUDR"))
                    if bloq.get(k) == "sim") or "<span>conferir</span>"
    impactos = "".join(
        f'<li class="imp {BLOQUEIA.get(bloq.get(k), ("nao", "não informado"))[0]}"><span>{_t(rotulo)}:</span> '
        f'<b>{_t(BLOQUEIA.get(bloq.get(k), ("nao", "não informado"))[1])}</b></li>'
        for k, rotulo in (("credito", "Crédito rural"), ("eudr", "Venda sob a EUDR")))
    passos = []
    for p in c.get("passos") or []:
        orgao = ""
        if p.get("orgao") or p.get("link"):
            site = _link("site oficial", p.get("link")) if p.get("link") else ""
            orgao = (f'<p class="orgao">{_t(p.get("orgao") or "")}{" · " if p.get("orgao") and site else ""}{site}</p>')
        passos.append(f'<li><span class="quem">{_t(p.get("quem") or "")}</span><p>{_t(p.get("acao"))}</p>{orgao}</li>')
    prazo = (f'<div><dt>Prazo ou condição</dt><dd>{_t(_datas_br(c["prazo_ou_condicao"]))}</dd></div>'
             if c.get("prazo_ou_condicao") else "")
    pe = [f"Fonte: {_t(c.get('fonte') or '—')}", f"dado de {_t(_datas_br(c.get('data_evidencia')) or '—')}"]
    if c.get("orgao"):
        pe.append(f"órgão: {_link(c['orgao'], c.get('link'))}")
    if c.get("link_conferido_em"):
        pe.append(f"links conferidos em {_t(_datas_br(c['link_conferido_em']))}")
    ident = f"acao-{i}"
    return f"""<li class="cartao" id="{ident}" aria-labelledby="{ident}-t">
  <div class="cartao-h">{_selo(situacao, f'<span class="chips">{chips}</span>')}<h3 id="{ident}-t">{_t(c.get("criterio"))}</h3></div>
  <dl class="cartao-d">
    <div><dt>O que bloqueia</dt><dd><ul class="imps">{impactos}</ul></dd></div>
    <div><dt>Por quê</dt><dd>{_t(c.get("por_que"))}</dd></div>
    <div><dt>Evidência</dt><dd>{_t(_datas_br(c.get("evidencia")))}
      <span class="no-mapa"><a class="leva" href="#mapa" data-rot="{escape(" ".join(letra for _, letra in LETRAS.get(c.get("chave", ""), ())))}"><span>Ver no mapa</span>{_ico("arrow", "ico seta")}</a>{_no_mapa(ficha, c.get("chave", ""))}</span></dd></div>
    {prazo}
  </dl>
  <h4 class="passos-h">O que fazer</h4>
  <ol class="passos">{"".join(passos)}</ol>
  <p class="cartao-pe">{" · ".join(pe)}</p>
</li>"""


def _plano(ficha: dict) -> str:
    plano = ficha.get("plano_de_acao")
    if plano is None:
        corpo = (f'<p class="estado">Esta ficha foi gerada antes do plano de ação existir. Refaça a consulta para ver '
                 f'o que fazer em cada pendência.</p><a class="btn b-sec leva" href="{escape(_url_consulta(ficha))}">'
                 f'<span>Refazer a consulta</span>{_ico("arrow", "ico seta")}</a>')
        n = "—"
    elif not plano:
        texto = ("Sem plano: o diagnóstico ficou inconclusivo. Informe o que falta e refaça a consulta."
                 if ficha["resultado"].get("situacao") == "inconclusivo" else
                 "Nenhuma pendência nem indício nas fontes verificadas. Isso não é atestado de conformidade: veja o "
                 "que falta logo abaixo.")
        corpo, n = f'<p class="estado">{_t(texto)}</p>', "0"
    else:
        corpo = f'<ol class="cartoes">{"".join(_cartao(ficha, i, c) for i, c in enumerate(plano, 1))}</ol>'
        n = str(len(plano))
    return f"""<section class="bloco" id="plano" aria-labelledby="t-plano">
  <div class="bloco-h"><h2 id="t-plano">Plano de ação</h2><span class="conta">{n}</span></div>
  <p class="mu apoio">Primeiro o que bloqueia crédito rural e venda sob a EUDR; depois o que bloqueia um dos dois; por
    último os indícios a conferir.</p>
  {corpo}
</section>"""


def _informar(entrada: str) -> str | None:
    return next((campo for inicio, campo in INFORMAR if entrada.startswith(inicio)), None)


def _o_que_falta(ficha: dict) -> str:
    itens = ficha.get("o_que_falta")
    if itens is None:
        corpo = '<p class="estado">Esta ficha foi gerada antes desta lista existir. Refaça a consulta para vê-la.</p>'
    elif not itens:
        corpo = '<p class="estado">Nenhuma entrada faltando para os critérios desta ficha.</p>'
    else:
        linhas = []
        for f in itens:
            sits = f.get("situacoes") or []
            selo = _selo(sits[0]) if sits else _selo("não verificado", rotulo="Não informado")
            campo = _informar(str(f.get("entrada") or ""))
            if campo:
                acao = (f'<a class="btn b-pri leva" href="{escape(_url_consulta(ficha, campo))}"><span>Informar agora'
                        f'</span>{_ico("arrow", "ico seta")}</a>')
            elif f.get("link"):
                acao = f'<span class="onde-link">{_link("Onde obter", f["link"], "btn b-sec")}</span>'
            else:
                acao = ""
            criterios = ", ".join(f.get("criterios") or [])
            linhas.append(f"""<li class="falta">
  {selo}
  <div class="falta-t"><b>{_t(f.get("entrada"))}</b>
    <p>Destrava: {_t(f.get("destrava"))}{f' <span class="mu">({_t(criterios)})</span>' if criterios else ''}</p>
    <p class="mu">Quem traz: {_t(f.get("quem"))} · Onde: {_t(f.get("onde"))}</p></div>
  {acao}
</li>""")
        corpo = f'<ul class="faltas">{"".join(linhas)}</ul>'
    n = "—" if itens is None else str(len(itens))
    return f"""<section class="bloco" id="falta" aria-labelledby="t-falta">
  <div class="bloco-h"><h2 id="t-falta">O que falta para fechar o diagnóstico</h2><span class="conta">{n}</span></div>
  <p class="mu apoio">Critério não verificado ou inconclusivo não é &ldquo;sem ocorrência&rdquo;: estas entradas
    destravam a verificação.</p>
  {corpo}
</section>"""


def _mapa(ficha: dict, svgs: dict) -> str:
    if not ficha.get("geometria_car"):
        corpo = '<p class="estado">Sem mapa: o CAR não foi localizado, então não há perímetro para desenhar.</p>'
    elif "mapa" in svgs:
        corpo = f'<div class="svg-mapa">{svgs["mapa"]}</div>'
    else:
        corpo = ('<p class="estado svg-falta">Mapa indisponível: o desenho que acompanha a ficha (o arquivo .html ao lado do '
                 'JSON) não foi encontrado. Refaça a consulta para gerá-lo de novo.</p>')
    sicar = next((p for p in ficha.get("procedencia") or [] if str(p.get("fonte", "")).startswith("SICAR")), None)
    nota = (f'<p class="mu nota">Perímetro do SICAR ({_t(_datas_br(sicar.get("data")))}); cada letra é uma evidência '
            'do plano de ação.</p>') if sicar and ficha.get("geometria_car") else ""
    satelite = _satelite(svgs["camadas"]) if ficha.get("geometria_car") and svgs.get("camadas") else ""
    return f"""<section class="bloco ev" id="mapa" aria-labelledby="t-mapa" tabindex="-1">
  <h2 id="t-mapa">Mapa do imóvel</h2>
  {satelite}{corpo}{nota}{_nao_verificadas(svgs.get("camadas"))}
</section>"""


def _atribuicao(ano: int) -> str:
    return (f'<small class="sat-cred"><a href="https://s2maps.eu" rel="noopener" target="_blank">Sentinel-2 cloudless'
            f'</a> by EOX IT Services GmbH (Contains modified Copernicus Sentinel data {ano}), CC BY 4.0</small>')


def _satelite(camadas: str) -> str:
    """Bloco do mapa de satélite, antes (2020) e depois (mosaico mais recente) lado a lado. Fica `hidden` até o
    mapa.js confirmar que a imagem carregou; sem rede (ou sem JS) a tela segue com o SVG da ficha."""
    dados = json.loads(camadas)
    por_camada: dict[str, list[str]] = {}
    for f in dados["features"]:
        p = f["properties"]
        por_camada.setdefault(str(p.get("camada")), []).append(str(p.get("rotulo") or ""))
    itens = []
    for camada, nome in [*CAMADAS_MAPA.items(), *((c, c) for c in por_camada if c not in CAMADAS_MAPA)]:
        if camada not in por_camada:
            continue
        rot = [r for r in por_camada[camada] if r and r != "CAR"]
        faixa = rot[0] if len(rot) == 1 else f"{rot[0]}–{rot[-1]}" if rot else ""
        itens.append(f'<label><input type="checkbox" checked data-camada="{escape(camada)}">'
                     f'<i class="sw" data-sw="{escape(camada)}"></i>{_t(nome)}'
                     f'{f" <span class=mono>{_t(faixa)}</span>" if faixa else ""}</label>')
    figuras = "".join(
        f'<figure class="sat-m"><figcaption><b>{titulo}</b> · mosaico {ano}{extra}</figcaption>'
        f'<div class="sat-mapa" id="sat-{qual}" role="region" aria-label="Imagem de satélite de {ano} com as camadas '
        f'da ficha"></div>{_atribuicao(ano)}</figure>'
        for qual, titulo, ano, extra in (("antes", "Antes", ANO_ANTES, " (corte da EUDR: 31/12/2020)"),
                                         ("depois", "Depois", ANO_DEPOIS, " (o mais recente publicado)")))
    return f"""<div class="sat" data-sat data-antes="{ANO_ANTES}" data-depois="{ANO_DEPOIS}" hidden>
  <div class="sat-par">{figuras}</div>
  <p class="mu nota">Mosaico anual sem nuvens: junta imagens do ano inteiro, então pode ser anterior ao alerta. As duas
    imagens andam juntas; clique num polígono para ver rótulo, fonte, data e área.</p>
  <fieldset class="sat-camadas"><legend>Camadas (ligar ou desligar)</legend>{"".join(itens)}</fieldset>
</div>
<p class="estado sat-aviso" role="status" hidden>Imagem de satélite indisponível (sem internet ou o provedor não
  respondeu): mostrando o mapa desenhado da ficha.</p>
<script type="application/json" id="camadas-dados">{camadas}</script>
<link rel="stylesheet" href="/estatico/leaflet/leaflet.css">
<script src="/estatico/leaflet/leaflet.js" defer></script>
<script src="/estatico/mapa.js" defer></script>
"""


def _nao_verificadas(camadas: str | None) -> str:
    """Camadas que o GeoJSON não pôde desenhar (ADR 0013): listadas, nunca tomadas por "sem ocorrência"."""
    if not camadas:
        return ""
    nao = json.loads(camadas).get("camadas_nao_verificadas") or []
    if not nao:
        return ""
    itens = "".join(
        f'<li><b>{_t(CAMADAS_MAPA.get(c.get("camada"), c.get("camada") or "camada"))}'
        f'{" " + _t(c["rotulo"]) if c.get("rotulo") else ""}</b>: {_t(c.get("motivo") or "sem motivo registrado")}</li>'
        for c in nao)
    return (f'<div class="nao-ver"><h3>Fora do mapa (não verificado)</h3><p class="mu">A ausência destas camadas no mapa '
            f'não quer dizer que não haja ocorrência.</p><ul>{itens}</ul></div>')


def _tempo(ficha: dict, svgs: dict) -> str:
    if "tempo" in svgs:
        corpo = (f'<div class="rolar" role="region" aria-label="Linha do tempo (role para o lado no celular)" '
                 f'tabindex="0"><div class="svg-tempo">{svgs["tempo"]}</div></div>')
    elif not ficha.get("geometria_car"):
        corpo = '<p class="estado">Sem linha do tempo: o CAR não foi localizado.</p>'
    else:
        corpo = '<p class="estado">Linha do tempo indisponível: o desenho que acompanha a ficha não foi encontrado.</p>'
    return f"""<section class="bloco" id="tempo" aria-labelledby="t-tempo">
  <h2 id="t-tempo">Linha do tempo diante do corte da EUDR</h2>
  <p class="mu apoio">Desmatamento depois de 31/12/2020 conta para a EUDR; antes do corte, não conta.</p>
  {corpo}
</section>"""


def _cargas(ficha: dict) -> dict[str, list[str]]:
    """Cargas do lago citadas nas evidências, por prefixo (ex.: "ibama_embargos" → ["ibama_embargos:2026…"])."""
    cargas: dict[str, list[str]] = {}
    for linhas in (ficha.get("evidencias") or {}).values():
        for r in linhas or []:
            cid = r.get("carga_id") if isinstance(r, dict) else None
            if cid and cid not in cargas.setdefault(str(cid).split(":")[0], []):
                cargas[str(cid).split(":")[0]].append(str(cid))
    return cargas


def _carga_da_fonte(fonte: str, cargas: dict[str, list[str]]) -> list[str]:
    palavras = re.findall(r"\w+", fonte.lower())
    achadas = []
    for prefixo, ids in cargas.items():
        tokens = prefixo.split("_")
        if palavras and tokens[0] == palavras[0] and all(t in palavras for t in tokens[1:2] if t in SUBFONTES):
            achadas += ids
    return achadas


def comando(ficha: dict) -> str:
    """Linha de comando que refaz o pré-diagnóstico. O documento nunca entra: fica o marcador."""
    c, im = ficha.get("consulta") or {}, ficha.get("imovel") or {}
    cod = im.get("cod_imovel") or c.get("cod_imovel")
    partes = [COMANDO]
    if cod:
        partes += ["--car", shlex.quote(cod)]
    elif c.get("lat") is not None and c.get("lon") is not None:
        partes += ["--ponto", str(c["lat"]), str(c["lon"])]
    if c.get("documento_informado"):
        partes += ["--documento", '"<CPF ou CNPJ do proprietário>"']
    if ficha.get("area_producao"):
        partes += ["--area-producao", "<arquivo do talhão>"]
    if c.get("commodity"):
        partes += ["--commodity", shlex.quote(str(c["commodity"]))]
    return " ".join(partes)


def _rastreabilidade(ficha: dict, nome: str) -> str:
    c = ficha.get("consulta") or {}
    procedencia = ficha.get("procedencia") or []
    cargas = _cargas(ficha)
    fontes = []
    for p in procedencia:
        ids = _carga_da_fonte(str(p.get("fonte") or ""), cargas)
        carga = ", ".join(ids) if ids else "—"
        url = _link("endereço da fonte", p.get("url")) if p.get("url") else ""
        fontes.append(f"""<li><b>{_t(p.get("fonte"))}</b>
  <dl><div><dt>Data do dado</dt><dd>{_t(_datas_br(p.get("data")) or "—")} <span class="mu">({_t(p.get("como") or "—")})</span></dd></div>
  <div><dt>Carga</dt><dd class="mono">{_t(carga)}</dd></div>
  <div><dt>SHA-256</dt><dd class="mono hash">{escape(str(p.get("sha256") or "—"))}</dd></div>
  <div><dt>Arquivo</dt><dd class="mono">{_t(p.get("arquivo") or "—")}{f" · {url}" if url else ""}</dd></div></dl></li>""")
    lista = (f'<ul class="fontes">{"".join(fontes)}</ul>' if fontes else
             '<p class="estado">Nenhuma fonte registrada nesta ficha: o resultado não tem procedência para mostrar.</p>')
    prodes = c.get("prodes") or {}
    prodes_txt = (f"PRODES publicado até {_t(prodes['ultimo_ano_do_imovel'])} para o imóvel "
                  f"({_t(prodes.get('origem') or '—')}, verificado em {_t(_datas_br(prodes.get('verificado_em')) or '—')})"
                  if prodes.get("ultimo_ano_do_imovel") else "sem registro do PRODES nesta ficha")
    execucao = (f'<span class="mono">{_t(c["execucao_id"])}</span>' if c.get("execucao_id") else
                "consulta registrada no lago como execução avulsa; o número dela não vem na ficha")
    tem_sicar = any(str(p.get("fonte", "")).startswith("SICAR") for p in procedencia)
    abs_ok = not any(str(x.get("chave", "")).startswith("ab_s") and x.get("situacao") == "não verificado"
                     for x in ficha["criterios"])
    etapas = [("fontes", f"{len(procedencia)} {'fonte' if len(procedencia) == 1 else 'fontes'}", bool(procedencia)),
              ("SICAR", "consultado" if tem_sicar else "sem registro", tem_sicar),
              ("cruzamento", _datas_br(c.get("gerado_em"))[:10] or "—", bool(c.get("gerado_em"))),
              ("AB+S", "verificado" if abs_ok else "não verificado", abs_ok)]
    trilho = "".join(f'<li class="{"ok" if ok else "aberta"}"><b>{_t(n)}</b><span>{_t(t)}</span></li>'
                     for n, t, ok in etapas)
    linha = comando(ficha)
    return f"""<details class="bloco rast" id="rastreabilidade">
  <summary><h2>Rastreabilidade</h2><span class="mu">execução, fontes com data, carga, SHA-256 e o comando que refaz</span></summary>
  <ol class="auditoria" aria-label="Etapas do pré-diagnóstico">{trilho}</ol>
  <dl class="rast-d">
    <div><dt>Execução</dt><dd>{execucao}</dd></div>
    <div><dt>Gerado em</dt><dd>{_t(_datas_br(c.get("gerado_em")) or "—")} (horário de Brasília)</dd></div>
    <div><dt>Documento do proprietário</dt><dd>{"informado e pseudonimizado na consulta; nunca gravado" if c.get("documento_informado") else "não informado"}</dd></div>
    <div><dt>PRODES</dt><dd>{prodes_txt}</dd></div>
    <div><dt>Arquivos da ficha</dt><dd><a href="/fichas/{escape(nome)}.json">{escape(nome)}.json</a> ·
      <a href="/fichas/{escape(nome)}.html">ficha avulsa (HTML)</a></dd></div>
  </dl>
  <h3>Fontes</h3>
  {lista}
  <h3>Comando que reproduz o resultado</h3>
  <div class="cmd"><pre><code>{_t(linha)}</code></pre>{_copiar(linha, "Copiar o comando")}</div>
  <p class="mu nota">Rode da raiz do projeto. O que está entre &lt; &gt; você informa de novo: o documento nunca fica
    gravado.</p>
</details>"""


def renderizar(ficha: dict, nome: str, svgs: dict[str, str] | None = None) -> tuple[str, str]:
    """(título, corpo HTML) da tela. `svgs`: o mapa e a linha do tempo de svgs_da_ficha (vazio → "indisponível")."""
    svgs = svgs or {}
    im, c = ficha.get("imovel") or {}, ficha.get("consulta") or {}
    cod = im.get("cod_imovel") or c.get("cod_imovel")
    titulo = f"Ficha {car_curto(cod)}" if cod else "Ficha do imóvel"
    corpo = f"""<div class="ficha" data-ficha="{escape(nome)}">
{_topo(ficha, nome)}
<div class="mesa-f">
  <div class="fila-f">{_plano(ficha)}{_o_que_falta(ficha)}</div>
  <div class="painel-f">{_mapa(ficha, svgs)}</div>
</div>
{_tempo(ficha, svgs)}
{_rastreabilidade(ficha, nome)}
</div>"""
    return titulo, corpo


def erro(titulo: str, texto: str) -> str:
    """Corpo da tela de erro (ficha não encontrada ou ilegível)."""
    return f"""<section class="vazia" aria-labelledby="t-erro">
  <h1 id="t-erro">{_t(titulo)}</h1>
  <p class="mu">{_t(texto)}</p>
  <a class="btn b-sec leva" href="/consulta"><span>Fazer uma nova consulta</span>{_ico("arrow", "ico seta")}</a>
</section>"""
