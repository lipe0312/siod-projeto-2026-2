import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from conftest import CHAVE, CPF_VALIDO, ocorrencias  # noqa: E402
from pipeline.fontes import ab_s  # noqa: E402
from pipeline.validacao import ErroDeValidacao  # noqa: E402

UUID = "57e267ec-70b4-4d46-bef8-535b8b49b5f9"


def pdf_sintetico(destino, texto_rodape):
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.08, 0.95, "RELATÓRIO DE VERIFICAÇÃO (documento sintético de teste)", fontsize=11)
    if texto_rodape:
        fig.text(0.08, 0.20, texto_rodape, fontsize=9)
    fig.savefig(destino, format="pdf")
    plt.close(fig)
    return destino


@pytest.mark.parametrize("texto, valido", [
    (UUID, True), (UUID.upper(), True), ("nao-e-um-uuid", False), (UUID[:-1], False),
    (UUID.replace("-", ""), False), (UUID.replace("f", "g"), False),
])
def test_validar_uuid(texto, valido):
    assert ab_s.validar_uuid(texto)["formato_valido"] is valido


def test_interpretacao_de_404_e_500():
    assert ab_s.interpretar(404, {}, "13/10/2026") == "não localizado na consulta pública em 13/10/2026"
    assert ab_s.interpretar(500, {}, "13/10/2026").startswith("erro do serviço (HTTP 500)")
    assert ab_s.interpretar(200, {}, "13/10/2026") == "localizado"


def test_extrai_uuid_do_pdf(tmp_path):
    com = pdf_sintetico(tmp_path / "com.pdf", f"Código de autenticidade: {UUID}")
    sem = pdf_sintetico(tmp_path / "sem.pdf", None)
    assert ab_s.extrair_uuid(com) == UUID and ab_s.extrair_uuid(sem) is None


def test_uuid_malformado_nao_vai_a_rede(monkeypatch):
    monkeypatch.setattr(ab_s, "consultar_url", lambda *a, **k: pytest.fail("não deveria consultar"))
    with pytest.raises(ErroDeValidacao, match="ABS_UUID_FORMATO_INVALIDO"):
        ab_s.consultar("nao-e-um-uuid", CHAVE)


def test_consulta_registra_404_como_nao_localizado_e_500_como_erro(monkeypatch, tmp_path):
    from pipeline import config
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(config, "DADOS_BRUTOS", tmp_path / "raw")
    status = {"qualificacao": 404, "habilitacao": 500, "area-producao": 404}

    def falso(url, destino, **kwargs):
        endpoint = url.split("/")[-2]
        corpo = json.dumps({"status": status[endpoint], "message": "Não foi encontrado nenhum registro"}).encode()
        return corpo, {"status_http": status[endpoint], "consultado_em_utc": "2026-10-13T22:27:26+00:00",
                       "sha256": "x"}

    monkeypatch.setattr(ab_s, "consultar_url", falso)
    df, r = ab_s.consultar(UUID, CHAVE)
    assert df["situacao"].tolist()[0] == "não localizado na consulta pública em 13/10/2026"
    assert ocorrencias(r, "ABS_NAO_LOCALIZADO") == 2 and ocorrencias(r, "ABS_ERRO_SERVICO") == 1


def test_documento_na_resposta_e_pseudonimizado():
    dados = {"produtor": {"cpfCnpj": CPF_VALIDO, "nome": "x"}, "obs": f"CPF {CPF_VALIDO} consultado"}
    novo, trocas = ab_s.pseudonimizar_resposta(dados, CHAVE)
    texto = json.dumps(novo)
    assert trocas == 2 and CPF_VALIDO not in texto and novo["produtor"]["cpfCnpj"].startswith("hmac:")


def test_matriz_tem_os_nove_criterios():
    assert ab_s.CRITERIOS["n"].tolist() == list(range(1, 10))
    assert set(ab_s.CRITERIOS["cobertura_projeto"]) <= {"verifica", "parcial", "não verifica"}
