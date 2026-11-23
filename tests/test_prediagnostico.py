import json

import numpy as np
import pandas as pd
import pytest
import shapely

from conftest import CHAVE, CPF_VALIDO, CPF_VALIDO_2
from pipeline import prediagnostico
from pipeline.documentos import pseudonimizar, somente_digitos

X0, Y0 = -46.99, -18.95
METRO = 1 / 105_000  # grau de longitude, aproximado, nesta latitude
CAR = shapely.box(X0, Y0, X0 + 0.01, Y0 + 0.01)
DENTRO = shapely.box(X0 + 0.002, Y0 + 0.002, X0 + 0.004, Y0 + 0.004)
NA_DIVISA = shapely.box(X0 + 0.01 - 10 * METRO, Y0 + 0.002, X0 + 0.02, Y0 + 0.008)  # 10 m dentro do CAR
FORA = shapely.box(X0 + 0.5, Y0, X0 + 0.51, Y0 + 0.01)


def hash_doc(doc):
    return pseudonimizar(somente_digitos(pd.Series([doc])), CHAVE).iloc[0]


def car(status="AT", condicao="Aguardando análise"):
    return pd.DataFrame([{
        "cod_imovel": "MG-3148103-" + "A" * 32, "uf": "MG", "cod_municipio": "3148103", "municipio": "Patrocínio",
        "tipo_imovel": "IRU", "status_imovel": status, "condicao": condicao, "area_geom_ha": 115.0, "m_fiscal": 2.9,
        "fracao_coberta_por_outros": 0.0, "data_atualizacao": pd.Timestamp("2025-05-16"), "geometria_wkt": CAR.wkt}])


def embargos(*linhas):
    """linhas: (id, geometria ou None, (lat, lon) ou None, documento ou None)."""
    return pd.DataFrame([{
        "id_embargo": i, "num_tad": i.upper(), "ser_tad": "E", "data_embargo": pd.Timestamp("2023-03-01"),
        "area_ha": 4.0, "descricao_infracao": "Desmatar", "municipio": "Patrocínio", "uf": "MG",
        "geometria_wkt": g.wkt if g else None, "latitude": p[0] if p else None, "longitude": p[1] if p else None,
        "documento_hash": hash_doc(d) if d else None} for i, g, p, d in linhas],
        columns=["id_embargo", "num_tad", "ser_tad", "data_embargo", "area_ha", "descricao_infracao", "municipio",
                 "uf", "geometria_wkt", "latitude", "longitude", "documento_hash"])


def alertas(*linhas):
    """linhas: (id, geometria, data da imagem)."""
    return pd.DataFrame([{"id_alerta": i, "classe": "DESMATAMENTO_CR", "data_imagem": pd.Timestamp(d),
                          "area_km2": 0.04, "satelite": "AMAZONIA-1", "uf": "MG", "geometria_wkt": g.wkt}
                         for i, g, d in linhas],
                        columns=["id_alerta", "classe", "data_imagem", "area_km2", "satelite", "uf", "geometria_wkt"])


def prodes(*linhas):
    """linhas: (uuid, geometria, ano PRODES, data da imagem)."""
    return pd.DataFrame([{"uuid": u, "bioma": "cerrado", "ano_prodes": a, "data_imagem": pd.Timestamp(d),
                          "area_km2": 0.04, "geometria_wkt": g.wkt} for u, g, a, d in linhas],
                        columns=["uuid", "bioma", "ano_prodes", "data_imagem", "area_km2", "geometria_wkt"])


def lista_suja(*docs):
    return pd.DataFrame([{"id_registro": f"r{k}", "uf": "MG", "cnae": "0134-2/00",
                          "data_inclusao": pd.Timestamp("2024-04-05"), "data_decisao": pd.Timestamp("2023-11-01"),
                          "documento_hash": hash_doc(d)} for k, d in enumerate(docs)],
                        columns=["id_registro", "uf", "cnae", "data_inclusao", "data_decisao", "documento_hash"])


def diagnosticar(car_df=None, emb=None, alt=None, prd=None, ls=None, documento=None):
    return prediagnostico.diagnosticar(
        car() if car_df is None else car_df, embargos() if emb is None else emb, alertas() if alt is None else alt,
        lista_suja() if ls is None else ls, prodes() if prd is None else prd,
        hash_doc(documento) if documento else None, ultimo_ano_prodes=2025)


def situacoes(ficha):
    return {c["chave"]: c["situacao"] for c in ficha["criterios"]}


def test_imovel_sem_nada_nas_fontes_e_sem_pendencia_mas_nao_e_conforme():
    ficha = diagnosticar(documento=CPF_VALIDO)
    s = situacoes(ficha)
    assert [s["car"], s["embargo"], s["desmatamento"], s["lista_suja"], s["terra_indigena"], s["quilombola"],
            s["unidade_conservacao"]] == ["sem ocorrência"] * 7
    assert ficha["resultado"]["situacao"] == "sem pendência nas fontes verificadas"
    # Os critérios do AB+S sem fonte aberta (1, 2 e 8) aparecem como "não verificado", nunca como conformes.
    assert ficha["resultado"]["contagem"]["não verificado"] == 3
    assert not any("conforme" == c["situacao"] for c in ficha["criterios"])


def test_embargo_por_poligono_coordenada_e_documento_e_pendencia_e_o_da_divisa_nao():
    emb = embargos(("dentro", DENTRO, None, None), ("divisa", NA_DIVISA, None, None),
                   ("ponto", None, (Y0 + 0.005, X0 + 0.005), None), ("doc", FORA, None, CPF_VALIDO),
                   ("longe", FORA, None, None))
    ficha = diagnosticar(emb=emb, documento=CPF_VALIDO)
    achados = ficha["evidencias"]["embargos"].set_index("id_embargo")
    assert achados["como"].to_dict() == {"dentro": "polígono", "divisa": "polígono", "ponto": "coordenada",
                                         "doc": "documento"}
    assert achados.at["divisa", "classe"] == "tangente"
    criterio = next(c for c in ficha["criterios"] if c["chave"] == "embargo")
    assert criterio["situacao"] == "pendência" and criterio["evidencia"].startswith("3 embargo(s)")
    assert "1 na divisa" in criterio["evidencia"]


def test_embargo_achado_pelo_poligono_e_pelo_documento_fica_numa_linha_so():
    ficha = diagnosticar(emb=embargos(("e1", DENTRO, None, CPF_VALIDO)), documento=CPF_VALIDO)
    assert ficha["evidencias"]["embargos"]["como"].tolist() == ["polígono e documento"]


def test_alerta_confirmado_pelo_prodes_e_pendencia():
    ficha = diagnosticar(alt=alertas(("a1", DENTRO, "2022-09-10")),
                         prd=prodes(("p1", DENTRO, 2023, "2023-07-15")))
    assert ficha["evidencias"]["alertas"].at[0, "situacao_prodes"] == "confirmado"
    assert situacoes(ficha)["desmatamento"] == "pendência"
    assert ficha["resultado"]["situacao"] == "com pendência"


def test_alerta_sem_prodes_e_so_indicio():
    ficha = diagnosticar(alt=alertas(("a1", DENTRO, "2025-08-28")))
    assert ficha["evidencias"]["alertas"].at[0, "situacao_prodes"] == "aguardando consolidação"
    assert situacoes(ficha)["desmatamento"] == "indício"
    assert ficha["resultado"]["situacao"] == "com indício"


def test_alerta_na_divisa_nao_conta():
    ficha = diagnosticar(alt=alertas(("a1", NA_DIVISA, "2022-09-10")))
    assert ficha["evidencias"]["alertas"].at[0, "situacao_prodes"] == "não avaliado"
    assert situacoes(ficha)["desmatamento"] == "sem ocorrência"


@pytest.mark.parametrize("ano, esperado", [(2021, "indício"), (2022, "pendência"), (2020, "sem ocorrência")])
def test_prodes_sozinho_depende_do_ano(ano, esperado):
    # O ano PRODES 2021 começa em 01/08/2020, antes da data de corte; 2020 inteiro é anterior.
    ficha = diagnosticar(prd=prodes(("p1", DENTRO, ano, f"{ano}-07-15")))
    assert situacoes(ficha)["desmatamento"] == esperado


@pytest.mark.parametrize("status, condicao, esperado", [
    ("CA", "Cancelado por decisão administrativa", "pendência"), ("SU", "Suspenso", "pendência"),
    ("PE", "Aguardando análise", "indício"), ("AT", "Analisado, aguardando atendimento a notificação", "indício"),
    ("AT", "Analisado, em conformidade com a Lei nº 12.651/2012", "sem ocorrência")])
def test_status_do_car(status, condicao, esperado):
    assert situacoes(diagnosticar(car(status, condicao)))["car"] == esperado


def test_lista_suja_pelo_documento_e_sem_documento_nao_verifica():
    ls = lista_suja(CPF_VALIDO)
    assert situacoes(diagnosticar(ls=ls, documento=CPF_VALIDO))["lista_suja"] == "pendência"
    assert situacoes(diagnosticar(ls=ls, documento=CPF_VALIDO_2))["lista_suja"] == "sem ocorrência"
    assert situacoes(diagnosticar(ls=ls))["lista_suja"] == "não verificado"


def test_ponto_em_dois_cars_e_inconclusivo(monkeypatch):
    dois = pd.concat([car(), car().assign(cod_imovel="MG-3148103-" + "B" * 32)], ignore_index=True)

    class R:
        entrada = {"servico": "sicar", "requisicoes": []}

    monkeypatch.setattr(prediagnostico.territorio, "uf_do_ponto", lambda lat, lon: "MG")
    monkeypatch.setattr(prediagnostico.sicar, "consultar_ponto", lambda lat, lon, uf, atualizar: (dois, R()))
    ficha = prediagnostico.executar(lat=Y0 + 0.005, lon=X0 + 0.005)
    assert ficha["resultado"]["situacao"] == "inconclusivo"
    assert len(ficha["imovel"]["candidatos"]) == 2


def test_ponto_fora_do_brasil_e_inconclusivo_sem_consultar_o_sicar(monkeypatch):
    monkeypatch.setattr(prediagnostico.territorio, "uf_do_ponto", lambda lat, lon: None)
    monkeypatch.setattr(prediagnostico.sicar, "consultar_ponto", lambda *a, **k: pytest.fail("consultou o SICAR"))
    ficha = prediagnostico.executar(lat=-20.0, lon=-30.0)
    assert ficha["resultado"]["situacao"] == "inconclusivo"
    assert "fora do território" in ficha["criterios"][0]["evidencia"]


def test_escreve_json_markdown_e_html_sem_documento_em_claro(tmp_path):
    ficha = diagnosticar(emb=embargos(("dentro", DENTRO, None, None)), alt=alertas(("a1", DENTRO, "2025-08-28")),
                         documento=CPF_VALIDO)
    ficha = {"consulta": {"gerado_em": "2026-10-30 10:00:00", "documento_informado": True, "cod_imovel": None},
             **ficha, "procedencia": [{"fonte": "SICAR (WFS)", "como": "sob demanda", "data": "2026-10-30",
                                       "sha256": "ab" * 32, "arquivo": "data/raw/sicar/x.geojson.gz"}]}
    caminhos = prediagnostico.escrever(ficha, tmp_path)
    dados = json.loads(caminhos["json"].read_text())
    assert dados["resultado"]["situacao"] == "com pendência"
    assert "geometria_wkt" not in dados["evidencias"]["embargos"][0]
    html = caminhos["html"].read_text()
    assert "<svg" in html and "E1" in html and "A1" in html
    for arquivo in caminhos.values():
        texto = arquivo.read_text()
        assert CPF_VALIDO not in texto and somente_digitos(pd.Series([CPF_VALIDO])).iloc[0] not in texto


def _ficha_para_escrever(cod_imovel=None, **kwargs):
    ficha = diagnosticar(**kwargs)
    if cod_imovel:
        ficha["imovel"]["cod_imovel"] = cod_imovel
    return {"consulta": {"gerado_em": "2026-10-30 10:00:00", "documento_informado": False, "cod_imovel": None},
            **ficha, "procedencia": []}


def _camadas(caminhos):
    return json.loads(caminhos["camadas"].read_text(encoding="utf-8"))


def test_camadas_geojson_tem_os_rotulos_da_ficha_e_coordenadas_em_graus(tmp_path):
    ficha = _ficha_para_escrever(
        emb=embargos(("dentro", DENTRO, None, None), ("sem_poligono", None, (Y0 + 0.005, X0 + 0.005), None)),
        alt=alertas(("a1", DENTRO, "2025-08-28"), ("a2", NA_DIVISA, "2025-09-10")),
        prd=prodes(("p1", DENTRO, 2023, "2023-07-20")))
    caminhos = prediagnostico.escrever(ficha, tmp_path)
    colecao, html = _camadas(caminhos), caminhos["html"].read_text(encoding="utf-8")
    assert colecao["type"] == "FeatureCollection" and "CRS84" in colecao["crs"]["properties"]["name"]
    por_rotulo = {f["properties"]["rotulo"]: f for f in colecao["features"]}
    assert set(por_rotulo) == {"CAR", "A1", "A2", "P1", "E1"}  # o embargo achado só pela coordenada não tem polígono
    for rotulo in set(por_rotulo) - {"CAR"}:
        assert f"<b>{rotulo}</b>" in html  # o mesmo rótulo da tabela da ficha
    for f in colecao["features"]:
        assert set(f["properties"]) == {"camada", "rotulo", "situacao", "data_imagem", "fonte", "ha"}
        xs, ys = zip(*[c for anel in f["geometry"]["coordinates"] for c in anel])
        assert all(-75 < x < -30 for x in xs) and all(-35 < y < 6 for y in ys)  # graus, não metros
        assert all(round(v, 6) == v for v in (*xs, *ys))
    assert por_rotulo["A1"]["properties"] | {"ha": None} == {
        "camada": "alerta_deter", "rotulo": "A1", "situacao": por_rotulo["A1"]["properties"]["situacao"],
        "data_imagem": "2025-08-28", "fonte": "INPE DETER", "ha": None}
    assert por_rotulo["A1"]["properties"]["ha"] > 0 and por_rotulo["CAR"]["properties"]["ha"] == 115.0
    assert por_rotulo["E1"]["properties"]["fonte"] == "IBAMA" and por_rotulo["P1"]["properties"]["fonte"] == "INPE PRODES"


def test_camadas_recortam_a_area_protegida_ao_entorno_do_car(tmp_path):
    from pipeline.fontes import funai_terras_indigenas

    grande = shapely.box(X0 - 1, Y0 - 1, X0 + 1, Y0 + 0.005)  # muito maior que o CAR
    ti = pd.DataFrame([{"terrai_codigo": "1", "nome": "TI Teste", "etnia": "X", "fase": "Regularizada",
                        "modalidade": "T", "uf": "MG", "municipio": "Patrocínio", "superficie_ha": 1e6,
                        "data_atualizacao": pd.Timestamp("2025-01-01"), "geometria_wkt": grande.wkt,
                        "alertas": None}], columns=funai_terras_indigenas.COLUNAS_SAIDA)
    ficha = prediagnostico.diagnosticar(
        car(), embargos(), alertas(), lista_suja(), prodes(), None, ultimo_ano_prodes=2025,
        protegidas={"terra_indigena": (ti, None), "quilombola": (pd.DataFrame(columns=["geometria_wkt"]), None),
                    "unidade_conservacao": (pd.DataFrame(columns=["geometria_wkt"]), None)})
    ficha = {"consulta": {"gerado_em": "2026-10-30 10:00:00"}, **ficha, "procedencia": []}
    t1 = next(f for f in json.loads(prediagnostico.camadas_geojson(ficha))["features"]
              if f["properties"]["rotulo"] == "T1")
    xs, ys = zip(*t1["geometry"]["coordinates"][0])
    assert min(xs) > X0 - 0.01 and min(ys) > Y0 - 0.01 and t1["properties"]["camada"] == "terra_indigena"


def test_camadas_simplificam_so_quando_passam_de_1_mb(monkeypatch):
    t = np.linspace(0, 2 * np.pi, 20000)
    detalhado = shapely.Polygon(np.c_[X0 + 0.005 + 0.004 * np.cos(t), Y0 + 0.005 + 0.004 * np.sin(t)])
    ficha = diagnosticar(emb=embargos(("dentro", detalhado, None, None)))
    inteiro = prediagnostico.camadas_geojson(ficha)
    assert len(inteiro.encode()) > 100_000
    monkeypatch.setattr(prediagnostico, "LIMITE_CAMADAS_BYTES", 60_000)
    simplificado = prediagnostico.camadas_geojson(ficha)
    assert len(simplificado.encode()) <= 60_000 < len(inteiro.encode())
    monkeypatch.setattr(prediagnostico, "LIMITE_CAMADAS_BYTES", 10**9)
    assert prediagnostico.camadas_geojson(ficha) == inteiro  # abaixo do limite, a geometria não é mexida


def test_camada_sem_fonte_ou_sem_poligono_vai_para_nao_verificadas_e_nao_vira_sem_ocorrencia(tmp_path):
    ficha = diagnosticar(emb=embargos(("sem_poligono", None, (Y0 + 0.005, X0 + 0.005), None)))
    ficha["criterios"] = [dict(c, situacao="inconclusivo", evidencia="Fonte não carregada (ref.terra_indigena)")
                          if c["chave"] == "terra_indigena" else c for c in ficha["criterios"]]
    ficha["evidencias"].pop("prodes")  # camada ausente da ficha
    colecao = json.loads(prediagnostico.camadas_geojson({"consulta": {}, **ficha}))
    nao = colecao["camadas_nao_verificadas"]
    assert {"camada": "terra_indigena", "motivo": "Fonte não carregada (ref.terra_indigena)"} in nao
    assert any(n["camada"] == "prodes" and "ausente" in n["motivo"] for n in nao)
    assert any(n["camada"] == "embargo" and n["rotulo"] == "E1" and "sem polígono" in n["motivo"] for n in nao)
    ok = json.loads(prediagnostico.camadas_geojson({"consulta": {}, **diagnosticar()}))
    assert ok["camadas_nao_verificadas"] == []  # tudo verificado e vazio: lista vazia, campo sempre presente


def test_geometria_invalida_nas_camadas_nao_derruba_a_ficha(tmp_path, caplog, monkeypatch):
    def quebrar(ficha, tolerancia):
        raise shapely.errors.GEOSException("ParseException: POLYGON((0 0, WKT-RUIM")

    monkeypatch.setattr(prediagnostico, "_feicoes_camadas", quebrar)
    ficha = _ficha_para_escrever(alt=alertas(("a1", DENTRO, "2025-08-28")))
    with caplog.at_level("WARNING"):
        caminhos = prediagnostico.escrever(ficha, tmp_path)
    assert set(caminhos) == {"json", "md", "html"} and all(c.exists() for c in caminhos.values())
    assert not list(tmp_path.glob("*.geojson")) and "WKT-RUIM" not in caplog.text
    assert "Camadas da ficha não gravadas" in caplog.text


def test_nome_do_arquivo_sanitizado_nunca_sai_da_pasta_de_saida(tmp_path):
    saida = tmp_path / "saida"
    ficha = _ficha_para_escrever("../../fora/MG-1", alt=alertas(("a1", DENTRO, "2025-08-28")))
    caminhos = prediagnostico.escrever(ficha, saida)
    assert {c.parent for c in caminhos.values()} == {saida}
    assert sorted(p.name for p in saida.iterdir()) == sorted(
        [f"fora_MG-1.{e}" for e in ("json", "md", "html")] + ["fora_MG-1.camadas.geojson"])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["saida"]  # nada em tmp_path nem acima
    codigo = "MG-3148103-" + "A" * 32  # código normal: o mesmo nome de antes
    assert prediagnostico.escrever(_ficha_para_escrever(codigo), saida)["camadas"].name == f"{codigo}.camadas.geojson"
    assert prediagnostico.escrever(_ficha_para_escrever(codigo), saida)["html"].name == f"{codigo}.html"


def test_ficha_sem_imovel_localizado_nao_grava_camadas(tmp_path):
    ficha = {"consulta": {"gerado_em": "2026-10-30 10:00:00", "documento_informado": False},
             **prediagnostico.ficha_inconclusiva("Coordenada fora do território"), "procedencia": []}
    caminhos = prediagnostico.escrever(ficha, tmp_path)
    assert set(caminhos) == {"json", "md", "html"} and not list(tmp_path.glob("*.geojson"))


def test_html_mostra_como_o_resultado_se_formou_e_a_linha_do_tempo():
    from pipeline import ficha_html

    ficha = diagnosticar(emb=embargos(("dentro", DENTRO, None, None)), alt=alertas(("a1", DENTRO, "2025-08-28")))
    ficha = {"consulta": {"gerado_em": "2026-10-30 10:00:00", "documento_informado": False,
                          "prodes": {"origem": "lote", "ultimo_ano_do_imovel": 2025, "verificado_em": "2026-10-30"}},
             **ficha, "procedencia": []}
    html = ficha_html.renderizar(ficha)
    assert "Como o resultado foi formado" in html and "1 pendência basta → com pendência" in html
    assert html.count(' vale">') == 1 and '<span class="pend vale">1 pendência basta' in html  # só a regra aplicada
    assert "Linha do tempo" in html and "PRODES publicado até 31/07/2025" in html and ">A1<" in html


def test_indice_confere_esperado_com_obtido():
    from pipeline import ficha_html

    ficha = {"consulta": {"gerado_em": "2026-10-30 10:00:00"}, **diagnosticar(alt=alertas(("a1", DENTRO,
                                                                                             "2025-08-28")))}
    certo = {"caso": "certo", "esperado": {"desmatamento": "indício", "resultado": "com indício"}}
    errado = {"caso": "errado", "esperado": {"desmatamento": "pendência"}}
    html = ficha_html.indice([(ficha, certo, "a.html"), (ficha, errado, "b.html")])
    assert "<b>1 de 2</b>" in html and "✕ desmatamento" in html
