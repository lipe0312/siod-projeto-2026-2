"""Plano de ação e "o que falta" da ficha (issue #30): função pura sobre os critérios, sem rede."""

import json

import pandas as pd

from conftest import CPF_VALIDO

from pipeline import carteira, config, ficha_html, plano_de_acao, prediagnostico
from pipeline.prediagnostico import ENCAMINHAMENTO, _criterio


def _ficha(criterios, uf="MG", **extra):
    return {"consulta": {"cod_imovel": f"{uf}-0000000-X", "gerado_em": "2026-11-23 10:00:00",
                         "documento_informado": True},
            "imovel": {"cod_imovel": f"{uf}-0000000-X", "uf": uf},
            "resultado": prediagnostico.resultado_geral(criterios), "criterios": criterios, "evidencias": {},
            "geometria_car": "POLYGON((0 0,1 0,1 1,0 0))",
            "procedencia": [{"fonte": "IBAMA, áreas embargadas (CSV)", "como": "lote", "data": "2026-11-02",
                             "sha256": "abc"}], **extra}


CAR_PENDENTE = _criterio("car", "CAR", 3, "indício", "Pendente", ENCAMINHAMENTO["car_pendente"], "SICAR")
EMBARGO = _criterio("embargo", "Embargo IBAMA", 7, "pendência", "1 embargo(s)", ENCAMINHAMENTO["embargo"], "IBAMA")
DESMATAMENTO = _criterio("desmatamento", "Desmatamento após 31/12/2020 (EUDR)", None, "pendência", "PRODES 2023",
                         ENCAMINHAMENTO["desmatamento"], "INPE DETER e PRODES")
LISTA_SUJA_NV = _criterio("lista_suja", "Lista Suja (trabalho escravo)", 4, "não verificado",
                          "Documento do proprietário não informado", ENCAMINHAMENTO["sem_documento"], "MTE")
TI = _criterio("terra_indigena", "Sobreposição: terras indígenas", 5, "pendência", "TI X",
               ENCAMINHAMENTO["terra_indigena"], "FUNAI")
UC_AUSENTE = prediagnostico.criterio_protegido("unidade_conservacao", None)


def test_ordem_dos_cartoes_credito_e_eudr_primeiro_depois_um_depois_indicio():
    ficha = _ficha([CAR_PENDENTE, TI, DESMATAMENTO, EMBARGO, *prediagnostico._nao_verificados()])
    cartoes = plano_de_acao.plano(ficha)
    assert [c["chave"] for c in cartoes] == ["embargo", "desmatamento", "terra_indigena", "car"]
    assert cartoes[0]["bloqueia"] == {"credito": "sim", "eudr": "sim"}
    assert list(cartoes[1]["bloqueia"].values()).count("sim") == 1
    assert cartoes[-1]["situacao"] == "indício"


def test_cartao_tem_norma_passos_com_quem_e_encaminhamento_preservado():
    cartao = plano_de_acao.plano(_ficha([EMBARGO]))[0]
    assert "MCR, Seção 2-9" in cartao["por_que"] and "art. 2(40)" in cartao["por_que"]
    assert cartao["passos"][0]["acao"] == ENCAMINHAMENTO["embargo"]  # o texto antigo vira o primeiro passo
    assert [p["ordem"] for p in cartao["passos"]] == [1, 2, 3]
    assert {p["quem"] for p in cartao["passos"]} <= {"técnico", "produtor", "órgão"}
    assert cartao["orgao"] == "IBAMA" and cartao["link"].startswith("https://")
    assert cartao["prazo_ou_condicao"] and cartao["link_conferido_em"] == plano_de_acao.CONFERIDO_EM
    assert cartao["fonte"] == "IBAMA" and cartao["data_evidencia"] == "2026-11-02"
    desm = plano_de_acao.plano(_ficha([DESMATAMENTO]))[0]
    assert "art. 3" in desm["por_que"] and "art. 2(13)" in desm["por_que"]


def test_orgao_por_uf_cobre_as_ufs_da_demonstracao():
    ufs = {cod[:2] for cod in config.CARS_DEMONSTRACAO}
    assert ufs <= set(plano_de_acao.ORGAOS_UF)
    for uf in ufs:
        cartao = plano_de_acao.plano(_ficha([CAR_PENDENTE], uf=uf))[0]
        assert cartao["orgao"] == plano_de_acao.ORGAOS_UF[uf][0]
        assert cartao["link"] == plano_de_acao.ORGAOS_UF[uf][1]


def test_uf_fora_da_tabela_cai_no_orgao_estadual_e_no_sicar():
    cartao = plano_de_acao.plano(_ficha([CAR_PENDENTE], uf="AC"))[0]
    assert cartao["orgao"].startswith("órgão ambiental estadual")
    assert cartao["link"] == plano_de_acao.SICAR
    assert plano_de_acao.orgao_estadual(None) == {"orgao": "órgão ambiental estadual", "link": plano_de_acao.SICAR}


def test_nao_verificado_e_inconclusivo_nunca_entram_no_plano_e_vao_para_o_que_falta():
    nv = prediagnostico._nao_verificados()
    ficha = _ficha([LISTA_SUJA_NV, UC_AUSENTE, *nv])
    assert plano_de_acao.plano(ficha) == []
    falta = plano_de_acao.o_que_falta(ficha)
    cobertos = [n for i in falta for n in i["criterios"]]
    for c in [LISTA_SUJA_NV, UC_AUSENTE, *nv]:
        assert c["criterio"] in cobertos
    abs_ = next(i for i in falta if "AgroBrasil" in i["entrada"])
    assert abs_["destrava"].startswith("critérios 1, 2 e 8") and abs_["quem"] == "produtor"
    doc = next(i for i in falta if i["entrada"].startswith("Documento"))
    assert "Lista Suja" in doc["destrava"] and "embargo" in doc["destrava"]
    assert all(i["quem"] and i["onde"] for i in falta)


def test_ficha_sem_localizacao_pede_a_localizacao_para_tudo():
    ficha = {**prediagnostico.ficha_inconclusiva("CAR não localizado"), "consulta": {"gerado_em": "x"},
             "procedencia": []}
    falta = plano_de_acao.o_que_falta(ficha)
    assert falta[0]["destrava"] == "todos os critérios" and "CAR" in falta[0]["entrada"]
    assert not any("Área de produção" in i["entrada"] for i in falta)  # sem imóvel, não há talhão a pedir


def test_area_de_producao_falta_so_quando_nao_foi_usada():
    sem = plano_de_acao.o_que_falta(_ficha([EMBARGO]))
    assert any("Área de produção" in i["entrada"] for i in sem)
    com = plano_de_acao.o_que_falta(_ficha([EMBARGO], area_producao={"usada": True}))
    assert not any("Área de produção" in i["entrada"] for i in com)


def test_gado_acrescenta_item_fixo_sem_mudar_situacao():
    criterios = [EMBARGO, *prediagnostico._nao_verificados()]
    ficha = _ficha(criterios)
    antes = json.dumps(ficha["criterios"], sort_keys=True)
    item = "Fornecedores indiretos e trânsito animal (GTA) não verificados"
    for commodity in ("gado", "Bovinos de corte", "carne bovina"):
        assert item in [i["entrada"] for i in plano_de_acao.o_que_falta(ficha, commodity)]
    for commodity in (None, "café", "soja"):
        assert item not in [i["entrada"] for i in plano_de_acao.o_que_falta(ficha, commodity)]
    pela_consulta = {**ficha, "consulta": {**ficha["consulta"], "commodity": "gado"}}  # --commodity da linha de comando
    assert item in [i["entrada"] for i in plano_de_acao.montar(pela_consulta)["o_que_falta"]]
    assert json.dumps(ficha["criterios"], sort_keys=True) == antes
    assert ficha["resultado"] == prediagnostico.resultado_geral(criterios)


def test_json_markdown_e_html_trazem_os_dois_blocos_separados():
    ficha = _ficha([EMBARGO, LISTA_SUJA_NV])
    dados = prediagnostico.para_json(ficha, "gado")
    assert dados["plano_de_acao"][0]["chave"] == "embargo"
    assert any("GTA" in i["entrada"] for i in dados["o_que_falta"])
    assert [c["situacao"] for c in dados["criterios"]] == ["pendência", "não verificado"]
    md = prediagnostico.para_markdown({**ficha, "imovel": {**ficha["imovel"], "municipio": None}})
    assert md.index("## Plano de ação") < md.index("## O que falta para fechar o diagnóstico")
    html = ficha_html.renderizar({**prediagnostico.ficha_inconclusiva("CAR não localizado"),
                                  "consulta": {"gerado_em": "2026-11-23 10:00:00", "documento_informado": False},
                                  "procedencia": []})
    assert "<h2>Plano de ação</h2>" in html and "<h2>O que falta para fechar o diagnóstico</h2>" in html
    for texto in (md, json.dumps(dados, ensure_ascii=False, default=str), html):
        assert CPF_VALIDO not in texto and "11144477735" not in texto
    blocos = json.dumps({k: dados[k] for k in ("plano_de_acao", "o_que_falta")}, ensure_ascii=False)
    novos = (blocos, md.split("## Plano de ação")[1].split("## Procedência")[0],
             html.split("<h2>Plano de ação</h2>")[1].split("<h2>Critérios</h2>")[0])
    for texto in novos:  # o plano nunca diz "conforme"
        assert "conforme" not in texto.replace("conformidade", "")


def test_carteira_com_linha_de_gado_traz_o_item_gta_na_ficha(tmp_path):
    from test_carteira import ficha_falsa

    df = pd.DataFrame([{"id_produtor": "A", "cod_car": "MG-GADO", "documento": CPF_VALIDO, "commodity": "gado de corte"},
                       {"id_produtor": "B", "cod_car": "MG-CAFE", "documento": None, "commodity": "café"}])
    fichas = {}

    def consultar(cod, *a, **k):
        ficha = ficha_falsa()
        ficha["imovel"] = {**ficha["imovel"], "cod_imovel": cod}
        fichas[cod] = ficha
        return ficha

    carteira.processar(df, tmp_path, consultar=consultar)
    gta = "Fornecedores indiretos e trânsito animal (GTA) não verificados"
    gado = json.loads((tmp_path / "fichas" / "MG-GADO.json").read_text(encoding="utf-8"))
    cafe = json.loads((tmp_path / "fichas" / "MG-CAFE.json").read_text(encoding="utf-8"))
    assert gta in [i["entrada"] for i in gado["o_que_falta"]]
    assert gta not in [i["entrada"] for i in cafe["o_que_falta"]]
    assert "GTA" in (tmp_path / "fichas" / "MG-GADO.html").read_text(encoding="utf-8")
    for arquivo in (tmp_path / "fichas").iterdir():
        assert CPF_VALIDO not in arquivo.read_text(encoding="utf-8")


def test_gado_por_palavra_inteira_e_markdown_e_link_seguros():
    assert plano_de_acao.eh_gado("Boi gordo") and plano_de_acao.eh_gado("bovinos")
    assert not plano_de_acao.eh_gado("boião") and not plano_de_acao.eh_gado("café") and not plano_de_acao.eh_gado(None)
    assert plano_de_acao.link_seguro("javascript:alert(1)") is None
    assert plano_de_acao.link_seguro("https://www.car.gov.br/") == "https://www.car.gov.br/"
    linhas = plano_de_acao.markdown({"plano_de_acao": [], "o_que_falta": [
        {"entrada": "a | b\nc", "destrava": "x", "quem": "técnico", "onde": "y", "link": "javascript:alert(1)"}]})
    ultima = linhas[-1]
    assert "a \\| b c" in ultima and "javascript" not in ultima and ultima.count(" | ") == 3
