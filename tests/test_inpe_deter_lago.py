"""DETER no lago (ref.alerta_deter): gravação por acréscimo e descartes em meta.descarte, sem rede e sem data/processed."""

import gzip
import json

import pytest

from conftest import HOJE
from pipeline import config
from pipeline.armazenamento import lago
from pipeline.fontes import inpe_deter
from test_inpe_deter import feature, resposta


@pytest.fixture
def fonte(tmp_path, monkeypatch):
    """executar() sem rede: o download mensal é trocado por respostas gravadas na pasta do teste. Devolve a lista de
    features que a "fonte" responde; mudar a lista simula a fonte mudando."""
    for nome, valor in (("RAIZ", tmp_path), ("DADOS_BRUTOS", tmp_path / "raw"), ("DADOS_PROCESSADOS", tmp_path / "processed"),
                        ("LAGO", tmp_path / "lago"), ("TRABALHO", tmp_path / "trabalho"), ("DETER_ARQUIVOS", {}),
                        ("CAMADAS_DETER", {"amazonia": config.CAMADAS_DETER["amazonia"]})):
        monkeypatch.setattr(config, nome, valor)
    features = [feature("1")]

    def baixar_camada(nome, desde, hoje, atualizar):
        pasta = config.DADOS_BRUTOS / "inpe_deter" / nome / f"desde_{desde}"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "2022-03.json.gz").write_bytes(gzip.compress(json.dumps(resposta(features)).encode()))
        (pasta / "manifesto.json").write_text("{}")
        return {"total_anunciado": len(features), "particoes": [{"inicio": "2022-03-01", "arquivo": "2022-03.json.gz"}]}

    monkeypatch.setattr(inpe_deter, "baixar_camada", baixar_camada)
    return features


def test_grava_no_lago_com_descartes_e_nada_em_processed(fonte, ref_municipios, tmp_path):
    fonte.append(feature("2", data="2022-03-02", classe="DEGRADACAO"))
    r = inpe_deter.executar(ref_municipios, HOJE)
    vigente = lago.ler("ref.alerta_deter")
    assert len(vigente) == 1 and vigente["id_alerta"].iloc[0].startswith("amazonia:1:")
    assert r.saida["tabelas"]["ref.alerta_deter"]["inseridos"] == 1
    assert r.saida["arquivo"] == "lago/ref/alerta_deter" and r.saida["registros_produzidos"] == 1
    descarte = lago.ler("meta.descarte")
    assert descarte["motivo"].tolist() == ["DETER_CLASSE_FORA_DO_RECORTE"]
    assert descarte["registro_id"].iloc[0].startswith("amazonia:2:") and descarte["fonte"].iloc[0] == "inpe_deter"
    assert not (tmp_path / "processed").exists()  # nada mais em data/processed


def test_segunda_execucao_nao_insere_nem_altera(fonte, ref_municipios):
    inpe_deter.executar(ref_municipios, HOJE)
    r = inpe_deter.executar(ref_municipios, HOJE)
    resumo = r.saida["tabelas"]["ref.alerta_deter"]
    assert resumo["inseridos"] == 0 and resumo["alterados"] == 0 and resumo["particoes_gravadas"] == []
    assert len(lago.ler("ref.alerta_deter")) == 1


def test_alerta_novo_entra_e_o_que_sumiu_da_fonte_continua(fonte, ref_municipios):
    inpe_deter.executar(ref_municipios, HOJE)
    fonte[:] = [feature("3", data="2022-03-05")]  # o alerta 1 deixou de vir; o 3 é novo
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert r.saida["tabelas"]["ref.alerta_deter"]["inseridos"] == 1
    assert sorted(i.split(":")[1] for i in lago.ler("ref.alerta_deter")["id_alerta"]) == ["1", "3"]
