import pandas as pd
import pytest

from pipeline.municipios import normalizar_nome

CHAVE = b"chave-de-teste"
HOJE = pd.Timestamp("2026-09-13 12:00:00")

# Documentos fictícios com dígito verificador válido.
CPF_VALIDO = "111.444.777-35"
CPF_VALIDO_2 = "529.982.247-25"
CNPJ_VALIDO = "11.222.333/0001-81"


@pytest.fixture
def ref_municipios():
    dados = [("1505486", "Pacajá", "PA"), ("2927408", "Salvador", "BA"), ("5107800", "Santo Antônio de Leverger", "MT"),
             ("3106200", "Belo Horizonte", "MG")]
    ref = pd.DataFrame(dados, columns=["cod_municipio", "municipio", "uf"])
    ref["chave"] = ref["municipio"].map(normalizar_nome) + "|" + ref["uf"]
    return ref


def ocorrencias(resultado, codigo):
    return next(v.ocorrencias for v in resultado.validacoes if v.codigo == codigo)


def pytest_addoption(parser):
    parser.addoption("--rede", action="store_true", help="roda também os testes que consultam serviços reais")
    parser.addoption("--banco", action="store_true",
                     help="roda também os testes que usam um Postgres/PostGIS local (banco/docker-compose.yml)")


def pytest_configure(config):
    config.addinivalue_line("markers", "rede: consulta um serviço real; só roda com --rede")
    config.addinivalue_line("markers", "banco: usa um Postgres/PostGIS local; só roda com --banco")


def pytest_collection_modifyitems(config, items):
    for opcao, marca, motivo in (("--rede", "rede", "consulta à rede; use --rede"),
                                 ("--banco", "banco", "precisa do Postgres local; use --banco")):
        if config.getoption(opcao):
            continue
        pular = pytest.mark.skip(reason=motivo)
        for item in items:
            if marca in item.keywords:
                item.add_marker(pular)


@pytest.fixture(autouse=True)
def lago_temporario(tmp_path, monkeypatch):
    """Nenhum teste lê ou grava em data/ (lago, chave de pseudonimização, brutos, saídas): cada um tem o seu, vazio.

    Assim a suíte passa também no GitHub Actions, onde data/ não existe."""
    from pipeline import config

    monkeypatch.setattr(config, "LAGO", tmp_path / "lago")
    monkeypatch.setattr(config, "CHAVE_ARQUIVO", tmp_path / "chave_pseudonimizacao")
    monkeypatch.setenv(config.CHAVE_ENV, "chave-de-teste-ci")  # nunca a chave real (env ou data/)
    for nome in ("DADOS_BRUTOS", "DADOS_PROCESSADOS", "LOGS", "TRABALHO", "SAIDAS"):
        monkeypatch.setattr(config, nome, tmp_path / nome.lower())
