from pathlib import Path

import pandas as pd

from pipeline import cadastro, resultados
from pipeline.armazenamento import lago

from conftest import CPF_VALIDO

CAR = "MG-3148103-5527FB32FFB24B7F850B487724583043"
QUADRADO = "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))"


def ficha(situacao_embargo: str, gerado_em: str) -> dict:
    embargos = pd.DataFrame({"id_embargo": ["X-1"], "num_tad": ["X"], "classe": ["parcial"], "inter_ha": [10.0],
                             "fracao_objeto": [0.5], "geometria_wkt": ["POLYGON ((0.5 0.5, 0.5 2, 2 2, 2 0.5, 0.5 0.5))"],
                             "carga_id": ["ibama_embargos:20261101T030000"]})
    criterios = [{"chave": "car", "criterio": "CAR", "criterio_ab_s": 3, "situacao": "sem ocorrência",
                  "evidencia": "Ativo", "encaminhamento": "—", "fonte": "SICAR", "aviso": None},
                 {"chave": "embargo", "criterio": "Embargo IBAMA", "criterio_ab_s": 7, "situacao": situacao_embargo,
                  "evidencia": "1 embargo", "encaminhamento": "Consultar o IBAMA", "fonte": "IBAMA", "aviso": None}]
    return {"consulta": {"gerado_em": gerado_em},
            "imovel": {"cod_imovel": CAR, "uf": "MG", "cod_municipio": "3148103", "area_geom_ha": 89.1},
            "resultado": {"situacao": "com pendência", "resumo": "1 pendência",
                          "contagem": {"pendência": 1, "sem ocorrência": 1}},
            "criterios": criterios,
            "evidencias": {"embargos": embargos if situacao_embargo == "pendência" else embargos.iloc[0:0]},
            "geometria_car": QUADRADO}


def test_execucao_grava_resultado_criterio_e_evidencia_com_intersecao():
    execucao = resultados.Execucao("demonstracao")
    resultado_id = execucao.acrescentar(ficha("pendência", "2026-11-01 10:00:00"), ficha_arquivo="x.html")
    execucao.encerrar()
    res = lago.ler("diag.resultado_imovel")
    assert res["resultado_id"].tolist() == [resultado_id] and res["n_pendencias"].iloc[0] == 1
    assert sorted(lago.ler("diag.criterio")["chave"]) == ["car", "embargo"]
    ev = lago.ler("diag.evidencia").iloc[0]
    assert (ev["tabela"], ev["registro_id"], ev["chave_criterio"]) == ("ref.embargo_ibama", "X-1", "embargo")
    assert ev["carga_id"] == "ibama_embargos:20261101T030000"
    assert ev["geometria_wkt"].startswith("POLYGON") and "2" not in ev["geometria_wkt"]  # recortada pelo imóvel
    assert '"num_tad":"X"' in ev["detalhes_json"].replace(" ", "")
    assert len(lago.ler("diag.execucao_carga")) > 0


def test_mudancas_entre_as_duas_ultimas_execucoes():
    for situacao, quando in (("sem ocorrência", "2026-10-01 10:00:00"), ("pendência", "2026-11-01 10:00:00")):
        execucao = resultados.Execucao("demonstracao")
        execucao.acrescentar(ficha(situacao, quando))
        execucao.encerrar()
    mudou = resultados.mudancas()
    assert mudou[["chave", "situacao_anterior", "situacao_atual"]].values.tolist() == [
        ["embargo", "sem ocorrência", "pendência"]]
    assert mudou["gerado_em_atual"].iloc[0] == pd.Timestamp("2026-11-01 10:00:00")
    assert resultados.mudancas("outra-organizacao").empty


def test_importar_carteira_reaproveita_produtor_e_imovel_e_nao_grava_cpf(tmp_path):
    planilha = pd.DataFrame({"id_produtor": ["P1", "P2"], "cod_car": [CAR, None], "lat": [None, "-18,9"],
                             "lon": [None, "-46,9"], "documento": [CPF_VALIDO, None], "ccir": ["123", None],
                             "commodity": ["café", "soja"]})
    arquivo = tmp_path / "coop.csv"
    planilha.to_csv(arquivo, index=False)
    org = cadastro.organizacao("Cooperativa Teste")
    assert cadastro.organizacao("Cooperativa Teste") == org
    _, ids1 = cadastro.importar_carteira(planilha, org, arquivo)
    _, ids2 = cadastro.importar_carteira(planilha.iloc[[0]], org, arquivo)
    assert ids2[0] == ids1[0]  # mês seguinte: mesmo produtor e mesmo imóvel
    produtores = lago.ler("cad.produtor")
    assert len(produtores) == 2 and produtores["documento_hash"].notna().sum() == 1
    for tabela in ("cad.produtor", "cad.imovel", "cad.carteira_item", "cad.documento_trazido"):
        texto = lago.ler(tabela).to_csv()
        assert "11144477735" not in texto and "111.444.777-35" not in texto
    imoveis = lago.ler("cad.imovel").set_index("cod_car", drop=False)
    assert imoveis.loc[CAR, "commodity"] == "café"
    assert imoveis["lat"].dropna().tolist() == [-18.9]
    assert lago.ler("cad.documento_trazido")[["tipo", "valor"]].values.tolist() == [["ccir", "123"]] * 2
    assert len(lago.ler("cad.carteira")) == 2
