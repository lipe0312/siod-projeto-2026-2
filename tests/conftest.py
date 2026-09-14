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
