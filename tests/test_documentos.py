import pandas as pd

from conftest import CHAVE, CNPJ_VALIDO, CPF_VALIDO
from pipeline.documentos import cnpj_valido, cpf_valido, digito_valido, pseudonimizar, somente_digitos, tipo_documento


def test_digito_verificador_de_cpf_e_cnpj():
    assert cpf_valido("11144477735")
    assert not cpf_valido("11144477736")
    assert not cpf_valido("11111111111")
    assert cnpj_valido("11222333000181")
    assert not cnpj_valido("11222333000182")
    assert not cnpj_valido("00000000000000")


def test_normalizacao_tipo_e_validade():
    docs = somente_digitos(pd.Series([CPF_VALIDO, CNPJ_VALIDO, "123", None]))
    assert docs.tolist()[:3] == ["11144477735", "11222333000181", "123"]
    assert tipo_documento(docs).tolist()[:2] == ["CPF", "CNPJ"]
    assert digito_valido(docs).tolist() == [True, True, False, False]


def test_pseudonimizacao_deterministica_e_dependente_da_chave():
    docs = pd.Series(["11144477735", pd.NA], dtype="string")
    h1, h2 = pseudonimizar(docs, CHAVE), pseudonimizar(docs, CHAVE)
    assert h1[0] == h2[0] and len(h1[0]) == 64 and "11144477735" not in h1[0]
    assert pseudonimizar(docs, b"outra-chave")[0] != h1[0]
    assert pd.isna(h1[1])
