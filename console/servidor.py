"""Console local do operador (ADR 0027): FastAPI só em 127.0.0.1, importa pipeline/ direto.

Rotas: páginas /consulta, /carteira, /fontes; GET /ficha/{nome} (tela da ficha, lida do JSON gravado);
POST /api/consultas (JSON; o documento só trafega aqui); GET /api/consultas/{id} (polling das etapas);
GET /fichas/{arquivo} (HTML/JSON gerados em data/saidas/console/).
HTML gerado aqui com html.escape; CSS e JS em console/estatico/.
"""

import json
import re
from collections.abc import Callable
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from console import consulta
from console.telas import ficha as tela_ficha

ESTATICO = Path(__file__).parent / "estatico"
HOSTS = ["127.0.0.1", "localhost"]
TAMANHO_MAXIMO_PEDIDO = consulta.TAMANHO_MAXIMO_AREA + 64 * 1024
ARQUIVO_FICHA = re.compile(r"[A-Za-z0-9_-]{1,80}\.(html|json)")
CABECALHOS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
              "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https://tiles.maps.eox.at; style-src 'self' 'unsafe-inline'; "
                                         "frame-ancestors 'none'"}

ABAS = (("carteira", "Carteira"), ("consulta", "Nova consulta"), ("fontes", "Fontes"))

ICONES = {
    "logo": ('8 -1 84 107', '<path stroke="none" fill="currentColor" d="M8.578 87.431L26.368 49.873L23.111 42.233L31.728 '
             '38.559L50 -0.016L68.272 38.559L76.889 42.233L73.632 49.873L91.422 87.431L80.578 92.569L67.342 64.626L50 '
             '105.298L32.658 64.626L19.422 92.569ZM39.524 50.132L50 74.702L60.476 50.132L50 28.016L39.524 50.132Z"/>'),
    "pend": ('0 0 24 24', '<path d="m15 9-6 6"/><path d="M2.586 16.726A2 2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-'
             '4.688A2 2 0 0 1 8.688 2h6.624a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 '
             '1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586z"/><path d="m9 9 6 6"/>'),
    "indi": ('0 0 24 24', '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
             '<path d="M12 9v4"/><path d="M12 17h.01"/>'),
    "sem": ('0 0 24 24', '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>'),
    "inco": ('0 0 24 24', '<path d="M12.75 7.09a3 3 0 0 1 2.16 2.16"/><path d="M17.072 17.072c-1.634 2.17-3.527 3.912-'
             '4.471 4.727a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 1.432-4.568"/><path d="m2 2 20 20"/>'
             '<path d="M8.475 2.818A8 8 0 0 1 20 10c0 1.183-.31 2.377-.81 3.533"/><path d="M9.13 9.13a3 3 0 0 0 3.74 '
             '3.74"/>'),
    "nao": ('0 0 24 24', '<path d="M10.1 2.182a10 10 0 0 1 3.8 0"/><path d="M13.9 21.818a10 10 0 0 1-3.8 0"/><path '
            'd="M17.609 3.721a10 10 0 0 1 2.69 2.7"/><path d="M2.182 13.9a10 10 0 0 1 0-3.8"/><path d="M20.279 17.609a10 '
            '10 0 0 1-2.7 2.69"/><path d="M21.818 10.1a10 10 0 0 1 0 3.8"/><path d="M3.721 6.391a10 10 0 0 1 2.7-2.69"/>'
            '<path d="M6.391 20.279a10 10 0 0 1-2.69-2.7"/>'),
    "arrow": ('0 0 24 24', '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>'),
    "search": ('0 0 24 24', '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'),
    "loader": ('0 0 24 24', '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>'),
    "list": ('0 0 24 24', '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/>'
             '<path d="M8 18h13"/><path d="M8 6h13"/>'),
    "plus": ('0 0 24 24', '<path d="M5 12h14"/><path d="M12 5v14"/>'),
    "file": ('0 0 24 24', '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 '
             '2 0 0 0 2 2h4"/>'),
    "redo": ('0 0 24 24', '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>'),
    "copy": ('0 0 24 24', '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-'
             '1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>'),
    "printer": ('0 0 24 24', '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
                '<path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>'),
}


def _sprite() -> str:
    simbolos = "".join(f'<symbol id="i-{nome}" viewBox="{caixa}">{corpo}</symbol>' for nome, (caixa, corpo) in ICONES.items())
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{simbolos}</svg>'


def ico(nome: str, classe: str = "ico") -> str:
    return f'<svg class="{classe}" aria-hidden="true"><use href="#i-{nome}"/></svg>'


def pagina(ativa: str, titulo: str, corpo: str, estilos: tuple[str, ...] = ()) -> str:
    abas = "".join(
        f'<a class="aba" href="/{chave}"{" aria-current=\"page\"" if chave == ativa else ""}>'
        f'{ico({"carteira": "list", "consulta": "plus", "fontes": "file"}[chave])}<span>{escape(nome)}</span></a>'
        for chave, nome in ABAS)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)} · AgroValid</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="/estatico/base.css">
{"".join(f'<link rel="stylesheet" href="/estatico/{escape(e)}">' for e in estilos)}
</head>
<body data-pagina="{escape(ativa)}">
{_sprite()}
<a class="pular" href="#principal">Pular para o conteúdo</a>
<header class="barra">
  <div class="barra-in">
    <a class="marca" href="/consulta">{ico("logo", "ico logo")}<span>AgroValid</span></a>
    <nav class="abas" aria-label="Telas">{abas}</nav>
    <button class="busca" type="button" data-busca aria-keyshortcuts="Control+K Meta+K">
      {ico("search")}<span class="busca-txt">CAR, produtor ou comando</span><kbd>Ctrl K</kbd>
    </button>
  </div>
</header>
<main id="principal" class="conteudo">
{corpo}
</main>
<script src="/estatico/console.js" defer></script>
</body>
</html>"""


def tela_consulta() -> str:
    commodities = "".join(
        f'<label class="opcao"><input type="radio" name="commodity" value="{escape(c)}"> {escape(c)}</label>'
        for c in consulta.COMMODITIES)
    return pagina("consulta", "Nova consulta", f"""
<div class="mesa">
<section class="col" aria-labelledby="t-consulta">
  <h1 id="t-consulta">Nova consulta</h1>
  <p class="mu apoio">Digite o código do CAR ou a coordenada da sede. O console cruza o imóvel com as fontes públicas e gera a ficha.</p>
  <form id="form-consulta" method="post" action="/api/consultas" novalidate>
    <fieldset class="modo">
      <legend class="sr">Buscar por</legend>
      <label class="seg"><input type="radio" name="modo" value="car" checked> Código do CAR</label>
      <label class="seg"><input type="radio" name="modo" value="ponto"> Coordenada</label>
    </fieldset>
    <div class="campo" data-modo="car">
      <label for="car">Código do CAR</label>
      <input id="car" name="car" class="mono" autocomplete="off" spellcheck="false" autocapitalize="characters"
             placeholder="MG-3148103-0A1B2C…" aria-describedby="car-ajuda" maxlength="60">
      <p id="car-ajuda" class="ajuda" aria-live="polite">UF, código IBGE do município (7 dígitos) e 32 letras ou números, separados por hífen.</p>
    </div>
    <div class="campo duplo" data-modo="ponto" hidden>
      <div><label for="lat">Latitude</label><input id="lat" name="lat" inputmode="decimal" autocomplete="off" placeholder="-18,9431"></div>
      <div><label for="lon">Longitude</label><input id="lon" name="lon" inputmode="decimal" autocomplete="off" placeholder="-46,9925"></div>
      <p class="ajuda">Graus decimais, como o GPS mostra. Se mais de um CAR contém o ponto, a ficha pede o código.</p>
    </div>
    <details class="completar">
      <summary>Completar a consulta <span class="mu">documento, área de produção, commodity</span></summary>
      <div class="campo">
        <label for="documento">CPF ou CNPJ do proprietário</label>
        <input id="documento" name="documento" class="mono" inputmode="numeric" autocomplete="off" spellcheck="false"
               maxlength="18" aria-describedby="doc-aviso" placeholder="000.000.000-00">
        <p id="doc-aviso" class="ajuda">Vira um código irreversível na hora e não é gravado. Serve para conferir a Lista Suja.</p>
      </div>
      <div class="campo">
        <label for="area">Área de produção <span class="mu">KML ou GeoJSON, até 2 MB</span></label>
        <input id="area" name="area" type="file" accept=".kml,.geojson,.json" aria-describedby="area-ajuda">
        <p id="area-ajuda" class="ajuda" aria-live="polite">O desmatamento é cruzado com essa área e, separado, com o resto do imóvel.</p>
      </div>
      <fieldset class="campo">
        <legend>Commodity</legend>
        <div class="opcoes">{commodities}</div>
      </fieldset>
    </details>
    <p class="erro" id="erro" role="alert" hidden></p>
    <button class="btn b-pri acao" id="cruzar" type="submit">Cruzar agora</button>
  </form>
</section>
<section class="col painel" aria-labelledby="t-cruzamento">
  <h2 id="t-cruzamento">Cruzamento</h2>
  <p class="mu vazio" id="vazio">As seis fontes aparecem aqui, uma por linha, quando você cruzar: SICAR, PRODES da UF, IBAMA, DETER, Lista Suja e áreas protegidas.</p>
  <p class="andamento" id="andamento" hidden aria-live="polite"></p>
  <ol class="etapas" id="etapas" aria-live="polite" hidden></ol>
  <div class="resultado" id="resultado" hidden tabindex="-1"></div>
</section>
</div>""")


def tela_vazia(chave: str, titulo: str, texto: str) -> str:
    return pagina(chave, titulo, f"""
<section class="vazia" aria-labelledby="t-{escape(chave)}">
  <h1 id="t-{escape(chave)}">{escape(titulo)}</h1>
  <p class="mu">{escape(texto)}</p>
  <a class="btn b-sec leva" href="/consulta"><span>Fazer uma nova consulta</span>{ico("arrow", "ico seta")}</a>
</section>""")


def criar_app(executar: Callable[..., dict] | None = None, hosts: list[str] | None = None) -> FastAPI:
    """`executar`: o pré-diagnóstico (padrão: pipeline.prediagnostico.executar); os testes injetam um falso."""
    app = FastAPI(title="AgroValid, console local", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts or HOSTS)
    app.state.consultas = consulta.Consultas(executar)
    app.mount("/estatico", StaticFiles(directory=ESTATICO), name="estatico")

    @app.middleware("http")
    async def cabecalhos(request: Request, chamar):
        resposta = await chamar(request)
        for k, v in CABECALHOS.items():
            resposta.headers.setdefault(k, v)
        return resposta

    @app.get("/", include_in_schema=False)
    def raiz():
        return RedirectResponse("/consulta", status_code=303)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @app.get("/consulta", response_class=HTMLResponse)
    def nova_consulta():
        return tela_consulta()

    @app.get("/carteira", response_class=HTMLResponse)
    def carteira():
        return tela_vazia("carteira", "Carteira", "A carteira da cooperativa, com os imóveis em ordem de prioridade, "
                          "chega aqui numa próxima entrega. Por enquanto, consulte um imóvel de cada vez.")

    @app.get("/fontes", response_class=HTMLResponse)
    def fontes():
        return tela_vazia("fontes", "Fontes", "A data e a procedência de cada fonte pública aparecem aqui numa "
                          "próxima entrega; hoje elas estão no fim de cada ficha.")

    @app.get("/ficha/{nome}", response_class=HTMLResponse)
    def ficha_tela(nome: str):
        """Tela da ficha: lê o JSON gravado em data/saidas/console/ (e o mapa do HTML ao lado); não recalcula."""
        try:
            dados, svgs = tela_ficha.ler(consulta.pasta_saida(), nome)
            titulo, corpo = tela_ficha.renderizar(dados, nome, svgs)
        except FileNotFoundError:
            return HTMLResponse(pagina("ficha", "Ficha não encontrada", tela_ficha.erro(
                "Ficha não encontrada", "Não há ficha com esse nome no console. Ela pode ter sido gerada em outra "
                "máquina ou apagada; faça a consulta de novo."), ("ficha.css",)), status_code=404)
        except (tela_ficha.FichaIlegivel, KeyError, TypeError, AttributeError) as e:
            motivo = str(e) if isinstance(e, tela_ficha.FichaIlegivel) else "o arquivo não tem o formato de uma ficha"
            return HTMLResponse(pagina("ficha", "Ficha ilegível", tela_ficha.erro(
                "A ficha não pôde ser lida", f"Motivo: {motivo}. Refaça a consulta para gerar a ficha de novo."),
                ("ficha.css",)), status_code=500)
        return pagina("ficha", titulo, corpo, ("ficha.css",))

    @app.post("/api/consultas", status_code=202)
    async def nova(request: Request):
        """O corpo é lido à mão (sem modelo pydantic): o erro de validação nunca devolve o que foi digitado."""
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"erro": "envie o pedido como application/json"}, status_code=415)
        corpo = await request.body()
        if len(corpo) > TAMANHO_MAXIMO_PEDIDO:
            return JSONResponse({"erro": "pedido maior que o permitido (área de produção até 2 MB)"}, status_code=413)
        try:
            dados = json.loads(corpo)
            entrada = consulta.validar(dados)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse({"erro": "pedido mal formado"}, status_code=400)
        except consulta.EntradaInvalida as e:
            return JSONResponse({"erro": str(e)}, status_code=422)
        except consulta.ChaveIndisponivel as e:
            return JSONResponse({"erro": str(e)}, status_code=500)
        try:
            ident = app.state.consultas.iniciar(entrada)
        except RuntimeError as e:
            return JSONResponse({"erro": str(e)}, status_code=409)
        return {"id": ident}

    @app.get("/api/consultas/{ident}")
    def andamento(ident: str):
        estado = app.state.consultas.publico(ident) if re.fullmatch(r"[0-9a-f]{32}", ident) else None
        if estado is None:
            raise HTTPException(404, "consulta não encontrada")
        return estado

    @app.get("/fichas/{arquivo}")
    def ficha(arquivo: str):
        if not ARQUIVO_FICHA.fullmatch(arquivo):
            raise HTTPException(404, "ficha não encontrada")
        pasta = consulta.pasta_saida().resolve()
        caminho = (pasta / arquivo).resolve()
        if not caminho.is_relative_to(pasta) or not caminho.is_file():
            raise HTTPException(404, "ficha não encontrada")
        resposta = FileResponse(caminho)
        resposta.headers["Content-Security-Policy"] = "frame-ancestors 'none'"  # a ficha tem o estilo dela, inline
        return resposta

    return app
