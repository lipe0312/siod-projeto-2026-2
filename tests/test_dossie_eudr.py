"""Dossiê EUDR (#6): geojson, texto, JSON, as duas linhas de desmatamento e o "o que não foi verificado". Sem rede: a
ficha é sintética (imóvel, alertas e PRODES de tests/test_prediagnostico.py) e as cargas de origem são injetadas."""

import json
import re
from pathlib import Path

import pandas as pd
import pytest
import shapely

from conftest import CPF_VALIDO
from pipeline import config, dossie_eudr, ficha_html, prediagnostico, resultados, vetor
from test_area_producao import DADOS, NO_TALHAO, SO_NO_CAR
from test_prediagnostico import CAR, X0, Y0, alertas, car, embargos, lista_suja, prodes

SHA_DETER = "d" * 64
SHA_PRODES = "e" * 64
SHA_ZIP_DETER_PANTANAL = "f" * 64
ULTIMA = {"cerrado": pd.Timestamp("2026-10-28"), "amazonia": pd.Timestamp("2026-11-01")}
CARGA_DETER, CARGA_PRODES = "inpe_deter:20261103T210437", "inpe_prodes:20261103T210506"


def _cargas(raiz: Path) -> pd.DataFrame:
    """meta.carga sintética: o DETER do cerrado tem manifesto mensal em `raiz`; o PRODES tem o zip do bioma."""
    (raiz / "raw").mkdir(parents=True, exist_ok=True)
    (raiz / "raw" / "manifesto.json").write_text(json.dumps({
        "url": "https://terrabrasilis.exemplo/deter-cerrado/ows", "iniciado_em_utc": "2026-11-02T18:14:19+00:00",
        "particoes": [{"inicio": "2024-05-01", "fim": "2024-06-01", "arquivo": "2024-05.json.gz", "sha256": "0" * 64},
                      {"inicio": "2024-06-01", "fim": "2024-07-01", "arquivo": "2024-06.json.gz",
                       "sha256": SHA_DETER}]}), encoding="utf-8")
    deter = {"manifestos": {"cerrado": "raw/manifesto.json"},
             "arquivos": {"pantanal": {"url": "https://terrabrasilis.exemplo/deter-pantanal/shape",
                                       "baixado_em_utc": "2026-11-02T18:17:59+00:00", "sha256": SHA_ZIP_DETER_PANTANAL}}}
    prodes_ = {"arquivos": {"cerrado": {"url": "https://terrabrasilis.exemplo/cerrado_v20261016.zip",
                                        "versao": "2026-10-16", "sha256": SHA_PRODES}}}
    return pd.DataFrame([
        {"carga_id": CARGA_DETER, "fonte": "inpe_deter", "status": "ok", "iniciada_em": pd.Timestamp("2026-11-03 21:04:37"),
         "entrada_json": json.dumps(deter)},
        {"carga_id": CARGA_PRODES, "fonte": "inpe_prodes", "status": "ok",
         "iniciada_em": pd.Timestamp("2026-11-03 21:05:06"), "entrada_json": json.dumps(prodes_)}])


def _ficha(area=None, *alerta, poligonos_prodes=()):
    alt = alertas(*alerta).assign(camada="cerrado", carga_id=CARGA_DETER)
    prd = prodes(*poligonos_prodes).assign(carga_id=CARGA_PRODES)
    ficha = prediagnostico.diagnosticar(car(), embargos(), alt, lista_suja(), prd, ultimo_ano_prodes=2025,
                                        area_producao=area)
    ficha["consulta"] = {"gerado_em": "2026-11-05 10:00:00", "biomas": ["cerrado"], "documento_informado": False,
                         "prodes": {"origem": "lote", "ultimo_ano_do_imovel": 2025, "verificado_em": "2026-11-02",
                                    "ultima_imagem": {}}}
    ficha["procedencia"] = [{"fonte": "INPE PRODES (lote, partição MG)", "como": "lote", "data": "verificado em 2026-11-02",
                             "sha256": SHA_PRODES, "url": "x", "arquivo": "x"}]
    return ficha


def _area(arquivo="talhao.kml"):
    geom, crs = vetor.ler_area_producao(DADOS / arquivo)
    return {"geometria": geom, "arquivo": arquivo, "crs": crs, "motivo": None}


def _gerar(tmp_path, ficha, **kwargs):
    return dossie_eudr.escrever(ficha, tmp_path / "dossie", cargas=_cargas(tmp_path), raiz=tmp_path,
                                ultima_imagem_deter=ULTIMA, **kwargs)


def _textos(caminhos):
    return {k: p.read_text(encoding="utf-8") for k, p in caminhos.items()}


# --- critério 6: duas linhas de desmatamento na ficha ----------------------------------------------------------------

def test_ficha_com_area_tem_duas_linhas_de_desmatamento_e_o_resto_nunca_vira_pendencia():
    ficha = _ficha(_area(), ("na_area", NO_TALHAO, "2024-06-10"), ("no_resto", SO_NO_CAR, "2024-06-12"),
                   poligonos_prodes=[("p-resto", SO_NO_CAR, 2023, "2023-08-01")])
    por_chave = {c["chave"]: c for c in ficha["criterios"]}
    assert por_chave["desmatamento"]["situacao"] == "indício"
    assert "na área de produção" in por_chave["desmatamento"]["evidencia"]
    resto = por_chave["desmatamento_resto"]
    assert resto["situacao"] == "indício"  # PRODES 2023 no resto: ainda indício, não pendência (ADR 0018)
    assert "no resto do imóvel" in resto["evidencia"] and resto["fonte"] == "INPE DETER e PRODES"
    assert ficha["evidencias"]["alertas"]["id_alerta"].tolist() == ["na_area"]
    no_resto = ficha["evidencias"]["alertas_resto"]  # o alerta do talhão toca a borda dele: tangente, não conta
    assert no_resto.set_index("id_alerta")["classe"].to_dict() == {"na_area": "tangente", "no_resto": "principal"}
    assert ficha["evidencias"]["prodes_resto"]["uuid"].tolist() == ["p-resto"]
    assert ficha["area_producao"]["resto_ha"] > 0 and ficha["geometria_area_producao"]


def test_sem_area_de_producao_nada_muda_e_nao_ha_linha_do_resto():
    ficha = _ficha(None, ("a1", SO_NO_CAR, "2024-06-12"))
    chaves = [c["chave"] for c in ficha["criterios"]]
    assert "desmatamento_resto" not in chaves and "alertas_resto" not in ficha["evidencias"]
    assert "geometria_area_producao" not in ficha


def test_area_que_cobre_o_imovel_inteiro_nao_gera_resto():
    ficha = _ficha({"geometria": shapely.MultiPolygon([CAR]), "arquivo": "tudo.kml", "crs": "WGS 84", "motivo": None})
    assert "desmatamento_resto" not in [c["chave"] for c in ficha["criterios"]]
    assert ficha["area_producao"]["resto_ha"] < prediagnostico.LIMIAR_RESTO_HA


def test_ficha_html_mostra_o_resto_do_imovel():
    ficha = _ficha(_area(), ("no_resto", SO_NO_CAR, "2024-06-12"))
    ficha["procedencia"] = [{"fonte": "f", "como": "c", "data": "d", "sha256": SHA_PRODES, "arquivo": "a"}]
    html = ficha_html.renderizar(ficha)
    assert "Desmatamento no resto do imóvel (fora da área de produção declarada)" in html and "AR1" in html


def test_resultado_grava_a_evidencia_do_resto_no_criterio_proprio():
    ficha = _ficha(_area(), ("no_resto", SO_NO_CAR, "2024-06-12"))
    execucao = resultados.Execucao("avulsa")
    execucao.acrescentar(ficha)
    do_resto = [e for e in execucao.evidencias if e["chave_criterio"] == "desmatamento_resto"]
    assert [e["registro_id"] for e in do_resto] == ["no_resto"] and do_resto[0]["carga_id"] == CARGA_DETER
    assert "desmatamento_resto" in [c["chave"] for c in execucao.criterios]


# --- critério 2: geojson ---------------------------------------------------------------------------------------------

def test_geojson_so_a_area_declarada_em_wgs84_com_casas_e_marcado_declarado(tmp_path):
    ficha = _ficha(_area(), ("na_area", NO_TALHAO, "2024-06-10"))
    texto = _textos(_gerar(tmp_path, ficha, commodity="café"))["geojson"]
    dado = json.loads(texto)
    assert dado["type"] == "FeatureCollection" and dado["datum"].startswith("WGS 84")
    assert dado["escopo"] == "area_de_producao" and "declarado pelo produtor" in dado["declaracao"]
    assert "comprovado" not in dado["declaracao"].replace("não comprovado", "")
    (feature,) = dado["features"]
    assert feature["geometry"]["type"] == "Polygon" and feature["properties"]["commodity"] == "café"
    poligono = shapely.geometry.shape(feature["geometry"])
    declarada = vetor.tornar_valida(_area()["geometria"])
    assert shapely.symmetric_difference(poligono, declarada).area < 1e-9
    assert not shapely.covers(poligono, CAR)  # nunca a fazenda inteira por precaução
    assert shapely.is_ccw(poligono.exterior)
    numeros = re.findall(r"-?\d+\.\d+", texto[texto.index('"coordinates"'):])
    assert numeros and all(len(n.split(".")[1]) >= 6 for n in numeros)


def test_um_poligono_por_parcela_e_parcela_pequena_aceita_ponto(tmp_path):
    ficha = _ficha(_area("talhoes.geojson"))
    dado = json.loads(_textos(_gerar(tmp_path, ficha))["geojson"])
    assert [f["properties"]["parcela"] for f in dado["features"]] == [1, 2]
    assert all(f["geometry"]["type"] == "Polygon" for f in dado["features"])
    for f in dado["features"]:  # cada talhão tem ~4,6 ha ou menos: o ponto vem junto, dentro do polígono
        if f["properties"]["area_ha"] <= 4:
            assert shapely.geometry.Point(f["properties"]["ponto"]).within(shapely.geometry.shape(f["geometry"]))
        else:
            assert "ponto" not in f["properties"]


def test_sem_area_o_geojson_e_o_imovel_e_o_dossie_diz_isso(tmp_path):
    ficha = _ficha(None, ("a1", SO_NO_CAR, "2024-06-12"))
    textos = _textos(_gerar(tmp_path, ficha))
    dado = json.loads(textos["geojson"])
    assert dado["escopo"] == "imovel_inteiro" and "imóvel inteiro (perímetro do CAR)" in dado["descricao_do_escopo"]
    assert "### No imóvel inteiro (área de produção não informada)" in textos["md"]
    assert "Área de produção não informada" in textos["md"].split("## 4.")[1]
    assert "Resto do imóvel" not in textos["md"]


# --- critérios 3, 4, 5: texto e JSON ---------------------------------------------------------------------------------

def test_dossie_traz_data_da_imagem_e_sha256_da_origem_das_duas_linhas(tmp_path):
    ficha = _ficha(_area(), ("na_area", NO_TALHAO, "2024-06-10"), ("no_resto", SO_NO_CAR, "2024-06-12"),
                   poligonos_prodes=[("p-resto", SO_NO_CAR, 2023, "2023-08-01")])
    caminhos = _gerar(tmp_path, ficha, commodity="soja")
    assert set(caminhos) == {"json", "md", "geojson"} and {p.name for p in caminhos.values()} == {
        "dossie.json", "dossie.md", "dossie.geojson"}
    textos, dossie = _textos(caminhos), json.loads(caminhos["json"].read_text(encoding="utf-8"))
    md = textos["md"]
    assert "### Na área declarada (decide o critério da EUDR)" in md
    blocos = dossie["desmatamento_apos_31_12_2020"]["blocos"]
    assert set(blocos) == {"desmatamento", "desmatamento_resto"}
    assert blocos["desmatamento"]["decide_a_eudr"] and not blocos["desmatamento_resto"]["decide_a_eudr"]
    area, resto = blocos["desmatamento"], blocos["desmatamento_resto"]
    assert [a["id_alerta"] for a in area["alertas_deter"]] == ["na_area"]
    assert area["alertas_deter"][0]["data_da_imagem"] == "10/06/2024"
    assert area["alertas_deter"][0]["origem"]["sha256"] == SHA_DETER  # partição de junho/2024 do manifesto
    assert area["alertas_deter"][0]["origem"]["arquivo"] == "raw/2024-06.json.gz"
    assert resto["poligonos_prodes"][0]["origem"]["sha256"] == SHA_PRODES
    assert resto["poligonos_prodes"][0]["data_da_imagem"] == "01/08/2023"
    for trecho in ("10/06/2024", "12/06/2024", "01/08/2023", SHA_DETER, SHA_PRODES, "No resto do imóvel",
                   "Embargo IBAMA", "indígena", "Lista Suja", "commodity", "Commodity:** soja"):
        assert trecho.lower() in md.lower(), trecho
    bases = {(b["fonte"], b["bioma"]): b for b in dossie["desmatamento_apos_31_12_2020"]["bases_consultadas"]}
    assert bases[("INPE DETER", "cerrado")]["carga_em"] == "03/11/2026"
    assert bases[("INPE DETER", "cerrado")]["ultima_imagem_na_base"] == "28/10/2026"
    assert bases[("INPE PRODES", "cerrado")]["sha256"] == SHA_PRODES


def test_sem_ocorrencia_so_aparece_com_fonte_e_data_e_nunca_como_conforme(tmp_path):
    ficha = _ficha(_area())
    textos = _textos(_gerar(tmp_path, ficha, commodity="café"))
    md = textos["md"].lower()
    assert "sem ocorrência" in md and "nenhum alerta deter nem polígono prodes" in md
    assert ("Fontes e datas: INPE DETER cerrado (base carregada em 03/11/2026, imagens até 28/10/2026); "
            "INPE PRODES cerrado (base carregada em 03/11/2026, publicado até 2025, verificado em 02/11/2026)") in textos["md"]
    secao = textos["md"].split("### Bases consultadas")[1].split("## 3.")[0]
    assert "03/11/2026" in secao and "28/10/2026" in secao and SHA_PRODES in secao
    for proibido in ("conforme", "livre de desmatamento", "desmatamento zero", "zero desmatamento"):
        assert proibido not in md and proibido not in textos["json"].lower()


def test_nao_verificado_sempre_presente_com_criterios_1_2_8_e_bioma_sem_deter(tmp_path):
    ficha = _ficha(_area(), poligonos_prodes=[])
    ficha["consulta"]["biomas"] = ["cerrado", "mata_atlantica"]
    ficha["criterios"] = [dict(c, aviso="Mata Atlântica sem DETER: sem cobertura de 01/08/2025 até hoje")
                          if c["chave"] == "desmatamento" else c for c in ficha["criterios"]]
    caminhos = _gerar(tmp_path, ficha, commodity="gado bovino")
    md = caminhos["md"].read_text(encoding="utf-8")
    secao = md.split("## 4. O que não foi verificado")[1].split("## 5.")[0]
    for n in (1, 2, 8):
        assert f"Critério {n} do AB+S" in secao
    assert "Mata Atlântica sem DETER" in secao and "Bioma mata_atlantica sem DETER" in secao
    assert "Gado" in secao and "declaração do produtor" in secao
    assert json.loads(caminhos["json"].read_text(encoding="utf-8"))["nao_verificado"]


def test_sha256_que_a_carga_nao_registra_vai_para_o_nao_verificado(tmp_path):
    ficha = _ficha(_area(), ("na_area", NO_TALHAO, "2024-06-10"))
    caminhos = dossie_eudr.escrever(ficha, tmp_path / "d", cargas=pd.DataFrame(columns=_cargas(tmp_path).columns),
                                    raiz=tmp_path, ultima_imagem_deter=ULTIMA)
    secao = caminhos["md"].read_text(encoding="utf-8").split("## 4.")[1].split("## 5.")[0]
    assert "SHA-256 do arquivo de origem não localizado em 1 evidência" in secao


def test_prazos_com_fonte_e_formato_sem_link_inventado(tmp_path):
    md = _textos(_gerar(tmp_path, _ficha(_area())))["md"]
    assert "30/12/2026" in md and "30/06/2027" in md and "eur-lex.europa.eu/eli/reg/2023/1115/oj" in md
    assert "744919a7-8650-4850-89ad-a597268cd69e" in md and "05/11/2026" in md  # FAQ 5ª versão, como em docs/
    assert "confira a especificação vigente" in md


def test_imovel_nao_localizado_gera_dossie_inconclusivo_sem_poligono(tmp_path):
    ficha = {"consulta": {"gerado_em": "2026-11-05 10:00:00"}, **prediagnostico.ficha_inconclusiva("CAR não localizado no SICAR"),
             "procedencia": []}
    caminhos = _gerar(tmp_path, ficha)
    assert set(caminhos) == {"json", "md"}
    md = caminhos["md"].read_text(encoding="utf-8")
    assert "Imóvel não localizado" in md and "CAR não localizado no SICAR" in md.split("## 4.")[1]


def test_nenhum_cpf_nem_cnpj_no_dossie(tmp_path):
    ficha = _ficha(_area(), ("na_area", NO_TALHAO, "2024-06-10"))
    caminhos = _gerar(tmp_path, ficha, commodity=f"café {CPF_VALIDO}")
    for texto in _textos(caminhos).values():
        assert CPF_VALIDO not in texto and "11144477735" not in texto and "111.444.777" not in texto


# --- linha de comando ------------------------------------------------------------------------------------------------

def test_linha_de_comando_gera_a_pasta_com_area_e_commodity(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREDIAGNOSTICO", tmp_path / "prediagnostico")
    usadas = []

    def executar(cod, lat, lon, documento, atualizar, baixar, area_producao=None):
        usadas.append(area_producao)
        ficha = _ficha(area_producao)
        ficha["imovel"] = {**ficha["imovel"], "cod_imovel": cod}
        return {"consulta": ficha.pop("consulta"), **ficha}

    monkeypatch.setattr(prediagnostico, "executar", executar)
    cargas = _cargas(tmp_path)  # sem isto o dossiê leria meta.carga do lago
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(dossie_eudr.lago, "ler_ou_none", lambda tabela, **k: cargas if tabela == "meta.carga" else None)
    monkeypatch.setattr(dossie_eudr, "_ultima_imagem_deter", lambda: ULTIMA)
    escrever_ficha = prediagnostico.escrever  # o padrão de `pasta` é fixado na importação: aponta para a pasta do teste
    monkeypatch.setattr(prediagnostico, "escrever", lambda ficha: escrever_ficha(ficha, tmp_path / "fichas"))
    shutil_kml = tmp_path / "entrada" / "talhao.kml"
    shutil_kml.parent.mkdir()
    shutil_kml.write_bytes((DADOS / "talhao.kml").read_bytes())
    assert prediagnostico.main(["--car", "MG-1", "--dossie-eudr", "--area-producao", str(shutil_kml),
                                "--commodity", "café"]) == 0
    pasta = tmp_path / "prediagnostico" / "dossie_eudr" / "MG-1"
    dossie = json.loads((pasta / "dossie.json").read_text(encoding="utf-8"))
    assert dossie["desmatamento_apos_31_12_2020"]["blocos"]["desmatamento"]["situacao"] == "sem ocorrência"
    assert sorted(p.name for p in pasta.iterdir()) == ["dossie.geojson", "dossie.json", "dossie.md"]
    assert usadas[0]["geometria"] is not None and usadas[0]["arquivo"] == "talhao.kml"
    assert json.loads((pasta / "dossie.json").read_text(encoding="utf-8"))["commodity"] == "café"
    with pytest.raises(SystemExit):
        prediagnostico.main(["--demo", "--dossie-eudr"])


def test_cli_nao_sai_da_pasta_do_dossie_com_codigo_de_imovel_estranho(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREDIAGNOSTICO", tmp_path / "prediagnostico")
    cargas = _cargas(tmp_path)
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(dossie_eudr.lago, "ler_ou_none", lambda tabela, **k: cargas if tabela == "meta.carga" else None)
    monkeypatch.setattr(dossie_eudr, "_ultima_imagem_deter", lambda: ULTIMA)
    monkeypatch.setattr(prediagnostico, "escrever", lambda ficha: {"html": Path("ficha.html")})  # só o dossiê importa

    def executar(cod, lat, lon, documento, atualizar, baixar, area_producao=None):
        ficha = _ficha(None)
        ficha["imovel"] = {**ficha["imovel"], "cod_imovel": "../../fora/MG-1"}
        return {"consulta": ficha.pop("consulta"), **ficha}

    monkeypatch.setattr(prediagnostico, "executar", executar)
    prediagnostico.main(["--car", "x", "--dossie-eudr"])
    raiz = tmp_path / "prediagnostico" / "dossie_eudr"
    assert [p.name for p in raiz.iterdir()] == ["fora_MG-1"] and not (tmp_path / "fora").exists()


# --- fonte, data e SHA-256 incompletos: inconclusivo, nunca "sem ocorrência" (ADR 0013) -----------------------------

def test_ultima_imagem_deter_e_a_do_bioma_do_imovel_e_nao_a_de_toda_a_base(tmp_path, monkeypatch):
    base = pd.DataFrame({"camada": ["cerrado", "cerrado", "amazonia"],
                         "data_imagem": pd.to_datetime(["2026-01-10", "2026-01-31", "2026-10-30"])})
    monkeypatch.setattr(dossie_eudr.lago, "ler_ou_none", lambda tabela, **k: base)
    ultima = dossie_eudr._ultima_imagem_deter()
    assert ultima == {"cerrado": pd.Timestamp("2026-01-31"), "amazonia": pd.Timestamp("2026-10-30")}
    ficha = _ficha(_area())  # imóvel só no Cerrado
    caminhos = dossie_eudr.escrever(ficha, tmp_path / "d", cargas=_cargas(tmp_path), raiz=tmp_path,
                                    ultima_imagem_deter=ultima)
    md = caminhos["md"].read_text(encoding="utf-8")
    assert "imagens até 31/01/2026" in md and "30/10/2026" not in md
    deter = next(b for b in json.loads(caminhos["json"].read_text(encoding="utf-8"))[
        "desmatamento_apos_31_12_2020"]["bases_consultadas"] if b["fonte"] == "INPE DETER")
    assert deter["ultima_imagem_na_base"] == "31/01/2026"


@pytest.mark.parametrize("cargas, esperado", [
    (None, "carga do DETER não registrada em meta.carga"),
    (pd.DataFrame(columns=["carga_id", "fonte", "status", "iniciada_em", "entrada_json"]),
     "carga do PRODES não registrada em meta.carga"),
])
def test_sem_carga_o_zero_achados_vira_inconclusivo_com_motivo_e_entra_no_nao_verificado(tmp_path, cargas, esperado):
    ficha = _ficha(_area())
    caminhos = dossie_eudr.escrever(ficha, tmp_path / "d", cargas=cargas if cargas is not None else
                                    pd.DataFrame(columns=["carga_id", "fonte", "status", "iniciada_em", "entrada_json"]),
                                    raiz=tmp_path, ultima_imagem_deter=ULTIMA)
    dossie = json.loads(caminhos["json"].read_text(encoding="utf-8"))
    md = caminhos["md"].read_text(encoding="utf-8")
    for bloco in dossie["desmatamento_apos_31_12_2020"]["blocos"].values():
        assert bloco["situacao"] == "inconclusivo" and bloco["situacao_da_ficha"] == "sem ocorrência"
        assert any(esperado in m for m in bloco["lacunas_de_fonte"])
    assert "**Situação nas bases consultadas: inconclusivo.**" in md and "sem ocorrência.** Nenhum alerta" not in md
    assert "data desconhecida" not in md
    secao = md.split("## 4.")[1].split("## 5.")[0]
    assert "desmatamento inconclusivo" in secao and esperado in secao
    assert "SHA-256 do arquivo de origem do DETER não localizado" in secao


def test_sem_ultima_imagem_do_bioma_o_deter_fica_incompleto(tmp_path):
    ficha = _ficha(_area())
    caminhos = dossie_eudr.escrever(ficha, tmp_path / "d", cargas=_cargas(tmp_path), raiz=tmp_path,
                                    ultima_imagem_deter={"amazonia": pd.Timestamp("2026-11-01")})
    bloco = json.loads(caminhos["json"].read_text(encoding="utf-8"))["desmatamento_apos_31_12_2020"]["blocos"][
        "desmatamento"]
    assert bloco["situacao"] == "inconclusivo"
    assert "última imagem DETER do bioma cerrado desconhecida" in " ".join(bloco["lacunas_de_fonte"])


def test_achado_confirmado_continua_pendencia_mesmo_com_fonte_incompleta(tmp_path):
    ficha = _ficha(_area(), ("na_area", NO_TALHAO, "2024-06-10"), poligonos_prodes=[("p", NO_TALHAO, 2023, "2023-08-01")])
    caminhos = dossie_eudr.escrever(ficha, tmp_path / "d", cargas=pd.DataFrame(
        columns=["carga_id", "fonte", "status", "iniciada_em", "entrada_json"]), raiz=tmp_path,
        ultima_imagem_deter=ULTIMA)
    bloco = json.loads(caminhos["json"].read_text(encoding="utf-8"))["desmatamento_apos_31_12_2020"]["blocos"][
        "desmatamento"]
    assert bloco["situacao"] == "pendência" and bloco["lacunas_de_fonte"]


# --- carteira: o dossiê de todos os imóveis de uma vez (#20) -----------------------------------------------------------

def _carteira_sintetica(tmp_path, monkeypatch, consultar_extra=None):
    """Planilha de 3 imóveis: A com área de produção, B sem área, C que o SICAR não encontra."""
    from pipeline import carteira

    cargas = _cargas(tmp_path)
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(dossie_eudr.lago, "ler_ou_none", lambda tabela, **k: cargas if tabela == "meta.carga" else None)
    monkeypatch.setattr(dossie_eudr, "_ultima_imagem_deter", lambda: ULTIMA)
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "talhao.kml").write_bytes((DADOS / "talhao.kml").read_bytes())
    df = pd.DataFrame([
        {"id_produtor": "P1", "cod_car": "MG-1", "commodity": "café", "area_producao": "talhao.kml",
         "documento": CPF_VALIDO},
        {"id_produtor": "P2", "cod_car": "MG-2", "commodity": "soja", "area_producao": None},
        {"id_produtor": "P3", "cod_car": "MG-404/../x", "commodity": "milho", "area_producao": None}])

    def consultar(cod, lat, lon, documento, baixar_prodes=True, area_producao=None):
        if consultar_extra:
            consultar_extra(cod)
        if cod.startswith("MG-404"):
            return {"consulta": {"gerado_em": "2026-11-05 10:00:00", "documento_informado": False},
                    **prediagnostico.ficha_inconclusiva("CAR não localizado no SICAR"), "procedencia": []}
        ficha = _ficha(area_producao, ("na_area", NO_TALHAO, "2024-06-10"))
        ficha["imovel"] = {**ficha["imovel"], "cod_imovel": cod}
        return {"consulta": ficha.pop("consulta"), **ficha}

    areas = carteira.areas_de_producao(df, entrada)
    execucao = resultados.Execucao("carteira", "demonstracao")
    saida = carteira.processar(df, tmp_path / "saida", consultar=consultar, execucao=execucao, areas=areas,
                               dossie_eudr=True)
    return saida, execucao, tmp_path / "saida" / "dossie_eudr"


def test_carteira_gera_o_dossie_de_cada_imovel_e_o_indice(tmp_path, monkeypatch, lago_temporario):
    _, execucao, raiz = _carteira_sintetica(tmp_path, monkeypatch)
    indice = pd.read_csv(raiz / "indice.csv", dtype=str, keep_default_na=False).set_index("cod_car")
    assert list(indice.columns) == dossie_eudr.COLUNAS_INDICE[1:] and len(indice) == 3
    assert sorted(p.name for p in (raiz / "MG-1").iterdir()) == ["dossie.geojson", "dossie.json", "dossie.md"]
    a, b = indice.loc["MG-1"], indice.loc["MG-2"]
    assert a.escopo == "área de produção" and b.escopo == "imóvel inteiro" and a.commodity == "café"
    assert a.desmatamento_area_declarada == "indício" and a.pasta == "dossie_eudr/MG-1"
    assert a.desmatamento_resto_do_imovel != dossie_eudr.NAO_SE_APLICA  # a área é menor que o imóvel
    assert b.desmatamento_resto_do_imovel == dossie_eudr.NAO_SE_APLICA
    assert (raiz / "MG-1" / "dossie.json").read_text(encoding="utf-8").count("área de produção informada") >= 1
    assert "imóvel inteiro" in (raiz / "MG-2" / "dossie.md").read_text(encoding="utf-8")
    assert set(indice.execucao_id) == {execucao.id}


def test_imovel_com_falha_vira_linha_inconclusiva_com_motivo_e_nao_para_os_outros(tmp_path, monkeypatch, lago_temporario):
    saida, _, raiz = _carteira_sintetica(tmp_path, monkeypatch)
    indice = pd.read_csv(raiz / "indice.csv", dtype=str, keep_default_na=False)
    falha = indice[indice.cod_car.str.startswith("MG-404")].iloc[0]
    assert falha.desmatamento_area_declarada == "inconclusivo" and "não localizado" in falha.motivo
    assert (raiz.parent / falha.pasta / "dossie.md").exists() and ".." not in falha.pasta  # nome sanitizado, como na #6
    assert len(saida) == 3 and (raiz / "MG-2" / "dossie.json").exists()


def test_excecao_na_consulta_e_linha_sem_cod_car_entram_no_indice_sem_derrubar_o_lote(tmp_path, monkeypatch,
                                                                                      lago_temporario):
    def explode(cod):
        if cod == "MG-2":
            raise TimeoutError("SICAR fora do ar")

    _, _, raiz = _carteira_sintetica(tmp_path, monkeypatch, explode)
    indice = pd.read_csv(raiz / "indice.csv", dtype=str, keep_default_na=False).set_index("cod_car")
    assert "TimeoutError" in indice.loc["MG-2"].motivo and indice.loc["MG-2"].pasta == ""
    assert indice.loc["MG-2"].desmatamento_area_declarada == "inconclusivo"
    assert indice.loc["MG-1"].desmatamento_area_declarada == "indício"


def test_indice_e_dossies_do_lote_sem_cpf_nem_documento_hash(tmp_path, monkeypatch, lago_temporario):
    _, _, raiz = _carteira_sintetica(tmp_path, monkeypatch)
    for arquivo in raiz.rglob("*"):
        if arquivo.is_file():
            texto = arquivo.read_text(encoding="utf-8")
            assert CPF_VALIDO not in texto and "11144477735" not in texto and "documento_hash" not in texto
