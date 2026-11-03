import json

import pandas as pd
import pytest

from apoio_lago import relogio_que_avanca, usar_lago_temporario
from pipeline import municipios
from pipeline.armazenamento import lago
from pipeline.municipios import construir_referencia, normalizar_nome, resolver_por_nome
from pipeline.validacao import ErroDeValidacao, ResultadoFonte


def municipio(cod, nome, uf):
    return {"id": cod, "nome": nome, "microrregiao": {"mesorregiao": {"UF": {"sigla": uf}}}}


def test_normalizacao_de_nome():
    assert normalizar_nome("Alta Floresta D'Oeste") == "ALTA FLORESTA D OESTE"
    assert normalizar_nome("SANTA FÉ DE MINAS") == "SANTA FE DE MINAS"


def test_resolucao_por_nome_com_apelido(ref_municipios):
    nomes = pd.Series(["PACAJA", "SANTO ANTONIO DO LEVERGER", "INEXISTENTE"])
    ufs = pd.Series(["PA", "MT", "PA"])
    codigos, corrigidos = resolver_por_nome(nomes, ufs, ref_municipios)
    assert codigos.tolist()[:2] == ["1505486", "5107800"] and pd.isna(codigos[2])
    assert corrigidos.tolist() == [False, True, False]


def test_referencia_pequena_interrompe():
    with pytest.raises(ErroDeValidacao, match="IBGE_QUANTIDADE_INESPERADA"):
        construir_referencia([municipio(1, "A", "PA")], ResultadoFonte("ibge", "API"))


def test_referencia_com_codigo_duplicado_interrompe():
    dados = [municipio(i, f"M{i}", "PA") for i in range(5600)] + [municipio(0, "Outro", "PA")]
    with pytest.raises(ErroDeValidacao, match="IBGE_CODIGO_DUPLICADO"):
        construir_referencia(dados, ResultadoFonte("ibge", "API"))


def test_estrutura_invalida_interrompe():
    with pytest.raises(ErroDeValidacao, match="IBGE_ESTRUTURA_RESPOSTA"):
        construir_referencia({"erro": "x"}, ResultadoFonte("ibge", "API"))


def test_municipio_sem_uf_interrompe():
    dados = [municipio(i, f"M{i}", "PA") for i in range(5600)] + [{"id": 9999999, "nome": "Sem UF"}]
    with pytest.raises(ErroDeValidacao, match="IBGE_UF_AUSENTE"):
        construir_referencia(dados, ResultadoFonte("ibge", "API"))


def test_nome_e_uf_repetidos_interrompem():
    dados = [municipio(i, f"M{i}", "PA") for i in range(5600)] + [municipio(9999999, "M1", "PA")]
    with pytest.raises(ErroDeValidacao, match="IBGE_NOME_UF_DUPLICADO"):
        construir_referencia(dados, ResultadoFonte("ibge", "API"))


def test_referencia_grava_no_lago_e_so_cria_carga_nova_quando_muda(tmp_path, monkeypatch):
    usar_lago_temporario(monkeypatch, tmp_path)
    relogio_que_avanca(monkeypatch)
    monkeypatch.setattr(municipios, "baixar", lambda *a, **k: {})
    arquivo = tmp_path / "data" / "raw" / "ibge_municipios.json"
    arquivo.parent.mkdir(parents=True)
    dados = [municipio(i, f"M{i}", "PA") for i in range(5600)]
    arquivo.write_text(json.dumps(dados))

    ref, primeira = municipios.carregar_referencia()
    _, igual = municipios.carregar_referencia()
    assert len(ref) == 5600 and "carga_id" not in ref.columns  # retorno compatível: só as colunas de sempre
    assert primeira.saida["tabelas"]["geo.municipio"]["novo"] and not igual.saida["tabelas"]["geo.municipio"]["novo"]
    assert primeira.saida["arquivo"] == "data/lago/geo/municipio" and primeira.saida["registros_produzidos"] == 5600

    dados[0] = municipio(0, "Renomeado", "PA")
    arquivo.write_text(json.dumps(dados))
    mudou = municipios.carregar_referencia()[1]
    assert mudou.saida["tabelas"]["geo.municipio"]["novo"]
    vigente = lago.ler("geo.municipio").set_index("cod_municipio")
    assert vigente.at["0", "municipio"] == "Renomeado" and set(vigente["carga_id"]) == {mudou.carga_id}
    assert len(lago.ler("geo.municipio", vigente=False)) == 2 * 5600  # as duas cargas ficam guardadas
    assert not (tmp_path / "data" / "processed").exists()
