"""PRODES no lago (ref.desmatamento_prodes): partição por UF substituída só quando muda, estado operacional na pasta da
tabela, peças em config.TRABALHO e descartes em meta.descarte. Sem rede (fixtures de test_prodes_arquivo)."""

import json

import pandas as pd

from conftest import ocorrencias
from pipeline import config, download
from pipeline.armazenamento import lago
from pipeline.fontes import inpe_prodes
from test_prodes_arquivo import tb  # noqa: F401 (fixture)
from test_prodes_lote import HOJE, servico  # noqa: F401 (fixture)

TABELA = "ref.desmatamento_prodes"


def sha(uf):
    return inpe_prodes.ler_publicacao()["particoes"][uf]["sha256"]


def test_particoes_ficam_no_lago_e_ler_uf_e_o_estado_vigente(tb, tmp_path):  # noqa: F811
    r = inpe_prodes.executar_arquivos(HOJE)
    assert r.saida["arquivo"] == "lago/ref/desmatamento_prodes"
    for uf in ("MG", "SP"):
        pelo_lago = lago.ler(TABELA, particao=uf)
        assert inpe_prodes.arquivo_uf(uf) == config.LAGO / "ref" / "desmatamento_prodes" / f"uf={uf}" / "part.parquet"
        pd.testing.assert_frame_equal(inpe_prodes.ler_uf(uf), pelo_lago)
        assert set(pelo_lago["uf"]) == {uf} and "carga_id" in pelo_lago
    # Chave [uuid, uf]: o polígono de divisa está nas duas UFs, uma linha em cada, com a `uf` da partição.
    mg, sp = (inpe_prodes.ler_uf(u).set_index("uuid").loc["ce-4"] for u in ("MG", "SP"))
    assert mg["uf"] == "MG" and sp["uf"] == "SP" and mg["uf_fonte"] == sp["uf_fonte"] == "SP"
    assert "UF_DIFERE_DO_CONTORNO" in mg["alertas"] and "UF_DIFERE_DO_CONTORNO" in sp["alertas"]
    assert lago.ler(TABELA)["uuid"].duplicated().sum() == 1  # só o ce-4, que tem as duas UFs
    assert r.saida["tabelas"][TABELA]["inseridos"] == 7 and sorted(r.saida["tabelas"][TABELA]["particoes_gravadas"]) == ["MG", "SP"]


def test_estado_operacional_na_pasta_da_tabela_e_nada_em_processed(tb, tmp_path):  # noqa: F811
    inpe_prodes.executar_arquivos(HOJE)
    pasta = config.LAGO / "ref" / "desmatamento_prodes"
    assert inpe_prodes.arquivo_publicacao() == pasta / "_publicacao.json" and (pasta / "_publicacao.json").exists()
    assert (pasta / "_manifesto_arquivos.json").exists()
    assert json.loads((pasta / "_publicacao.json").read_text())["particoes"]["MG"]["arquivo"].endswith("uf=MG/part.parquet")
    assert not (tmp_path / "processed").exists()  # nem partição, nem publicação, nem descartados, nem peças
    assert not inpe_prodes.pasta_pecas().exists() and inpe_prodes.pasta_pecas() == config.TRABALHO / "inpe_prodes_pecas"
    # Os arquivos "_" não atrapalham a leitura das partições.
    assert sorted(lago.ler(TABELA)["uf"].unique()) == ["MG", "SP"]


def test_repetir_nao_regrava_a_particao_e_o_sha256_so_muda_quando_ela_muda(tb):  # noqa: F811
    inpe_prodes.executar_arquivos(HOJE)
    antes = {uf: sha(uf) for uf in ("MG", "SP")}
    # Mesma versão do arquivo, verificada de novo: nada a regravar.
    r = inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=29), verificar=True)
    assert r.saida["particoes_regravadas"] == {} and sha("MG") == antes["MG"] and sha("SP") == antes["SP"]
    # Versão nova do Cerrado, com o mesmo conteúdo: as peças são refeitas, mas a partição não muda.
    tb.versao["cerrado"] = "20271015"
    r = inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=45))
    assert r.entrada["biomas_refeitos"] == ["cerrado"] and r.saida["particoes_regravadas"] == {}
    assert sha("MG") == antes["MG"] and sha("SP") == antes["SP"]
    assert r.saida["tabelas"][TABELA]["inseridos"] == 0 and r.saida["tabelas"][TABELA]["alterados"] == 0
    # Polígono novo em MG: só a partição de MG é regravada, e o sha256 dela muda.
    tb.versao["cerrado"] = "20281015"
    tb.poligonos["cerrado"].append(("ce-6", 2025, -47.2, "MINAS GERAIS"))
    r = inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=90))
    assert list(r.saida["particoes_regravadas"]) == ["MG"] and r.saida["tabelas"][TABELA]["inseridos"] == 1
    assert sha("MG") != antes["MG"] and sha("SP") == antes["SP"]


def test_poligono_que_sumiu_do_arquivo_sai_da_particao(tb):  # noqa: F811
    inpe_prodes.executar_arquivos(HOJE)
    tb.versao["cerrado"] = "20271015"
    tb.poligonos["cerrado"] = [p for p in tb.poligonos["cerrado"] if p[0] != "ce-1"]
    r = inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=45))
    assert "ce-1" not in set(inpe_prodes.ler_uf("MG")["uuid"]) and r.saida["tabelas"][TABELA]["removidos"] == 1


def test_descartes_vao_para_meta_descarte(tb):  # noqa: F811
    inpe_prodes.executar_arquivos(HOJE)
    descarte = lago.ler("meta.descarte")
    assert descarte[["fonte", "registro_id", "motivo"]].values.tolist() == [
        ["inpe_prodes", "ce-5", "PRODES_CLASSE_FORA_DO_DOMINIO"]]
    assert json.loads(descarte["dados_json"].iloc[0])["main_class"] == "RESERVATORIO"


def test_wfs_grava_no_lago_e_repetir_nao_regrava(servico):  # noqa: F811
    r = inpe_prodes.executar(HOJE)
    assert r.saida["tabelas"][TABELA]["inseridos"] == 6 and list(r.saida["particoes_regravadas"]) == ["MG"]
    antes = sha("MG")
    assert inpe_prodes.arquivo_publicacao().exists() and inpe_prodes._arquivo_manifesto_wfs().exists()
    r = inpe_prodes.executar(HOJE, verificar=True)
    assert r.saida["particoes_regravadas"] == {} and sha("MG") == antes
    # Revisão do INPE (mesma contagem, uuid novo em um polígono): a partição muda e o sha256 também.
    servico.versao[("cerrado", 2025)] = "-rev"
    r = inpe_prodes.executar(HOJE, verificar=True)
    assert list(r.saida["particoes_regravadas"]) == ["MG"] and sha("MG") != antes
    assert len(inpe_prodes.ler_uf("MG")) == 6  # o substituir_particao tira os uuid antigos


def test_wfs_preenche_as_colunas_do_contrato(servico):  # noqa: F811
    inpe_prodes.executar(HOJE)
    mg = lago.ler(TABELA, particao="MG")
    assert {"uf_fonte", "data_publicacao"} <= set(mg.columns) and mg["data_publicacao"].isna().all()
    assert set(mg["uf_fonte"]) == {"MG"}


def test_uf_sem_poligono_no_wfs_fica_na_publicacao_com_particao_vazia(servico):  # noqa: F811
    servico.poligonos[("cerrado", 2025)] = [p for p in servico.poligonos[("cerrado", 2025)] if p[1] != "SAO PAULO"]
    inpe_prodes.executar(HOJE)
    pub = inpe_prodes.garantir_uf("SP", HOJE)
    assert "SP" in pub["particoes"] and inpe_prodes.ler_uf("SP").empty
    assert list(inpe_prodes.ler_uf("SP").columns[:3]) == ["uuid", "bioma", "ano_prodes"]


def test_enquanto_o_lago_nao_tem_o_prodes_vale_o_legado(tb, tmp_path, monkeypatch):  # noqa: F811
    inpe_prodes.executar_arquivos(HOJE)
    pub = json.loads(inpe_prodes.arquivo_publicacao().read_text())
    # Lago novo e vazio; o que estava em data/processed continua legível.
    processed = tmp_path / "processed"
    (processed / "inpe_prodes" / "uf=MG").mkdir(parents=True)
    inpe_prodes.ler_uf("MG").drop(columns="carga_id").to_parquet(processed / "inpe_prodes" / "uf=MG" / "part.parquet")
    (processed / "inpe_prodes_publicacao.json").write_text(json.dumps(pub))
    monkeypatch.setattr(config, "LAGO", tmp_path / "lago_novo")
    assert inpe_prodes.ler_publicacao()["particoes"]["MG"]["sha256"] == pub["particoes"]["MG"]["sha256"]
    assert len(inpe_prodes.ler_uf("MG")) == 4


def test_primeira_gravacao_no_lago_a_partir_do_bruto_local_nao_baixa_nada(tb, tmp_path, monkeypatch):  # noqa: F811
    inpe_prodes.executar_arquivos(HOJE)
    # Lago novo, bruto já baixado e manifesto do lugar antigo (raw/arquivo_bioma): a verificação ainda vale e o lote
    # sai do arquivo local, sem consultar o catálogo.
    (config.LAGO / "ref" / "desmatamento_prodes" / "_manifesto_arquivos.json").rename(
        inpe_prodes.PASTA_ARQUIVOS / "manifesto.json")
    monkeypatch.setattr(config, "LAGO", tmp_path / "lago_novo")
    tb.catalogos, tb.baixados = 0, []
    r = inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=1))
    assert tb.catalogos == 0 and r.entrada["verificacao"].startswith("reaproveitada")
    assert sorted(inpe_prodes.ler_uf("MG")["uuid"]) == ["ce-0", "ce-1", "ce-4", "ma-0"]
    assert download.sha256(inpe_prodes.arquivo_uf("MG")) == sha("MG")
    assert ocorrencias(r, "PRODES_UUID_EM_DOIS_BIOMAS") == 0
