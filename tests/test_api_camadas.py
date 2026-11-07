"""API sem banco: camadas isoladas (ADR 0019), formato da chave (ADR 0021), /docs só no local e erros (ADR 0020)."""

import ast
import re
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from api import app as api_app
from api import chaves, config

RAIZ = Path(__file__).resolve().parents[1]
PROIBIDOS_NA_API = {"pipeline", "pandas", "pyarrow", "geopandas", "shapely"}


def _modulos(pasta: Path) -> list[Path]:
    return sorted(pasta.rglob("*.py"))


def _importados(arquivo: Path) -> set[str]:
    nomes = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            nomes |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            nomes.add(no.module.split(".")[0])
    return nomes


def _textos_fora_de_docstring(arquivo: Path) -> list[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    docstrings = {id(n.body[0].value) for n in ast.walk(arvore)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
                  and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(arvore)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def test_api_nao_importa_pipeline_nem_le_o_lago():
    arquivos = _modulos(RAIZ / "api")
    assert arquivos
    for arquivo in arquivos:
        assert not _importados(arquivo) & PROIBIDOS_NA_API, arquivo
        for texto in _textos_fora_de_docstring(arquivo):
            assert "lago" not in texto and "data/" not in texto and ".parquet" not in texto, (arquivo, texto)


def test_pipeline_nao_importa_api():
    for arquivo in _modulos(RAIZ / "pipeline"):
        assert "api" not in _importados(arquivo), arquivo


def test_chave_tem_prefixo_do_ambiente_e_so_o_hash_sai_dela():
    chave = chaves.gerar("local")
    assert chave.startswith("agv_local_") and chaves.ambiente_da_chave(chave) == "local"
    assert chaves.gerar("local") != chave
    h = chaves.hash_da_chave(chave)
    assert re.fullmatch(r"[0-9a-f]{64}", h) and chave not in h
    assert chaves.identificador(chave) == chave[:len("agv_local_") + 6]
    assert chaves.ambiente_da_chave(chaves.gerar("producao")) == "producao"
    for ruim in ("", "agv_local_curta", "xyz_local_" + "a" * 43, "agv_teste_" + "a" * 43, chave + "!",
                 chave + "\n"):  # `$` aceitaria a quebra de linha no fim; fullmatch não
        assert chaves.ambiente_da_chave(ruim) is None
    with pytest.raises(ValueError):
        chaves.gerar("teste")


def test_ambiente_desconhecido_e_recusado(monkeypatch):
    monkeypatch.setenv(config.VARIAVEL_AMBIENTE, "qualquer")
    with pytest.raises(config.ConfiguracaoInvalida):
        config.carregar()


def test_ambiente_ausente_falha_fechado(monkeypatch):
    monkeypatch.delenv(config.VARIAVEL_AMBIENTE, raising=False)
    cfg = config.carregar()
    assert cfg.ambiente is None and not cfg.local


def _cliente(ambiente: str | None = "local", conexao=None) -> TestClient:
    app = api_app.criar_app(config.Configuracao(url_banco=None, ambiente=ambiente))
    if conexao:
        app.dependency_overrides[api_app.conexao] = conexao
    return TestClient(app, raise_server_exceptions=False)


def test_docs_so_no_ambiente_local():
    assert _cliente("local").get("/docs").status_code == 200
    assert _cliente("local").get("/openapi.json").status_code == 200
    for ambiente in ("homologacao", "producao", None):
        cliente = _cliente(ambiente)
        assert cliente.get("/docs").status_code == 404
        assert cliente.get("/openapi.json").status_code == 404
        assert cliente.get("/redoc").status_code == 404


def test_rotas_versionadas_e_nenhum_campo_de_documento_no_contrato_da_api():
    esquema = _cliente().get("/openapi.json").json()
    assert set(esquema["paths"]) == {"/saude", "/v1/carteira", "/v1/fichas/{resultado_id}", "/v1/mudancas"}
    assert all(list(m) == ["get"] for m in esquema["paths"].values())  # só leitura
    texto = str(esquema).lower()
    assert "documento" not in texto and "cpf" not in texto and "cnpj" not in texto
    for nome in ("Carteira", "Ficha", "Mudancas"):  # toda resposta leva a execução e as fontes
        assert {"execucao", "fontes"} <= set(esquema["components"]["schemas"][nome]["properties"])
    assert {"fonte", "carga_id", "data"} <= set(esquema["components"]["schemas"]["FonteUsada"]["properties"])


def test_sem_chave_ou_chave_de_outro_ambiente_da_401_sem_tocar_no_banco():
    def nunca():
        raise AssertionError("não deveria abrir conexão")
        yield  # pragma: no cover

    cliente = _cliente("local", nunca)
    for cabecalho in ({}, {"Authorization": "Bearer xyz"},
                      {"Authorization": f"Bearer {chaves.gerar('producao')}"}):
        r = cliente.get("/v1/carteira", headers=cabecalho)
        assert r.status_code == 401
        assert r.json()["erro"] == "chave de API ausente ou inválida" and r.json()["request_id"]


def test_sem_ambiente_declarado_nenhuma_chave_entra():
    def nunca():
        raise AssertionError("não deveria abrir conexão")
        yield  # pragma: no cover

    cliente = _cliente(None, nunca)
    for ambiente in config.AMBIENTES:
        r = cliente.get("/v1/carteira", headers={"Authorization": f"Bearer {chaves.gerar(ambiente)}"})
        assert r.status_code == 401


def _falha():
    raise psycopg.OperationalError("connection refused: segredo-que-nao-pode-vazar")
    yield  # pragma: no cover


def test_banco_fora_do_ar_vira_503_sem_detalhe():
    cliente = _cliente("local", _falha)
    for caminho, cabecalho in (("/saude", {}), ("/v1/carteira", {"Authorization": f"Bearer {chaves.gerar('local')}"})):
        r = cliente.get(caminho, headers=cabecalho)
        assert r.status_code == 503
        assert r.json()["erro"] == "banco indisponível; tente de novo"
        assert r.headers["X-Request-ID"] == r.json()["request_id"]
        assert "segredo" not in r.text


def test_sem_url_do_banco_vira_503():
    assert _cliente("local").get("/saude").status_code == 503


def test_erro_inesperado_vira_500_generico():
    class Quebrada:
        def execute(self, *a, **k):
            raise RuntimeError("detalhe interno")

    def quebrada():
        yield Quebrada()

    r = _cliente("local", quebrada).get("/saude")
    assert r.status_code == 500
    assert r.json()["erro"] == "erro interno" and "detalhe" not in r.text
