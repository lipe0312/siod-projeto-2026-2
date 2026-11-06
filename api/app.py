"""Aplicação FastAPI de leitura (ADR 0020). Só GET; a organização vem só da chave, nunca de parâmetro.

    AGROVALID_DATABASE_URL=postgresql://... uvicorn api.app:app --host 127.0.0.1 --port 8000

Rotas: /saude (sem chave, testa o banco), /v1/carteira, /v1/fichas/{resultado_id}, /v1/mudancas.
Erro do banco vira 503 sem dado parcial; erro inesperado vira 500 genérico; os dois com `request_id`.
"""

import logging
import uuid
from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api import banco, chaves, config, consultas, modelos

log = logging.getLogger("agrovalid.api")
UUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
_portador = HTTPBearer(auto_error=False, description="Chave de API da organização: Authorization: Bearer agv_<ambiente>_…")


def configuracao() -> config.Configuracao:
    return config.carregar()


def conexao(cfg: Annotated[config.Configuracao, Depends(configuracao)]) -> Iterator[psycopg.Connection]:
    """Uma conexão por requisição (sem pool até o dono aprovar psycopg_pool). Os testes trocam por uma compartilhada."""
    if not cfg.url_banco:
        raise psycopg.OperationalError(f"{config.VARIAVEL_URL} não definida")
    conn = banco.conectar(cfg.url_banco)
    try:
        yield conn
    finally:
        conn.close()


def hash_da_chave(cfg: Annotated[config.Configuracao, Depends(configuracao)],
                  credencial: Annotated[HTTPAuthorizationCredentials | None, Depends(_portador)]) -> str:
    """SHA-256 da chave do cabeçalho. Chave de outro ambiente ou fora do formato nem chega ao banco."""
    chave = credencial.credentials if credencial else ""
    if chaves.ambiente_da_chave(chave) != cfg.ambiente:
        raise banco.ChaveInvalida()
    return chaves.hash_da_chave(chave)


Conexao = Annotated[psycopg.Connection, Depends(conexao)]
Hash = Annotated[str, Depends(hash_da_chave)]
v1 = APIRouter(prefix="/v1")


def _ou_404(dado: dict | None, o_que: str) -> dict:
    if dado is None:
        raise HTTPException(status_code=404, detail=o_que)
    return dado


@v1.get("/carteira", response_model=modelos.Carteira, summary="Carteira da última execução da organização")
def carteira(chave: Hash, conn: Conexao):
    with banco.sessao(conn, chave):
        return _ou_404(consultas.carteira(conn), "nenhuma execução da organização")


@v1.get("/fichas/{resultado_id}", response_model=modelos.Ficha, summary="Ficha de um imóvel: critérios e evidências")
def ficha(chave: Hash, conn: Conexao, resultado_id: Annotated[str, Path(pattern=UUID)]):
    with banco.sessao(conn, chave):
        return _ou_404(consultas.ficha(conn, resultado_id), "ficha não encontrada")


@v1.get("/mudancas", response_model=modelos.Mudancas, summary="O que mudou entre as duas últimas execuções")
def mudancas(chave: Hash, conn: Conexao):
    with banco.sessao(conn, chave):
        return _ou_404(consultas.mudancas(conn), "nenhuma execução da organização")


def _erro(request: Request, status: int, mensagem: str, **cabecalhos) -> JSONResponse:
    return JSONResponse(status_code=status, content={"erro": mensagem, "request_id": request.state.request_id},
                        headers={"X-Request-ID": request.state.request_id, **cabecalhos})


def criar_app(cfg: config.Configuracao | None = None) -> FastAPI:
    cfg = cfg or config.carregar()
    local = cfg.local
    app = FastAPI(title="AgroValid: API de leitura", version="1",
                  docs_url="/docs" if local else None, redoc_url=None, openapi_url="/openapi.json" if local else None)
    app.dependency_overrides[configuracao] = lambda: cfg

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        resposta = await call_next(request)
        resposta.headers["X-Request-ID"] = request.state.request_id
        return resposta

    @app.exception_handler(banco.ChaveInvalida)
    async def chave_invalida(request: Request, _erro_):
        return _erro(request, 401, "chave de API ausente ou inválida", **{"WWW-Authenticate": "Bearer"})

    @app.exception_handler(HTTPException)
    async def http(request: Request, exc: HTTPException):
        return _erro(request, exc.status_code, str(exc.detail))

    @app.exception_handler(psycopg.Error)
    async def banco_indisponivel(request: Request, exc: psycopg.Error):
        log.error("[api] banco: %s (request_id=%s)", type(exc).__name__, request.state.request_id)
        return _erro(request, 503, "banco indisponível; tente de novo")

    @app.exception_handler(Exception)
    async def inesperado(request: Request, exc: Exception):
        log.exception("[api] erro inesperado (request_id=%s)", request.state.request_id)
        return _erro(request, 500, "erro interno")

    @app.get("/saude", response_model=modelos.Saude, summary="O banco responde?")
    def saude(conn: Conexao):
        banco.saude(conn)
        return {"banco": "ok"}

    app.include_router(v1)
    return app


app = criar_app()
