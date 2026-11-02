"""Carteira: leitura da planilha, linhas com problema e ordem de prioridade (sem rede: a consulta é falsa)."""

import pandas as pd

from pipeline import carteira, prediagnostico
from test_prediagnostico import alertas, car, embargos, lista_suja, prodes


def ficha_falsa():
    ficha = prediagnostico.diagnosticar(car(), embargos(), alertas(), lista_suja(), prodes(), ultimo_ano_prodes=2025)
    return {"consulta": {"gerado_em": "2026-11-02 10:00:00", "prodes": {}, "documento_informado": False}, **ficha,
            "procedencia": []}


def test_planilha_com_virgula_decimal_e_colunas_em_maiusculas(tmp_path):
    arq = tmp_path / "c.csv"
    arq.write_text("ID_PRODUTOR;LAT;LON\nA; -17,70 ;-51,10\n", encoding="utf-8")
    df = carteira.ler_planilha(arq)
    assert list(df.columns) == ["id_produtor", "lat", "lon"] and df.at[0, "lat"].strip() == "-17,70"
    assert carteira.problema(df.iloc[0]) is None


def test_linhas_com_problema_nao_vao_a_rede_e_ficam_inconclusivas(tmp_path):
    df = pd.DataFrame([{"id_produtor": None, "cod_car": "MG-1"},
                       {"id_produtor": "B", "cod_car": None, "lat": None, "lon": None},
                       {"id_produtor": "C", "cod_car": None, "lat": "-51.1", "lon": "-17.7"},
                       {"id_produtor": "D", "cod_car": "MG-1", "documento": "111.444.777-00"}])
    chamadas = []
    saida = carteira.processar(df, tmp_path, consultar=lambda *a, **k: chamadas.append(a))
    assert chamadas == [] and set(saida["resultado"]) == {"inconclusivo"}
    assert saida["problema_na_linha"].tolist() == ["sem id_produtor", "sem cod_car e sem lat/lon",
                                                   "lat/lon fora do Brasil (conferir se não estão trocados)",
                                                   "documento com dígito verificador inválido"]


def test_pendencia_vem_antes_e_o_documento_nao_sai_na_carteira(tmp_path, monkeypatch):
    limpo = ficha_falsa()
    com_pendencia = ficha_falsa()
    com_pendencia["resultado"] = {**com_pendencia["resultado"], "situacao": "com pendência"}
    com_pendencia["criterios"] = [{**c, "situacao": "pendência"} if c["chave"] == "embargo" else c
                                  for c in com_pendencia["criterios"]]
    respostas = {"MG-LIMPO": limpo, "MG-PEND": com_pendencia}
    df = pd.DataFrame([{"id_produtor": "A", "cod_car": "MG-LIMPO", "documento": "111.444.777-35", "commodity": "café"},
                       {"id_produtor": "B", "cod_car": "MG-PEND", "ccir": "123"}])
    saida = carteira.processar(df, tmp_path, consultar=lambda cod, *a, **k: respostas[cod])
    assert saida["id_produtor"].tolist() == ["B", "A"] and saida["prioridade"].tolist() == [1, 2]
    assert saida.at[0, "pendencias"] == "Embargo IBAMA" and saida.at[0, "ccir"] == "123"
    assert "documento" not in saida and saida.at[1, "documento_informado"] == "sim"
    assert saida.at[1, "commodity"] == "café"
    texto = carteira.html(saida, "c.csv")
    assert "111.444.777-35" not in texto and "Quem atender primeiro" in texto
