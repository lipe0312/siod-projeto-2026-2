"""PRODES em lote pelo arquivo do bioma (ADR 0015): catálogo do TerraBrasilis, leitura do shapefile, peças por UF,
verificação mensal pela versão do arquivo e equivalência com o lote pelo WFS. Sem rede: shapefiles fictícios e os
contornos de UF e bioma de test_prodes_lote."""

import datetime as dt
import io
import zipfile

import pandas as pd
import pytest
import shapefile
import shapely

from conftest import ocorrencias
from pipeline import config, download, ficha_html, prediagnostico
from pipeline.fontes import inpe_prodes
from pipeline.validacao import ErroDeValidacao, ResultadoFonte
from test_prodes_lote import HOJE, Y, servico  # noqa: F401 (fixture)

PRJ_SIRGAS = 'GEOGCS["GCS_SIRGAS_2000",DATUM["D_SIRGAS_2000",SPHEROID["GRS_1980",6378137.0,298.257222101]]]'
CAMPOS = [("fid", "N", 9, 0), ("state", "C", 18, 0), ("main_class", "C", 254, 0), ("class_name", "C", 80, 0),
          ("image_date", "D", 8, 0), ("year", "N", 9, 0), ("area_km", "N", 24, 15), ("satellite", "C", 80, 0),
          ("sensor", "C", 80, 0), ("uuid", "C", 80, 0)]


def escrever_zip(caminho, poligonos, prj=PRJ_SIRGAS, codificacao="utf-8"):
    """poligonos: (uuid, ano, x, state[, classe]); quadrado de 0,05° em y = Y, imagem de 20/07 do ano."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON, encoding=codificacao)
    for campo in CAMPOS:
        w.field(*campo)
    for i, (uuid, ano, x, uf, *classe) in enumerate(poligonos):
        caixa = shapely.box(x, Y, x + 0.05, Y + 0.05)
        w.poly([list(caixa.exterior.coords)[::-1]])
        w.record(i + 1, uf, classe[0] if classe else "DESMATAMENTO", f"d{ano}", dt.date(ano, 7, 20), ano,
                 inpe_prodes.area_km2(caixa), "Sentinel-2", "MSI", uuid)
    w.close()
    base = caminho.name.removesuffix(".zip")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho, "w") as z:
        for ext, buf in (("shp", shp), ("shx", shx), ("dbf", dbf)):
            z.writestr(f"{base}.{ext}", buf.getvalue())
        z.writestr(f"{base}.prj", prj)
    return caminho


class TerraBrasilisFalso:
    """Catálogo e arquivos por bioma. `poligonos[bioma]` e `versao[bioma]` definem o que o catálogo anuncia."""

    def __init__(self, pasta):
        self.pasta = pasta
        # MG a oeste de -45, SP a leste (test_prodes_lote). 2023 fica fora do recorte (PRODES_DESDE = 2024).
        self.poligonos = {"cerrado": [("ce-0", 2024, -47.0, "MINAS GERAIS"), ("ce-1", 2025, -46.5, "MINAS GERAIS"),
                                      ("ce-2", 2025, -43.0, "SAO PAULO"), ("ce-3", 2023, -47.5, "MINAS GERAIS"),
                                      ("ce-4", 2025, -45.03, "SAO PAULO"),  # divisa: 0,03° em MG e 0,02° em SP
                                      ("ce-5", 2024, -46.0, "MINAS GERAIS", "RESERVATORIO")],
                          "mata_atlantica": [("ma-0", 2024, -46.8, "MG"), ("ma-1", 2025, -44.0, "SP")]}
        self.versao = {"cerrado": "20261016", "mata_atlantica": "20260806"}
        self.catalogos, self.baixados = 0, []

    def itens(self):
        self.catalogos += 1
        pasta = {"cerrado": "cerrado-prodes", "mata_atlantica": "mata-atlantica-prodes"}
        saida = []
        for b, v in self.versao.items():
            link = f"/download/dataset/{pasta[b]}/vector/yearly_deforestation_biome_{b}_v{v}.zip"
            saida += [{"name": "Incremento anual", "link": link, "lang": "pt"},
                      {"name": "Yearly increment", "link": link, "lang": "en"}]
        return saida

    def baixar(self, url, destino, atualizar=False):
        bioma = next(b for b in self.versao if f"biome_{b}_v" in url)
        self.baixados.append(bioma)
        escrever_zip(destino, self.poligonos[bioma])
        meta = {"url": url, "baixado_em_utc": "2026-10-30T10:00:00+00:00", "sha256": download.sha256(destino),
                "tamanho_bytes": destino.stat().st_size}
        return {"arquivo": str(destino.relative_to(config.RAIZ)), **meta}


@pytest.fixture
def tb(servico, tmp_path, monkeypatch):  # noqa: F811
    t = TerraBrasilisFalso(tmp_path)
    monkeypatch.setattr(config, "UFS", frozenset({"MG", "SP"}))
    monkeypatch.setattr(inpe_prodes, "PASTA_ARQUIVOS", tmp_path / "raw" / "arquivo_bioma")
    monkeypatch.setattr(inpe_prodes, "PASTA_PECAS", tmp_path / "processed" / "pecas")
    monkeypatch.setattr(inpe_prodes, "consultar_catalogo", lambda: inpe_prodes.catalogo(t.itens()))
    monkeypatch.setattr(download, "baixar", t.baixar)
    monkeypatch.setattr(inpe_prodes.config, "CAMADAS_PRODES",
                        {b: config.CAMADAS_PRODES[b] for b in ("cerrado", "mata_atlantica")})
    return t


# --- Catálogo e leitura ---------------------------------------------------------------------------------------------

def test_catalogo_fica_com_o_incremento_anual_do_bioma_e_a_versao_mais_nova():
    base = "/download/dataset/{}/vector/{}.zip"
    itens = [{"link": base.format("amz-prodes", "yearly_deforestation_biome_amazonia_v20261016")},
             {"link": base.format("amz-prodes", "yearly_deforestation_nf_biome_amazonia_v20261016")},
             {"link": base.format("amz-prodes", "yearly_deforestation_smaller_than_625ha_biome_amazonia_v20261016")},
             {"link": base.format("cerrado-prodes", "yearly_deforestation_biome_cerrado_v20260407")},
             {"link": base.format("cerrado-prodes", "yearly_deforestation_biome_cerrado_v20261016")},
             {"link": base.format("cerrado-prodes", "accumulated_deforestation_2000_biome_cerrado_v20261016")},
             {"link": "/download/dataset/cerrado-prodes/vector/prodes_biome_cerrado_v20261016.gpkg.zip"},
             {"link": base.format("x", "yearly_deforestation_biome_marte_v20261016")},
             {"link": base.format("pampa-prodes", "yearly_deforestation_biome_pampa_v20260807"), "enabled": False}]
    cat = inpe_prodes.catalogo(itens)
    assert sorted(cat) == ["amazonia", "cerrado"]
    assert cat["cerrado"]["versao"] == "2026-10-16"
    assert cat["amazonia"]["url"].endswith("yearly_deforestation_biome_amazonia_v20261016.zip")


def test_ler_arquivo_fica_com_os_anos_do_recorte_e_converte_a_data(tmp_path):
    z = escrever_zip(tmp_path / "a.zip", [("a", 2018, -47.0, "MG"), ("b", 2019, -46.0, "MG"), ("c", 2025, -46.5, "MG")])
    r = ResultadoFonte("inpe_prodes", "teste")
    df = inpe_prodes.ler_arquivo(z, "cerrado", r, desde=2019)
    assert df["uuid"].tolist() == ["b", "c"] and df["image_date"].tolist() == ["2019-07-20", "2025-07-20"]
    assert set(df["bioma"]) == {"cerrado"} and df["publish_year"].isna().all()
    saida, descartados = inpe_prodes.tratar(df, r)
    assert len(saida) == 2 and descartados.empty and ocorrencias(r, "PRODES_PUBLISH_YEAR_DIVERGENTE") == 0
    assert saida.loc[0, "area_km2"] == pytest.approx(saida.loc[0, "area_km2_fonte"])


def test_dbf_em_latin1_e_lido_sem_perder_o_acento(tmp_path):
    z = escrever_zip(tmp_path / "a.zip", [("a", 2024, -47.0, "MARANHÃO"), ("b", 2024, -46.0, "SÃO PAULO")],
                     codificacao="latin1")
    r = ResultadoFonte("inpe_prodes", "teste")
    saida, _ = inpe_prodes.tratar(inpe_prodes.ler_arquivo(z, "cerrado", r), r)
    assert saida["uf"].tolist() == ["MA", "SP"] and ocorrencias(r, "PRODES_DBF_LATIN1") == 1
    assert ocorrencias(r, "PRODES_UF_INVALIDA") == 0


def test_coordenada_gravada_com_seis_casas(tmp_path):
    z = escrever_zip(tmp_path / "a.zip", [("a", 2024, -47.123456789, "MG")])
    r = ResultadoFonte("inpe_prodes", "teste")
    saida, _ = inpe_prodes.tratar(inpe_prodes.ler_arquivo(z, "cerrado", r), r)
    assert "-47.123457" in saida.at[0, "geometria_wkt"] and "-47.1234568" not in saida.at[0, "geometria_wkt"]


def test_arquivo_fora_de_sirgas_interrompe(tmp_path):
    z = escrever_zip(tmp_path / "a.zip", [("a", 2024, -47.0, "MG")], prj='GEOGCS["WGS 84"]')
    with pytest.raises(ErroDeValidacao, match="PRODES_CRS_INESPERADO"):
        inpe_prodes.ler_arquivo(z, "cerrado", ResultadoFonte("inpe_prodes", "teste"))


# --- Lote -----------------------------------------------------------------------------------------------------------

def test_lote_pelo_arquivo_grava_as_ufs_com_o_poligono_de_divisa_nas_duas(tb):
    r = inpe_prodes.executar_arquivos(HOJE)
    mg, sp = inpe_prodes.ler_uf("MG"), inpe_prodes.ler_uf("SP")
    assert sorted(mg["uuid"]) == ["ce-0", "ce-1", "ce-4", "ma-0"]
    assert sorted(sp["uuid"]) == ["ce-2", "ce-4", "ma-1"]
    divisa = mg.set_index("uuid").loc["ce-4"]
    assert divisa["uf"] == "MG" and divisa["uf_fonte"] == "SP" and "UF_DIFERE_DO_CONTORNO" in divisa["alertas"]
    assert ocorrencias(r, "PRODES_CLASSE_FORA_DO_DOMINIO") == 1  # o reservatório
    pub = inpe_prodes.ler_publicacao()
    assert pub["origem"].startswith("arquivo") and pub["ufs"] == ["MG", "SP"]
    assert pub["ultimo_ano_publicado"] == {"cerrado": 2025, "mata_atlantica": 2025}
    assert pub["ufs_biomas"] == {"MG": ["cerrado", "mata_atlantica"], "SP": ["cerrado", "mata_atlantica"]}
    assert pub["proxima_verificacao"] == "2026-11-29" and pub["arquivos"]["cerrado"]["versao"] == "2026-10-16"
    assert tb.baixados == ["cerrado", "mata_atlantica"]
    descartados = pd.read_parquet(inpe_prodes.ARQ_DESCARTADOS)
    assert descartados[["uuid", "bioma"]].values.tolist() == [["ce-5", "cerrado"]]


def test_arquivo_e_wfs_dao_a_mesma_particao(tb, servico):  # noqa: F811
    """Os mesmos polígonos pelos dois caminhos: mesma partição, linha a linha (fora a data de publicação, que só a
    camada do WFS traz)."""
    servico.poligonos = {("cerrado", 2024): [(-47.0, "MINAS GERAIS")],
                         ("cerrado", 2025): [(-46.5, "MINAS GERAIS"), (-45.03, "SAO PAULO")],
                         ("mata_atlantica", 2024): [(-46.8, "MG")], ("mata_atlantica", 2025): []}
    inpe_prodes.executar(HOJE)
    pelo_wfs = inpe_prodes.ler_uf("MG")
    tb.poligonos = {"cerrado": [("ce2024-0", 2024, -47.0, "MINAS GERAIS"), ("ce2025-0", 2025, -46.5, "MINAS GERAIS"),
                                ("ce2025-1", 2025, -45.03, "SAO PAULO")],
                    "mata_atlantica": [("ma2024-0", 2024, -46.8, "MG")]}
    inpe_prodes.executar_arquivos(HOJE)
    pelo_arquivo = inpe_prodes.ler_uf("MG")
    colunas = ["uuid", "bioma", "ano_prodes", "data_imagem", "uf", "uf_fonte", "classe", "alertas"]
    a = pelo_wfs[colunas].sort_values("uuid").reset_index(drop=True)
    b = pelo_arquivo[colunas].sort_values("uuid").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
    ga = shapely.from_wkt(pelo_wfs.sort_values("uuid")["geometria_wkt"].to_numpy())
    gb = shapely.from_wkt(pelo_arquivo.sort_values("uuid")["geometria_wkt"].to_numpy())
    assert all(shapely.equals(ga, gb))


def test_dentro_do_mes_nao_consulta_o_catalogo(tb):
    inpe_prodes.executar_arquivos(HOJE)
    tb.catalogos, tb.baixados = 0, []
    r = inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=29))
    assert tb.catalogos == 0 and tb.baixados == [] and r.entrada["verificacao"].startswith("reaproveitada")
    # Com --verificar-prodes, consulta o catálogo; a versão é a mesma, então nada é baixado.
    r = inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=29), verificar=True)
    assert tb.catalogos == 1 and tb.baixados == [] and r.entrada["biomas_refeitos"] == []


def test_versao_nova_refaz_so_o_bioma_que_mudou_e_registra_o_ano_novo(tb):
    inpe_prodes.executar_arquivos(HOJE)
    assert not inpe_prodes.PASTA_PECAS.exists()  # as peças são temporárias
    ma_antes = inpe_prodes.ler_uf("MG").query("bioma == 'mata_atlantica'").reset_index(drop=True)
    velho = inpe_prodes.PASTA_ARQUIVOS / "yearly_deforestation_biome_cerrado_v20261016.zip"
    assert velho.exists()
    tb.baixados = []
    tb.versao["cerrado"] = "20271015"
    tb.poligonos["cerrado"].append(("ce-6", 2026, -47.2, "MINAS GERAIS"))
    r = inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=45))
    assert tb.baixados == ["cerrado"] and r.entrada["biomas_refeitos"] == ["cerrado"]
    # A Mata Atlântica não foi lida de novo: as linhas dela vêm da partição anterior, iguais.
    ma_depois = inpe_prodes.ler_uf("MG").query("bioma == 'mata_atlantica'").reset_index(drop=True)
    pd.testing.assert_frame_equal(ma_antes, ma_depois)
    assert "ce-6" in set(inpe_prodes.ler_uf("MG")["uuid"]) and "ma-0" in set(inpe_prodes.ler_uf("MG")["uuid"])
    assert ocorrencias(r, "PRODES_NOVO_ANO_PUBLICADO") == 1 and not velho.exists()
    pub = inpe_prodes.ler_publicacao()
    assert pub["ultimo_ano_publicado"]["cerrado"] == 2026
    assert pub["historico"][-1]["mudancas"] == [{"bioma": "cerrado", "ano": 2026, "tipo": "novo ano publicado",
                                                 "antes": "2026-10-16", "agora": "2027-10-15"}]
    assert "novo" in ficha_html._situacao_prodes(pub)  # a página marca o ano novo


def test_bioma_fora_do_catalogo_interrompe_e_o_lote_anterior_fica(tb):
    inpe_prodes.executar_arquivos(HOJE)
    sha = inpe_prodes.ler_publicacao()["particoes"]["MG"]["sha256"]
    tb.versao.pop("mata_atlantica")
    with pytest.raises(ErroDeValidacao, match="PRODES_BIOMA_FORA_DO_CATALOGO"):
        inpe_prodes.executar_arquivos(HOJE + pd.Timedelta(days=45))
    assert download.sha256(inpe_prodes.arquivo_uf("MG")) == sha


def test_particao_apagada_e_refeita_sem_ir_a_rede(tb):
    inpe_prodes.executar_arquivos(HOJE)
    inpe_prodes.arquivo_uf("SP").unlink()
    mg = download.sha256(inpe_prodes.arquivo_uf("MG"))
    tb.catalogos, tb.baixados = 0, []
    pub = inpe_prodes.garantir_uf("SP", HOJE + pd.Timedelta(days=1))
    assert "SP" in pub["particoes"] and tb.catalogos == 0
    assert sorted(inpe_prodes.ler_uf("SP")["uuid"]) == ["ce-2", "ce-4", "ma-1"]
    assert download.sha256(inpe_prodes.arquivo_uf("MG")) == mg  # a outra UF não é regravada


def test_prediagnostico_le_a_particao_do_lote_pelo_arquivo(tb):
    inpe_prodes.executar_arquivos(HOJE)
    prediagnostico._prodes_uf.cache_clear()
    prodes, situacao, procedencia = prediagnostico.obter_prodes("SP", (-44.01, Y - 0.01, -43.9, Y + 0.06))
    assert prodes["uuid"].tolist() == ["ma-1"] and situacao["ultimo_ano_publicado"]["cerrado"] == 2025
    assert situacao["ultima_imagem"] == {"cerrado": "2025-07-20", "mata_atlantica": "2025-07-20"}
    assert procedencia[0]["sha256"] == inpe_prodes.ler_publicacao()["particoes"]["SP"]["sha256"]


@pytest.mark.rede
def test_catalogo_real_tem_os_seis_biomas():
    cat = inpe_prodes.consultar_catalogo()
    assert set(cat) == set(config.CAMADAS_PRODES)
    assert all(v["versao"] >= "2026-01-01" for v in cat.values())
