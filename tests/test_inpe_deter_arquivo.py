"""DETER da Amazônia e do Cerrado pelo arquivo do TerraBrasilis: leitura filtrada, reconciliação com ref.alerta_deter
(id_alerta e gid do lago), queda para o WFS e download só quando a versão muda. Sem rede: shapefile sintético, respostas
do WFS gravadas e funções injetadas."""

import datetime as dt
import gzip
import io
import json
import zipfile

import pandas as pd
import pytest
import shapefile
import shapely

from conftest import HOJE, ocorrencias
from pipeline import config, download
from pipeline.armazenamento import lago
from pipeline.fontes import inpe_deter
from pipeline.validacao import ErroDeValidacao, ResultadoFonte
from test_inpe_deter import PRJ_GDAL, feature, resposta

CAMPOS = [("FID", "C", 12, 0), ("CLASSNAME", "C", 40, 0), ("VIEW_DATE", "D", 8, 0), ("AREAMUNKM", "N", 32, 10),
          ("MUNICIPALI", "C", 100, 0), ("GEOCODIBGE", "C", 7, 0), ("UF", "C", 2, 0), ("SENSOR", "C", 10, 0),
          ("SATELLITE", "C", 13, 0)]


def linha(fid, data="2022-03-01", area=0.1, classe="DESMATAMENTO_CR", municipio="Pacajá", uf="PA", geocod="1505486",
          deslocamento=0.0):
    return dict(fid=fid, data=data, area=area, classe=classe, municipio=municipio, uf=uf, geocod=geocod,
                deslocamento=deslocamento)


def zip_deter(caminho, linhas, prj=PRJ_GDAL):
    """Shapefile no formato do arquivo da Amazônia/Cerrado (FID, CLASSNAME, AREAMUNKM, MUNICIPALI, GEOCODIBGE, UF).
    Cada alerta é um quadrado de 0,1° com o canto em x = -50,6 + deslocamento."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON, encoding="utf-8")
    for campo in CAMPOS:
        w.field(*campo)
    for r in linhas:
        x = -50.6 + r["deslocamento"]
        w.poly([list(shapely.box(x, -3.8, x + 0.1, -3.7).exterior.coords)[::-1]])
        w.record(r["fid"], r["classe"], dt.date.fromisoformat(r["data"]), r["area"], r["municipio"], r["geocod"],
                 r["uf"], "WFI", "AMAZONIA-1")
    w.close()
    with zipfile.ZipFile(caminho, "w") as z:
        for ext, buf in (("shp", shp), ("shx", shx), ("dbf", dbf)):
            z.writestr(f"deter-amz-deter-public.{ext}", buf.getvalue())
        z.writestr("deter-amz-deter-public.prj", prj)
    return caminho


def wfs_feature(gid, deslocamento=0.0, **kw):
    return feature(gid, geometria=quadrado_x(deslocamento), **kw)


def quadrado_x(deslocamento):
    x = round(-50.6 + deslocamento, 4)
    return {"type": "MultiPolygon", "coordinates": [[[[x, -3.8], [round(x + 0.1, 4), -3.8], [round(x + 0.1, 4), -3.7],
                                                     [x, -3.7], [x, -3.8]]]]}


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    """Ambiente de executar() sem rede. Devolve um objeto com o que o "servidor" responde: `arquivo` (linhas do
    shapefile), `wfs` (features do WFS), `versao` (nome no cabeçalho), `contagem_wfs`, e os contadores de chamadas."""
    for nome, valor in (("RAIZ", tmp_path), ("DADOS_BRUTOS", tmp_path / "raw"), ("DADOS_PROCESSADOS", tmp_path / "processed"),
                        ("TRABALHO", tmp_path / "trabalho"),
                        ("DETER_ARQUIVOS", {"amazonia": {**config.DETER_ARQUIVOS["amazonia"], "url": "http://x/shape"}}),
                        ("CAMADAS_DETER", {"amazonia": config.CAMADAS_DETER["amazonia"]})):
        monkeypatch.setattr(config, nome, valor)

    class Mundo:
        arquivo, wfs, versao, contagem_wfs = [], [], "deter-amz-public-2026nov04.zip", None
        downloads = wfs_baixados = 0
        arquivo_quebrado = False

    m = Mundo()

    def baixar_uma_vez(url, temporario):
        m.downloads += 1
        if m.arquivo_quebrado:
            raise download.DownloadIncompleto("recebidos 10 de 99 bytes")
        zip_deter(temporario, m.arquivo)
        return {"Content-Type": "application/zip", "Last-Modified": None, "Content-Length": None}

    def baixar_camada(nome, desde, hoje, atualizar):
        m.wfs_baixados += 1
        pasta = config.DADOS_BRUTOS / "inpe_deter" / nome / f"desde_{desde}"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "2022-03.json.gz").write_bytes(gzip.compress(json.dumps(resposta(m.wfs)).encode()))
        return {"total_anunciado": len(m.wfs), "particoes": [{"inicio": "2022-03-01", "arquivo": "2022-03.json.gz"}]}

    def contagem_wfs(nome, desde, ate):
        if m.contagem_wfs is None:
            raise ConnectionError("WFS fora do ar")
        return m.contagem_wfs

    monkeypatch.setattr(download, "_baixar_uma_vez", baixar_uma_vez)
    monkeypatch.setattr(download.time, "sleep", lambda s: None)
    monkeypatch.setattr(inpe_deter, "_versao_remota", lambda url: m.versao)
    monkeypatch.setattr(inpe_deter, "baixar_camada", baixar_camada)
    monkeypatch.setattr(inpe_deter, "contagem_wfs", contagem_wfs)
    return m


def semear_lago_pelo_wfs(mundo, ref):
    """Primeira carga: o arquivo está fora do ar, então o lote vem do WFS (gids do WFS no lago)."""
    mundo.arquivo_quebrado = True
    inpe_deter.executar(ref, HOJE)
    mundo.arquivo_quebrado = False


def wfs_padrao():
    return [wfs_feature("10_hist", data="2022-03-01", area=0.1),
            wfs_feature("11_hist", data="2022-03-02", area=0.2, deslocamento=0.2),
            wfs_feature("12_hist", data="2022-03-03", area=0.3, deslocamento=0.4),
            wfs_feature("13_hist", data="2022-03-03", area=0.3, deslocamento=0.6)]


def arquivo_padrao():
    return [linha("a1", "2022-03-01", 0.1),
            linha("a2", "2022-03-02", 0.2, deslocamento=0.2),
            linha("a3", "2022-03-03", 0.3, deslocamento=0.6000001),  # é o 13: a FID vem antes da do 12 de propósito
            linha("a4", "2022-03-03", 0.3, deslocamento=0.4000001),  # é o 12
            linha("a5", "2022-04-01", 0.5, deslocamento=0.8),  # novo
            linha("a6", "2022-03-05", 0.7, classe="CICATRIZ_DE_QUEIMADA"),  # classe ignorada na leitura
            linha("a7", "2020-05-05", 0.9)]  # anterior a DETER_DESDE_PADRAO


def ids_por_gid():
    v = lago.ler("ref.alerta_deter")
    return dict(zip(v["gid"], v["id_alerta"]))


def test_leitura_filtra_classe_e_data_antes_de_montar_a_geometria(tmp_path):
    z = zip_deter(tmp_path / "a.zip", arquivo_padrao())
    r = ResultadoFonte("inpe_deter", "teste")
    monkey = config.DETER_ARQUIVOS
    assert monkey["amazonia"]["so_desmatamento"]
    tabela = inpe_deter.tabela_arquivo(z, "amazonia", r, config.DETER_DESDE_PADRAO)
    assert sorted(tabela["gid"]) == ["arq-a1", "arq-a2", "arq-a3", "arq-a4", "arq-a5"]
    assert set(tabela["classe"]) == {"DESMATAMENTO_CR"} and set(tabela["uf"]) == {"PA"}
    assert (tabela["mun_geocod"] == "1505486").all() and tabela["publish_month"].isna().all()
    assert r.entrada["camadas"]["amazonia"] | {"arquivo": None} == {
        "arquivo": None, "no_arquivo": 7, "classes_ignoradas": 1, "antes_de_desde": 1, "recebidos": 5}
    assert ocorrencias(r, "DETER_AMAZONIA_CLASSE_TRADUZIDA") == 6  # as 6 de desmatamento, antes do filtro de data


def test_arquivo_projetado_interrompe(tmp_path):
    z = zip_deter(tmp_path / "a.zip", [linha("a1")],
                  prj='PROJCS["SIRGAS 2000 / UTM zone 21S",GEOGCS["SIRGAS 2000",AUTHORITY["EPSG","4674"]]]')
    with pytest.raises(ErroDeValidacao, match="DETER_AMAZONIA_CRS_INESPERADO"):
        inpe_deter.tabela_arquivo(z, "amazonia", ResultadoFonte("inpe_deter", "teste"), config.DETER_DESDE_PADRAO)


def test_casado_novo_e_ambiguo_mantem_id_e_gid_do_lago(mundo, ref_municipios):
    mundo.wfs = wfs_padrao()
    semear_lago_pelo_wfs(mundo, ref_municipios)
    antes = ids_por_gid()
    assert set(antes) == {"10_hist", "11_hist", "12_hist", "13_hist"}

    mundo.arquivo = arquivo_padrao()
    mundo.contagem_wfs = 4
    r = inpe_deter.executar(ref_municipios, HOJE)

    assert r.entrada["quedas_para_wfs"] == {} and mundo.wfs_baixados == 1  # só o da semeadura
    depois = ids_por_gid()
    assert {g: depois[g] for g in antes} == antes  # os quatro do lago mantêm gid e id_alerta
    assert [g for g in depois if g not in antes] == ["arq-a5"]
    assert depois["arq-a5"].startswith("amazonia:arq-a5:")
    vigente = lago.ler("ref.alerta_deter")
    assert len(vigente) == 5 and vigente["id_alerta"].is_unique
    assert set(vigente["classe"]) == {"DESMATAMENTO_CR"}
    mes = vigente.set_index("gid")["mes_publicacao"]
    assert mes["10_hist"] == pd.Timestamp("2022-03-01") and pd.isna(mes["arq-a5"])  # o mês do lago é mantido
    # o desempate pelo centroide ligou a3 ao 13 e a4 ao 12 (e não pela ordem das FIDs)
    x = vigente.set_index("gid")["geometria_wkt"].map(lambda w: round(shapely.from_wkt(w).centroid.x, 2))
    assert x["13_hist"] == -49.95 and x["12_hist"] == -50.15

    rec = r.entrada["reconciliacao"]["amazonia_arquivo"]
    assert rec == {"linhas": 5, "reconciliados": 4, "ambiguos": 2, "ambiguos_resolvidos": 2, "novos": 1, "so_no_lago": 0,
                   "no_lago_no_periodo": 4, "periodo_ate": "2022-04-01"}
    assert ocorrencias(r, "DETER_AMAZONIA_RECONCILIADO") == 4 and ocorrencias(r, "DETER_AMAZONIA_NOVO") == 1
    assert ocorrencias(r, "DETER_AMAZONIA_AMBIGUO") == 2 and ocorrencias(r, "DETER_AMAZONIA_AMBIGUO_SEM_PAR") == 0
    assert ocorrencias(r, "DETER_AMAZONIA_MUNICIPIO_DIFERENTE_NO_PAR") == 0
    assert ocorrencias(r, "DETER_AMAZONIA_ARQUIVO_X_LAGO") == 1  # 5 no arquivo, 4 no lago no período
    assert r.entrada["camadas"]["amazonia"]["diferenca_arquivo_menos_wfs"] == 1
    assert ocorrencias(r, "DETER_AMAZONIA_ARQUIVO_X_WFS") == 0  # 1 de diferença, dentro do limite de 50
    assert ocorrencias(r, "DETER_AMAZONIA_ARQUIVO_X_WFS_DIFERENCA") == 1


def test_segunda_execucao_com_o_mesmo_arquivo_nao_muda_nada(mundo, ref_municipios):
    mundo.wfs, mundo.arquivo, mundo.contagem_wfs = wfs_padrao(), arquivo_padrao(), 5
    semear_lago_pelo_wfs(mundo, ref_municipios)
    inpe_deter.executar(ref_municipios, HOJE)
    ids = ids_por_gid()
    r = inpe_deter.executar(ref_municipios, HOJE)
    resumo = r.saida["tabelas"]["ref.alerta_deter"]
    assert resumo["inseridos"] == 0 and resumo["alterados"] == 0
    assert ids_por_gid() == ids  # o id do alerta novo (arq-a5) é estável: ele casa com o lago na execução seguinte
    assert r.entrada["reconciliacao"]["amazonia_arquivo"]["novos"] == 0
    assert ocorrencias(r, "DETER_AMAZONIA_ARQUIVO_X_WFS_DIFERENCA") == 0


def test_chave_ambigua_sem_par_suficiente_vira_alerta_novo(mundo, ref_municipios):
    mundo.wfs = [wfs_feature("12_hist", data="2022-03-03", area=0.3, deslocamento=0.4)]
    semear_lago_pelo_wfs(mundo, ref_municipios)
    mundo.arquivo = [linha("a3", "2022-03-03", 0.3, deslocamento=0.6), linha("a4", "2022-03-03", 0.3, deslocamento=0.4)]
    mundo.contagem_wfs = 1
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert ids_por_gid()["12_hist"].startswith("amazonia:12_hist:")
    assert "arq-a3" in ids_por_gid() and "arq-a4" not in ids_por_gid()  # a4 está mais perto do 12; a3 fica sem par
    assert ocorrencias(r, "DETER_AMAZONIA_AMBIGUO") == 2 and ocorrencias(r, "DETER_AMAZONIA_AMBIGUO_SEM_PAR") == 1


def lago_de_dez():
    return [wfs_feature(f"{20 + i}_hist", data=f"2022-03-{i + 1:02d}", area=round(0.1 + i / 10, 1), deslocamento=i / 10)
            for i in range(10)]


def arquivo_de_dez(sem=()):
    return [linha(f"b{i}", f"2022-03-{i + 1:02d}", round(0.1 + i / 10, 1), deslocamento=i / 10)
            for i in range(10) if i not in sem]


def test_alerta_do_lago_que_sumiu_do_arquivo_fica_e_e_contado(mundo, ref_municipios):
    mundo.wfs = lago_de_dez()
    semear_lago_pelo_wfs(mundo, ref_municipios)
    mundo.arquivo = arquivo_de_dez(sem=(3,)) + [linha("n1", "2022-04-01", 0.55, deslocamento=0.9)]
    mundo.contagem_wfs = 10
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert r.entrada["quedas_para_wfs"] == {}
    assert len(lago.ler("ref.alerta_deter")) == 11  # 10 do WFS + 1 novo: nada some do lago
    assert ocorrencias(r, "DETER_AMAZONIA_SO_NO_LAGO") == 1


def test_municipio_diferente_no_par_e_registrado(mundo, ref_municipios):
    mundo.wfs = [wfs_feature("10_hist", data="2022-03-01", area=0.1)]
    semear_lago_pelo_wfs(mundo, ref_municipios)
    mundo.arquivo, mundo.contagem_wfs = [linha("a1", "2022-03-01", 0.1, municipio="Outro", geocod="1500000")], 1
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert ocorrencias(r, "DETER_AMAZONIA_RECONCILIADO") == 1
    assert ocorrencias(r, "DETER_AMAZONIA_MUNICIPIO_DIFERENTE_NO_PAR") == 1


def test_arquivo_falha_cai_para_o_wfs_com_o_motivo_e_nao_duplica(mundo, ref_municipios):
    mundo.wfs, mundo.arquivo, mundo.contagem_wfs = wfs_padrao(), arquivo_padrao(), 5
    mundo.wfs = wfs_padrao()
    semear_lago_pelo_wfs(mundo, ref_municipios)
    inpe_deter.executar(ref_municipios, HOJE)  # o lago agora tem o alerta nascido do arquivo (arq-a5)
    ids = ids_por_gid()
    mundo.arquivo_quebrado, mundo.versao = True, "deter-amz-public-2026nov05.zip"
    mundo.wfs = wfs_padrao() + [wfs_feature("14_hist", data="2022-04-01", area=0.5, deslocamento=0.8)]  # o a5, já com gid
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert "DownloadIncompleto" in r.entrada["quedas_para_wfs"]["amazonia"]
    assert ocorrencias(r, "DETER_AMAZONIA_ARQUIVO_FALHOU") == 1 and r.status == "ok"
    assert r.entrada["reconciliacao"]["amazonia_wfs"]["reconciliados"] == 1  # o 14 casa com o arq-a5
    assert ids_por_gid() == ids and len(lago.ler("ref.alerta_deter")) == 5  # sem duplicar


def test_arquivo_ilegivel_cai_para_o_wfs_e_grava_o_que_o_wfs_trouxe(mundo, ref_municipios, monkeypatch):
    mundo.wfs = wfs_padrao()
    monkeypatch.setattr(inpe_deter, "tabela_arquivo", lambda *a, **k: (_ for _ in ()).throw(KeyError("CLASSNAME")))
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert r.entrada["quedas_para_wfs"]["amazonia"] == "KeyError: 'CLASSNAME'"
    assert len(lago.ler("ref.alerta_deter")) == 4
    assert not any(v.codigo.startswith("DETER_AMAZONIA_ARQUIVO_X") for v in r.validacoes)  # nada do arquivo ficou registrado


def test_wfs_fora_do_ar_deixa_a_comparacao_nao_feita_sem_derrubar_a_fonte(mundo, ref_municipios):
    mundo.arquivo, mundo.contagem_wfs = arquivo_padrao(), None
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert r.status == "ok" and ocorrencias(r, "DETER_AMAZONIA_ARQUIVO_X_WFS_NAO_FEITA") == 1
    assert r.entrada["camadas"]["amazonia"]["wfs"].startswith("comparação não feita: ConnectionError")
    assert len(lago.ler("ref.alerta_deter")) == 5 and mundo.wfs_baixados == 0


def test_so_baixa_de_novo_quando_a_versao_muda(mundo, tmp_path):
    mundo.arquivo = [linha("a1")]
    primeiro = inpe_deter.baixar_arquivo("amazonia")
    assert mundo.downloads == 1 and primeiro["baixado_agora"] and primeiro["mudou"]
    igual = inpe_deter.baixar_arquivo("amazonia")
    assert mundo.downloads == 1 and not igual["baixado_agora"] and igual["sha256"] == primeiro["sha256"]
    mundo.versao = "deter-amz-public-2026nov05.zip"  # dia seguinte, mesmo conteúdo
    sem_mudanca = inpe_deter.baixar_arquivo("amazonia")
    assert mundo.downloads == 2 and sem_mudanca["baixado_agora"] and not sem_mudanca["mudou"]
    mundo.arquivo = [linha("a1"), linha("a2", "2022-03-02", 0.2)]
    mundo.versao = "deter-amz-public-2026nov06.zip"
    assert inpe_deter.baixar_arquivo("amazonia")["mudou"] and mundo.downloads == 3
    assert inpe_deter.baixar_arquivo("amazonia", atualizar=True)["baixado_agora"] and mundo.downloads == 4
    meta = json.loads((tmp_path / "raw/inpe_deter/amazonia/deter-amz-public.meta.json").read_text())
    assert meta["versao"] == "deter-amz-public-2026nov06.zip" and len(meta["sha256"]) == 64


def test_sem_versao_no_cabecalho_baixa(mundo):
    mundo.arquivo, mundo.versao = [linha("a1")], None
    inpe_deter.baixar_arquivo("amazonia")
    inpe_deter.baixar_arquivo("amazonia")
    assert mundo.downloads == 2


# --- freios: arquivo vazio depois do filtro, cobertura parcial, pareamento colapsado -------------------------------------

def test_arquivo_sem_desmatamento_depois_do_filtro_cai_para_o_wfs(mundo, ref_municipios):
    mundo.wfs = wfs_padrao()
    mundo.arquivo = [linha("q1", classe="CICATRIZ_DE_QUEIMADA"), linha("a7", "2020-05-05", 0.9)]  # classe ou data fora
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert "DETER_AMAZONIA_ARQUIVO_SEM_DESMATAMENTO" in r.entrada["quedas_para_wfs"]["amazonia"]
    assert len(lago.ler("ref.alerta_deter")) == 4 and set(lago.ler("ref.alerta_deter")["gid"]) >= {"10_hist"}  # veio do WFS


def test_classe_renomeada_no_arquivo_tambem_cai_para_o_wfs(mundo, ref_municipios):
    mundo.wfs = wfs_padrao()
    mundo.arquivo = [linha("a1", classe="DESMATAMENTO_RASO")]
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert "ARQUIVO_SEM_DESMATAMENTO" in r.entrada["quedas_para_wfs"]["amazonia"]


def test_cobertura_parcial_acima_do_limite_cai_para_o_wfs(mundo, ref_municipios):
    mundo.wfs, mundo.arquivo = wfs_padrao(), arquivo_padrao()
    mundo.contagem_wfs = 5 + 51  # diferença de 51 > max(2% de 56, 50)
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert "DETER_AMAZONIA_ARQUIVO_X_WFS" in r.entrada["quedas_para_wfs"]["amazonia"]
    assert set(lago.ler("ref.alerta_deter")["gid"]) == {"10_hist", "11_hist", "12_hist", "13_hist"}  # nada do arquivo


def test_divergencia_no_limite_ainda_segue_com_o_arquivo(mundo, ref_municipios):
    mundo.arquivo, mundo.contagem_wfs = arquivo_padrao(), 5 + 50
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert r.entrada["quedas_para_wfs"] == {} and ocorrencias(r, "DETER_AMAZONIA_ARQUIVO_X_WFS") == 0
    assert r.entrada["camadas"]["amazonia"]["limite_divergencia"] == 50


def test_limite_de_divergencia_cresce_com_a_contagem_do_wfs(mundo, ref_municipios, monkeypatch):
    mundo.wfs, mundo.arquivo, mundo.contagem_wfs = wfs_padrao(), arquivo_padrao(), 5 + 60
    monkeypatch.setattr(config, "DETER_DIVERGENCIA_WFS_PCT", 0.5)  # 50% de 65 = 33 < 50: vale o mínimo de 50
    assert inpe_deter.executar(ref_municipios, HOJE).entrada["quedas_para_wfs"] != {}
    monkeypatch.setattr(config, "DETER_DIVERGENCIA_WFS_MIN", 10)  # agora vale 50% de 65 = 33 e 60 > 33
    mundo.versao = "deter-amz-public-2026nov05.zip"
    assert inpe_deter.executar(ref_municipios, HOJE).entrada["quedas_para_wfs"] != {}
    mundo.contagem_wfs = 5 + 10  # limite = max(50% de 15, 10) = 10; diferença 10: dentro
    mundo.versao = "deter-amz-public-2026nov06.zip"
    assert inpe_deter.executar(ref_municipios, HOJE).entrada["quedas_para_wfs"] == {}


def test_wfs_inconclusivo_nao_diz_que_confere(mundo, ref_municipios):
    mundo.arquivo, mundo.contagem_wfs = arquivo_padrao(), None
    r = inpe_deter.executar(ref_municipios, HOJE)
    codigos = [v.codigo for v in r.validacoes]
    assert "DETER_AMAZONIA_ARQUIVO_X_WFS_NAO_FEITA" in codigos and "DETER_AMAZONIA_ARQUIVO_X_WFS" not in codigos
    assert "cobertura do arquivo não conferida" in next(v.descricao for v in r.validacoes if v.codigo.endswith("_NAO_FEITA"))


def test_pareamento_colapsado_nao_grava_o_arquivo_e_cai_para_o_wfs(mundo, ref_municipios):
    mundo.wfs = lago_de_dez()
    semear_lago_pelo_wfs(mundo, ref_municipios)
    antes = ids_por_gid()
    mundo.arquivo = [linha(f"c{i}", f"2022-03-{i + 1:02d}", round(0.1 + i / 10 + 0.001, 3), deslocamento=i / 10)
                     for i in range(10)]  # a área mudou na 3ª casa: nenhum alerta acha par
    mundo.contagem_wfs = 10
    mundo.versao = "deter-amz-public-2026nov05.zip"
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert "DETER_AMAZONIA_PAREAMENTO_COLAPSADO" in r.entrada["quedas_para_wfs"]["amazonia"]
    assert "0.0%" in r.entrada["quedas_para_wfs"]["amazonia"] or "0,0%" in r.entrada["quedas_para_wfs"]["amazonia"]
    assert ids_por_gid() == antes and not any(g.startswith("arq-") for g in ids_por_gid())  # nenhuma duplicata


def test_pareamento_no_piso_passa_e_abaixo_do_piso_cai(mundo, ref_municipios):
    mundo.wfs = lago_de_dez()
    semear_lago_pelo_wfs(mundo, ref_municipios)
    mundo.contagem_wfs = 10
    mundo.arquivo = arquivo_de_dez(sem=(3,))  # 9 de 10 = 90%: no piso, passa
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert r.entrada["quedas_para_wfs"] == {} and r.entrada["camadas"]["amazonia"]["fracao_do_lago_com_par"] == 0.9
    mundo.arquivo = arquivo_de_dez(sem=(3, 4))  # 8 de 10 = 80%: abaixo do piso
    mundo.versao = "deter-amz-public-2026nov05.zip"
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert "PAREAMENTO_COLAPSADO" in r.entrada["quedas_para_wfs"]["amazonia"]


def test_lago_sem_alerta_do_bioma_nao_aciona_o_freio_de_pareamento(mundo, ref_municipios):
    mundo.arquivo, mundo.contagem_wfs = arquivo_padrao(), 5
    r = inpe_deter.executar(ref_municipios, HOJE)  # primeira carga: o lago está vazio
    assert r.entrada["quedas_para_wfs"] == {} and "fracao_do_lago_com_par" not in r.entrada["camadas"]["amazonia"]
    assert len(lago.ler("ref.alerta_deter")) == 5


def test_dbf_com_area_de_menos_casas_que_a_tolerancia_cai_para_o_wfs(mundo, ref_municipios, monkeypatch):
    mundo.wfs, mundo.arquivo = wfs_padrao(), arquivo_padrao()
    monkeypatch.setattr(config, "DETER_AREA_CASAS", 11)  # o DBF sintético declara 10 casas
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert "DETER_AMAZONIA_AREA_PRECISAO" in r.entrada["quedas_para_wfs"]["amazonia"]


# --- ida e volta arquivo -> WFS -> arquivo -------------------------------------------------------------------------------

def test_ida_e_volta_arquivo_wfs_arquivo_nao_cria_id_novo_nem_cresce_o_lago(mundo, ref_municipios):
    mundo.wfs, mundo.arquivo, mundo.contagem_wfs = wfs_padrao(), arquivo_padrao(), 5
    semear_lago_pelo_wfs(mundo, ref_municipios)
    inpe_deter.executar(ref_municipios, HOJE)  # arquivo: o a5 nasce com gid arq-a5
    ids, n = ids_por_gid(), len(lago.ler("ref.alerta_deter"))
    assert n == 5

    mundo.arquivo_quebrado, mundo.versao = True, "deter-amz-public-2026nov05.zip"  # queda para o WFS
    mundo.wfs = wfs_padrao() + [wfs_feature("14_hist", data="2022-04-01", area=0.5, deslocamento=0.8)]
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert r.entrada["quedas_para_wfs"] and ids_por_gid() == ids and len(lago.ler("ref.alerta_deter")) == n

    mundo.arquivo_quebrado, mundo.versao = False, "deter-amz-public-2026nov06.zip"  # volta ao arquivo
    r = inpe_deter.executar(ref_municipios, HOJE)
    assert r.entrada["quedas_para_wfs"] == {} and r.entrada["reconciliacao"]["amazonia_arquivo"]["novos"] == 0
    assert ids_por_gid() == ids and len(lago.ler("ref.alerta_deter")) == n
    # estável: repetir o arquivo não altera mais nada
    mundo.versao = "deter-amz-public-2026nov07.zip"
    resumo = inpe_deter.executar(ref_municipios, HOJE).saida["tabelas"]["ref.alerta_deter"]
    assert resumo["inseridos"] == 0 and resumo["alterados"] == 0


# --- .meta.json e zip ------------------------------------------------------------------------------------------------------

def test_meta_corrompido_vale_como_sem_versao_e_baixa_de_novo(mundo, tmp_path):
    mundo.arquivo = [linha("a1")]
    inpe_deter.baixar_arquivo("amazonia")
    meta = tmp_path / "raw/inpe_deter/amazonia/deter-amz-public.meta.json"
    meta.write_text('{"url": "http://x", "versao": "deter-amz-pub')  # gravação interrompida
    refeito = inpe_deter.baixar_arquivo("amazonia")
    assert mundo.downloads == 2 and refeito["baixado_agora"]
    assert json.loads(meta.read_text())["versao"] == "deter-amz-public-2026nov04.zip"


def test_meta_corrompido_no_pantanal_nao_derruba_a_leitura(mundo, tmp_path, monkeypatch):
    monkeypatch.setitem(config.DETER_ARQUIVOS, "pantanal", {**config.DETER_ARQUIVOS["amazonia"], "arquivo": "p.zip"})
    mundo.arquivo = [linha("a1")]
    pasta = tmp_path / "raw/inpe_deter/pantanal"
    pasta.mkdir(parents=True)
    (pasta / "p.zip").write_bytes(b"x")
    (pasta / "p.meta.json").write_text("{nao e json")
    assert inpe_deter.baixar_arquivo("pantanal")["baixado_agora"]
    assert download.ler_json(pasta / "p.meta.json")["versao"]


def test_meta_e_gravado_por_troca_atomica(tmp_path, monkeypatch):
    destino = tmp_path / "m.meta.json"
    destino.write_text('{"antigo": 1}')
    chamadas = []
    real = download.os.replace
    monkeypatch.setattr(download.os, "replace", lambda a, b: (chamadas.append((a.name, b.name)), real(a, b))[1])
    download.gravar_json(destino, {"novo": 2})
    assert chamadas == [("m.meta.json.tmp", "m.meta.json")] and json.loads(destino.read_text()) == {"novo": 2}
    assert not (tmp_path / "m.meta.json.tmp").exists()


def test_versao_so_e_gravada_depois_de_o_zip_validar(mundo, tmp_path, monkeypatch):
    def baixar_zip_ruim(url, temporario):
        temporario.write_bytes(b"isto nao e um zip")
        return {"Content-Type": "application/zip", "Last-Modified": None, "Content-Length": None}

    monkeypatch.setattr(download, "_baixar_uma_vez", baixar_zip_ruim)
    with pytest.raises(zipfile.BadZipFile):
        inpe_deter.baixar_arquivo("amazonia")
    assert "versao" not in download.ler_json(tmp_path / "raw/inpe_deter/amazonia/deter-amz-public.meta.json")
    # zip válido, mas sem o shapefile: também não grava a versão
    def baixar_zip_vazio(url, temporario):
        with zipfile.ZipFile(temporario, "w") as z:
            z.writestr("leia-me.txt", "nada")
        return {"Content-Type": "application/zip", "Last-Modified": None, "Content-Length": None}

    monkeypatch.setattr(download, "_baixar_uma_vez", baixar_zip_vazio)
    with pytest.raises(ValueError, match="falta o arquivo .shp"):
        inpe_deter.baixar_arquivo("amazonia")
    assert "versao" not in download.ler_json(tmp_path / "raw/inpe_deter/amazonia/deter-amz-public.meta.json")
