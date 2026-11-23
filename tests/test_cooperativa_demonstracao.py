"""Carteira de demonstração da cooperativa: planilha, talhões e o caso sem cache (offline: nenhuma consulta é real)."""

import importlib.util
import re
from pathlib import Path

import pandas as pd
import pytest

from pipeline import carteira, config, vetor

RAIZ = Path(__file__).resolve().parents[1]
PLANILHA = RAIZ / "docs" / "modelos" / "cooperativa_demonstracao.csv"
SCRIPT = RAIZ / "docs" / "evidencias" / "entrega-final" / "01_cooperativa_demonstracao.py"
DOCUMENTO = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|(?<!\d)\d{11}(?!\d)|(?<!\d)\d{14}(?!\d)")


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("cooperativa_demonstracao", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_planilha_tem_12_imoveis_7_de_cafe_e_5_de_gado():
    df = carteira.ler_planilha(PLANILHA)
    assert len(df) == 12 and df["id_produtor"].is_unique
    assert df["commodity"].str.contains("café").sum() == 7 and df["commodity"].str.contains("gado").sum() == 5
    assert df["nome_area"].str.contains("demonstração").all()
    assert df["documento"].isna().all()  # o documento de demonstração entra em memória, pelo script


def test_so_a_linha_da_coordenada_trocada_tem_problema():
    df = carteira.ler_planilha(PLANILHA)
    problemas = {df.at[i, "id_produtor"]: carteira.problema(linha) for i, linha in df.iterrows()}
    assert {k: v for k, v in problemas.items() if v} == {"CVC-07": "lat/lon fora do Brasil (conferir se não estão trocados)"}


def test_nenhum_cpf_ou_cnpj_na_planilha_nos_talhoes_nem_no_script():
    arquivos = [PLANILHA, SCRIPT, *(PLANILHA.parent / "talhoes").glob("*.kml"), SCRIPT.parent / "LEIA-ME.md"]
    assert len(arquivos) >= 4
    for arquivo in arquivos:
        assert not DOCUMENTO.search(arquivo.read_text(encoding="utf-8")), arquivo.name


def test_talhoes_sao_poligonos_legiveis_pela_carteira():
    df = carteira.ler_planilha(PLANILHA)
    areas = carteira.areas_de_producao(df, PLANILHA.parent)
    assert len(areas) >= 2
    assert all(a["geometria"] is not None and a["motivo"] is None for a in areas.values())
    assert all(vetor.tornar_valida(a["geometria"]).area > 0 for a in areas.values())


def test_sem_cache_do_sicar_o_caso_vira_inconclusivo_com_motivo_e_nao_vai_a_rede(script, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DADOS_BRUTOS", tmp_path / "raw")
    sem_cache = []
    df = pd.DataFrame([{"id_produtor": "CVC-X", "cod_car": "MG-3148103-6245AC9B371A4422B2FA8011CFCC5566"}])
    saida = carteira.processar(df, tmp_path / "saida", baixar_prodes=False,
                               consultar=script.consultar_do_cache(False, sem_cache))
    assert saida.at[0, "resultado"] == "inconclusivo"
    assert "sem cache" in saida.at[0, "problema_na_linha"] and "offline" in saida.at[0, "problema_na_linha"]
    assert sem_cache == ["MG-3148103-6245AC9B371A4422B2FA8011CFCC5566"]
