"""Carteira: leitura da planilha, linhas com problema e ordem de prioridade (sem rede: a consulta é falsa)."""

import pandas as pd

from pipeline import cadastro, carteira, prediagnostico, resultados

from conftest import CPF_VALIDO
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


def ficha_de(cod: str, quando: str, embargo: str = "sem ocorrência", deter: bool = False) -> dict:
    """Ficha sintética de um imóvel: situação do embargo e, opcionalmente, um critério novo (alerta DETER)."""
    ficha = ficha_falsa()
    ficha["consulta"] = {**ficha["consulta"], "gerado_em": quando}
    ficha["imovel"] = {**ficha["imovel"], "cod_imovel": cod}
    ficha["criterios"] = [{**c, "situacao": embargo} if c["chave"] == "embargo" else c for c in ficha["criterios"]]
    if embargo == "pendência":
        ficha["resultado"] = {**ficha["resultado"], "situacao": "com pendência"}
    if deter:
        ficha["criterios"].append({"chave": "deter", "criterio": "Alerta DETER", "criterio_ab_s": None,
                                   "situacao": "indício", "evidencia": "1 alerta", "encaminhamento": "Conferir",
                                   "fonte": "INPE", "aviso": None})
    return ficha


def rodar(df, org, respostas, pasta):
    execucao = resultados.Execucao("carteira", org)
    saida = carteira.processar(df, pasta, consultar=lambda cod, *a, **k: respostas[cod], execucao=execucao)
    execucao.encerrar()
    return carteira.comparar(saida, org, execucao.id)


def test_carteira_mostra_o_que_mudou_desde_a_execucao_anterior_da_mesma_organizacao(tmp_path):
    org, outra = cadastro.organizacao("Coop A"), cadastro.organizacao("Coop B")
    df = pd.DataFrame([{"id_produtor": "P1", "cod_car": "MG-1", "documento": CPF_VALIDO},
                       {"id_produtor": "P2", "cod_car": "MG-2"},
                       {"id_produtor": "P3", "cod_car": "MG-3"}])
    mes1 = {c: ficha_de(c, "2026-10-02 10:00:00") for c in ("MG-1", "MG-2", "MG-3")}
    saida, comp = rodar(df, org, mes1, tmp_path / "m1")
    assert comp["primeira"] and saida["mudou"].isna().all()
    assert "primeira execução, sem comparação" in carteira.html(saida, "c.csv", comp).lower()
    # Outra organização roda entre os dois meses com o mesmo CAR em pendência: não pode entrar na comparação de A.
    rodar(df.iloc[[2]], outra, {"MG-3": ficha_de("MG-3", "2026-10-20 10:00:00", "pendência")}, tmp_path / "b")
    # Mês 2: MG-1 ganha embargo, MG-2 ganha um critério novo, MG-3 fica igual; MG-9 é novo e P5 não tem CAR.
    df2 = pd.concat([df, pd.DataFrame([{"id_produtor": "P4", "cod_car": "MG-9"},
                                       {"id_produtor": "P5", "cod_car": None, "lat": None, "lon": None}])],
                    ignore_index=True)
    mes2 = {"MG-1": ficha_de("MG-1", "2026-11-02 10:00:00", "pendência"),
            "MG-2": ficha_de("MG-2", "2026-11-02 10:00:00", deter=True),
            "MG-3": ficha_de("MG-3", "2026-11-02 10:00:00"), "MG-9": ficha_de("MG-9", "2026-11-02 10:00:00")}
    saida, comp = rodar(df2, org, mes2, tmp_path / "m2")
    assert saida["id_produtor"].iloc[0] == "P1"  # a ordem de prioridade continua a mesma
    linha = saida.set_index("id_produtor")
    assert linha.at["P1", "mudou"] == "sim"
    assert linha.at["P1", "o_que_mudou"] == "Embargo IBAMA: sem ocorrência → pendência"
    assert linha.at["P2", "mudou"] == "sim" and "Alerta DETER: (não avaliado) → indício" in linha.at["P2", "o_que_mudou"]
    assert linha.at["P3", "mudou"] == "não"  # a pendência da Coop B não vaza
    assert pd.isna(linha.at["P4", "mudou"]) and linha.at["P4", "o_que_mudou"].startswith("sem comparação")
    assert pd.isna(linha.at["P5", "mudou"]) and linha.at["P5", "o_que_mudou"] == "sem comparação"
    assert not comp["primeira"] and comp["mudaram"] == 2 and comp["desde"] == pd.Timestamp("2026-10-02 10:00:00")
    texto = carteira.html(saida, "c.csv", comp)
    assert "2 imóveis mudaram desde 02/10/2026" in texto and texto.count('<tr class="mudou">') == 2
    csv = saida.to_csv(index=False)
    assert {"mudou", "o_que_mudou"} <= set(saida.columns)
    for t in (csv, texto):
        assert CPF_VALIDO not in t and "111.444.777-35" not in t
    assert resultados.mudancas(outra, {"MG-3"}).empty  # Coop B tem uma execução só
