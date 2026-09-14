import json

import pipeline.__main__ as execucao
from pipeline import config


def test_falha_da_referencia_registra_fontes_dependentes_como_erro(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DADOS_PROCESSADOS", tmp_path / "processed")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.setenv(config.CHAVE_ENV, "chave-de-teste")

    def referencia_indisponivel(*args, **kwargs):
        raise ConnectionError("sem rede")

    monkeypatch.setattr(execucao, "carregar_referencia", referencia_indisponivel)
    assert execucao.main(["--fontes", "ibama", "deter"]) == 1
    relatorio = json.loads((tmp_path / "processed" / "relatorio_execucao.json").read_text())
    status = {f["fonte"]: (f["status"], f["mensagem"]) for f in relatorio["fontes"]}
    assert status["ibge_municipios"][0] == "erro"
    assert status["ibama_embargos"] == ("erro", "referência de municípios do IBGE indisponível")
    assert status["inpe_deter"] == ("erro", "referência de municípios do IBGE indisponível")
