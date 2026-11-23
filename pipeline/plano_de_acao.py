"""Plano de ação e "o que falta" da ficha do pré-diagnóstico (issue #30).

Função pura sobre a ficha (`prediagnostico.diagnosticar`/`executar`): não consulta nada e não muda a situação de
nenhum critério.

- `plano_de_acao`: um cartão por critério em "pendência" ou "indício", com o porquê (a regra e a norma), o que
  bloqueia (crédito rural, venda sob a EUDR: "sim", "não" ou "talvez"), os passos em ordem com quem age, o órgão, o
  link oficial, o prazo ou condição quando a norma diz, e a fonte e a data da evidência que gerou o cartão.
- `o_que_falta`: para cada critério "não verificado" ou "inconclusivo", a entrada que destrava, quem traz e onde se
  obtém. "Não verificado" e "inconclusivo" nunca viram cartão de pendência (ADR 0013).

Normas citadas: MCR, Seção 2-9 (Res. CMN 5.193/2024) para o crédito rural; EUDR, Regulamento (UE) 2023/1115, art. 3
(livre de desmatamento e produzido de acordo com a legislação), art. 2(13) (desmatamento), art. 2(40) (legislação
relevante do país de produção) e art. 10(2)(j) (risco de mistura).

Links oficiais conferidos à mão em 23/11/2026 (resposta HTTP 200 na data; ver `CONFERIDO_EM`).
"""

from __future__ import annotations

CONFERIDO_EM = "2026-11-23"

# --- Links oficiais (conferidos em CONFERIDO_EM) ---------------------------------------------------------------------
SICAR = "https://www.car.gov.br/"
IBAMA = "https://www.gov.br/ibama/pt-br/servicos/consultas"
MTE = ("https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/areas-de-atuacao/"
       "cadastro_de_empregadores.pdf")
FUNAI = "https://www.gov.br/funai/pt-br"
INCRA_QUILOMBOLAS = "https://www.gov.br/incra/pt-br/assuntos/governanca-fundiaria/quilombolas"
ICMBIO = "https://www.gov.br/icmbio/pt-br"
CNUC = "https://cnuc.mma.gov.br/powerbi"
MCR = "https://manuais.bcb.gov.br/app/manual/mcr/publico"
EUDR = "https://eur-lex.europa.eu/eli/reg/2023/1115/oj"
MAPA_SUSTENTABILIDADE = "https://www.gov.br/agricultura/pt-br/assuntos/sustentabilidade"
MAPA_TRANSITO_ANIMAL = ("https://www.gov.br/agricultura/pt-br/assuntos/sanidade-animal-e-vegetal/saude-animal/"
                        "transito-animal")

# Órgão ambiental estadual (CAR e autorização de supressão) das UFs dos CARs de demonstração
# (config.CARS_DEMONSTRACAO). Portal oficial de cada órgão, conferido em CONFERIDO_EM.
ORGAOS_UF = {
    "BA": ("INEMA (Instituto do Meio Ambiente e Recursos Hídricos da Bahia)", "https://www.inema.ba.gov.br/"),
    "MG": ("SEMAD-MG (Secretaria de Estado de Meio Ambiente e Desenvolvimento Sustentável)",
           "https://www.meioambiente.mg.gov.br/"),
    "MS": ("IMASUL (Instituto de Meio Ambiente de Mato Grosso do Sul)", "https://www.imasul.ms.gov.br/"),
    "MT": ("SEMA-MT (Secretaria de Estado de Meio Ambiente de Mato Grosso)", "https://www.sema.mt.gov.br/"),
    "PA": ("SEMAS-PA (Secretaria de Estado de Meio Ambiente e Sustentabilidade do Pará)", "https://www.semas.pa.gov.br/"),
    "PR": ("IAT (Instituto Água e Terra do Paraná)", "https://www.iat.pr.gov.br/"),
    "RS": ("SEMA-RS (Secretaria do Meio Ambiente e Infraestrutura do Rio Grande do Sul)", "https://www.sema.rs.gov.br/"),
    "SP": ("SEMIL-SP (Secretaria de Meio Ambiente, Infraestrutura e Logística de São Paulo)",
           "https://www.semil.sp.gov.br/"),
}
ORGAO_PADRAO = ("órgão ambiental estadual", SICAR)

# --- Normas ----------------------------------------------------------------------------------------------------------
NORMA_MCR = "MCR, Seção 2-9 (Res. CMN 5.193/2024)"
NORMA_EUDR_DESMATAMENTO = "EUDR (Reg. (UE) 2023/1115), art. 3 e art. 2(13): livre de desmatamento após 31/12/2020"
NORMA_EUDR_LEGALIDADE = "EUDR (Reg. (UE) 2023/1115), art. 3 e art. 2(40): produzido de acordo com a legislação relevante"
NORMA_EUDR_MISTURA = "EUDR (Reg. (UE) 2023/1115), art. 10(2)(j): risco de mistura com produto de origem desconhecida"
NORMA_ABS = "AgroBrasil+Sustentável (MAPA)"

SIM, NAO, TALVEZ = "sim", "não", "talvez"
PENDENTES = ("pendência", "indício")
FALTANTES = ("não verificado", "inconclusivo")
TERMOS_GADO = ("gado", "bovin", "boi", "carne", "pecuári", "cattle", "bezerr", "novilh")


def orgao_estadual(uf: str | None) -> dict:
    """Órgão ambiental da UF (tabela ORGAOS_UF); UF fora da tabela: "órgão ambiental estadual" + link do SICAR."""
    uf = (uf or "").upper()
    if uf in ORGAOS_UF:
        nome, link = ORGAOS_UF[uf]
    else:
        nome, link = ORGAO_PADRAO
        nome += f" ({uf})" if uf else ""
    return {"orgao": nome, "link": link}


def _passo(quem: str, acao: str, orgao: str | None = None, link: str | None = None) -> dict:
    return {"quem": quem, "acao": acao, "orgao": orgao, "link": link}


def _cartao(tipo: str, criterio: dict, uf: str | None) -> dict:
    """Cartão de um critério pelo tipo de encaminhamento (a chave de prediagnostico.ENCAMINHAMENTO). O texto do
    encaminhamento vira o primeiro passo, sem perda."""
    enc = criterio["encaminhamento"]
    est = orgao_estadual(uf)
    if tipo == "car_irregular":
        return dict(por_que=f"CAR cancelado ou suspenso: o crédito rural é vedado ({NORMA_MCR}); o CAR em situação "
                            f"irregular também pesa na legalidade da produção ({NORMA_EUDR_LEGALIDADE}).",
                    bloqueia={"credito": SIM, "eudr": TALVEZ}, **est, prazo_ou_condicao=None,
                    passos=[_passo("técnico", enc, est["orgao"], est["link"]),
                            _passo("produtor", "Abrir a central do proprietário no SICAR, ver o motivo do "
                                               "cancelamento ou suspensão e apresentar a retificação ou os documentos "
                                               "pedidos.", "SICAR", SICAR),
                            _passo("órgão", "Analisar a retificação e reativar o CAR.", est["orgao"], est["link"])])
    if tipo == "car_pendente":
        return dict(por_que="CAR com pendência ou notificação no SICAR: ainda não impede o crédito, mas notificação "
                            "sem resposta pode levar à suspensão do CAR, que o veda "
                            f"({NORMA_MCR}).",
                    bloqueia={"credito": TALVEZ, "eudr": TALVEZ}, **est, prazo_ou_condicao=None,
                    passos=[_passo("produtor", enc, "SICAR", SICAR),
                            _passo("técnico", "Conferir com o produtor o teor de cada notificação e os documentos "
                                              "que faltam."),
                            _passo("órgão", "Analisar a resposta às notificações.", est["orgao"], est["link"])])
    if tipo == "embargo":
        return dict(por_que=f"Embargo ativo do IBAMA dentro do imóvel: o crédito rural é vedado ({NORMA_MCR}); a "
                            "produção de área embargada não atende à legislação ambiental "
                            f"({NORMA_EUDR_LEGALIDADE}).",
                    bloqueia={"credito": SIM, "eudr": SIM}, orgao="IBAMA", link=IBAMA,
                    prazo_ou_condicao="O desembargo depende da regularização da área.",
                    passos=[_passo("técnico", enc, "IBAMA", IBAMA),
                            _passo("produtor", "Apresentar ao IBAMA a defesa ou o projeto de recuperação da área "
                                               "embargada, como o processo pedir.", "IBAMA", IBAMA),
                            _passo("órgão", "Julgar o processo e, regularizada a área, levantar o embargo.", "IBAMA",
                                   IBAMA)])
    if tipo == "desmatamento":
        return dict(por_que=f"Desmatamento após 31/12/2020 confirmado pelo PRODES: a produção que sai dessa área não "
                            f"atende à EUDR ({NORMA_EUDR_DESMATAMENTO}), mesmo com autorização. Sem autorização de "
                            "supressão, é também infração ambiental, que pode levar a embargo e à vedação do crédito "
                            f"({NORMA_MCR}).",
                    bloqueia={"credito": TALVEZ, "eudr": SIM}, **est,
                    prazo_ou_condicao="Data de corte da EUDR: 31/12/2020.",
                    passos=[_passo("técnico", enc),
                            _passo("produtor", "Apresentar a autorização de supressão de vegetação (ASV) da área, se "
                                               "houver.", est["orgao"], est["link"]),
                            _passo("técnico", "Separar a produção da área desmatada da que vai para comprador sob a "
                                              "EUDR.", "EUDR", EUDR)])
    if tipo == "desmatamento_indicio":
        return dict(por_que=f"Alerta DETER ainda não confirmado pelo PRODES (ou PRODES de 2021, com data incerta diante "
                            f"do corte): se confirmado, a produção da área não atende à EUDR "
                            f"({NORMA_EUDR_DESMATAMENTO}).",
                    bloqueia={"credito": NAO, "eudr": TALVEZ}, **est,
                    prazo_ou_condicao="Data de corte da EUDR: 31/12/2020.",
                    passos=[_passo("técnico", enc),
                            _passo("produtor", "Informar o que houve na área e, se houve supressão, a autorização "
                                               "(ASV).", est["orgao"], est["link"])])
    if tipo == "desmatamento_resto":
        return dict(por_que="Desmatamento fora da área de produção declarada: desmatamento ilegal no imóvel afeta a "
                            f"legalidade da produção ({NORMA_EUDR_LEGALIDADE}) e há risco de mistura "
                            f"({NORMA_EUDR_MISTURA}).",
                    bloqueia={"credito": NAO, "eudr": TALVEZ}, **est, prazo_ou_condicao=None,
                    passos=[_passo("técnico", enc),
                            _passo("produtor", "Apresentar a autorização de supressão (ASV) e dizer o que é produzido "
                                               "na área desmatada.", est["orgao"], est["link"])])
    if tipo == "lista_suja":
        return dict(por_que=f"Empregador no Cadastro de Empregadores (trabalho análogo ao de escravo): o crédito rural "
                            f"é vedado enquanto constar ({NORMA_MCR}); a legislação trabalhista e de direitos humanos "
                            f"entra na legalidade da EUDR ({NORMA_EUDR_LEGALIDADE}).",
                    bloqueia={"credito": SIM, "eudr": TALVEZ}, orgao="MTE", link=MTE,
                    prazo_ou_condicao="Vale enquanto o nome constar no Cadastro.",
                    passos=[_passo("técnico", enc, "MTE", MTE),
                            _passo("produtor", "Apresentar a decisão ou o acordo que tira o nome do Cadastro, se "
                                               "houver.", "MTE", MTE)])
    if tipo in ("terra_indigena", "terra_indigena_estudo"):
        pend = tipo == "terra_indigena"
        return dict(por_que=("Sobreposição com terra indígena: impede a qualificação no " if pend else
                             "Terra indígena em estudo sobre o imóvel: pode impedir a qualificação no ")
                            + f"{NORMA_ABS} e pesa na legalidade da produção ({NORMA_EUDR_LEGALIDADE}).",
                    bloqueia={"credito": TALVEZ, "eudr": TALVEZ}, orgao="FUNAI", link=FUNAI, prazo_ou_condicao=None,
                    passos=[_passo("técnico", enc, "FUNAI", FUNAI),
                            _passo("produtor", "Se a sobreposição for erro de desenho, retificar o CAR.", "SICAR",
                                   SICAR)])
    if tipo in ("quilombola", "quilombola_estudo"):
        pend = tipo == "quilombola"
        return dict(por_que=("Sobreposição com território quilombola delimitado: impede a qualificação no " if pend else
                             "Território quilombola em estudo ou sem fase: pode impedir a qualificação no ")
                            + f"{NORMA_ABS} e pesa na legalidade da produção ({NORMA_EUDR_LEGALIDADE}).",
                    bloqueia={"credito": TALVEZ, "eudr": TALVEZ}, orgao="INCRA", link=INCRA_QUILOMBOLAS,
                    prazo_ou_condicao=None,
                    passos=[_passo("técnico", enc, "INCRA", INCRA_QUILOMBOLAS),
                            _passo("produtor", "Se a sobreposição for erro de desenho, retificar o CAR.", "SICAR",
                                   SICAR)])
    if tipo in ("unidade_conservacao", "unidade_conservacao_indicio"):
        orgao = "ICMBio (UC federal) ou órgão gestor da UC (ver CNUC)"
        return dict(por_que="Sobreposição com unidade de conservação: a atividade produtiva dentro dela depende do "
                            "órgão gestor e do plano de manejo; pesa na legalidade da produção "
                            f"({NORMA_EUDR_LEGALIDADE}).",
                    bloqueia={"credito": TALVEZ, "eudr": TALVEZ}, orgao=orgao, link=CNUC, prazo_ou_condicao=None,
                    passos=[_passo("técnico", enc, "CNUC (MMA)", CNUC),
                            _passo("órgão", "Informar se a atividade é permitida pelo plano de manejo.", orgao,
                                   ICMBIO)])
    # Tipo sem regra própria: o encaminhamento vira o único passo, sem inventar norma.
    return dict(por_que=criterio["evidencia"], bloqueia={"credito": TALVEZ, "eudr": TALVEZ}, orgao=None, link=None,
                prazo_ou_condicao=None, passos=[_passo("técnico", enc)])


def _tipo(criterio: dict) -> str:
    """Chave do ENCAMINHAMENTO que gerou o texto do critério (a ficha guarda o texto, não a chave)."""
    from pipeline.prediagnostico import ENCAMINHAMENTO  # aqui: prediagnostico importa este módulo

    return next((k for k, t in ENCAMINHAMENTO.items() if t == criterio.get("encaminhamento")), criterio["chave"])


def _data_evidencia(ficha: dict, fonte: str) -> str | None:
    """Data da procedência da fonte do critério (primeira palavra da fonte, ex.: "IBAMA", "INPE", "MTE")."""
    prefixo = (fonte or "").split()[0] if fonte else ""
    datas = [p["data"] for p in ficha.get("procedencia") or [] if prefixo and str(p.get("fonte", "")).startswith(prefixo)]
    return datas[0] if datas else (ficha.get("consulta") or {}).get("gerado_em")


def _ordem(cartao: dict) -> tuple:
    """Primeiro o que bloqueia crédito e EUDR, depois só um dos dois, depois o resto da pendência, depois indício."""
    sins = sum(v == SIM for v in cartao["bloqueia"].values())
    talvez = sum(v == TALVEZ for v in cartao["bloqueia"].values())
    indicio = cartao["situacao"] == "indício"
    return (indicio, -sins, -talvez)


def plano(ficha: dict) -> list[dict]:
    uf = (ficha.get("imovel") or {}).get("uf")
    cartoes = []
    for c in ficha["criterios"]:
        if c["situacao"] not in PENDENTES:
            continue
        cartao = _cartao(_tipo(c), c, uf)
        cartao["passos"] = [{"ordem": i, **p} for i, p in enumerate(cartao["passos"], 1)]
        cartoes.append({"chave": c["chave"], "criterio": c["criterio"], "situacao": c["situacao"], **cartao,
                        "evidencia": c["evidencia"], "fonte": c["fonte"], "data_evidencia": _data_evidencia(ficha, c["fonte"]),
                        "link_conferido_em": CONFERIDO_EM})
    return sorted(cartoes, key=_ordem)  # sorted é estável: empate mantém a ordem da ficha


def _faltante(tipo: str, c: dict) -> dict:
    """(entrada que destrava, o que ela destrava, quem traz, onde se obtém, link)."""
    if c["chave"] == "car" and c["situacao"] == "inconclusivo":
        return dict(entrada="Localização do imóvel: código do CAR (recibo de inscrição) ou coordenada da sede",
                    destrava="todos os critérios", quem="produtor",
                    onde="Recibo de inscrição do CAR ou central do proprietário no SICAR", link=SICAR)
    if tipo == "sem_documento":
        return dict(entrada="Documento (CPF ou CNPJ) de cada proprietário, pseudonimizado na consulta",
                    destrava="Lista Suja e embargo do IBAMA por documento", quem="produtor",
                    onde="Documento do proprietário, informado ao técnico na consulta", link=None)
    if tipo == "nao_verificado":
        return dict(entrada="Relatório do AgroBrasil+Sustentável do produtor",
                    destrava="critérios 1, 2 e 8 do AgroBrasil+Sustentável", quem="produtor",
                    onde="Plataforma AgroBrasil+Sustentável (MAPA)", link=MAPA_SUSTENTABILIDADE)
    if tipo == "fonte_ausente":
        return dict(entrada=f"Carga da fonte {c['fonte']} no pipeline", destrava=c["criterio"], quem="técnico",
                    onde=c["evidencia"], link=None)
    if tipo == "fonte_falhou":
        return dict(entrada=f"Resposta da fonte {c['fonte']} (o serviço não respondeu)", destrava=c["criterio"],
                    quem="técnico", onde="Repetir o pré-diagnóstico quando o serviço voltar", link=None)
    return dict(entrada=c["encaminhamento"], destrava=c["criterio"], quem="técnico", onde=c["fonte"], link=None)


def eh_gado(commodity: str | None) -> bool:
    texto = (commodity or "").lower()
    return any(t in texto for t in TERMOS_GADO)


def o_que_falta(ficha: dict, commodity: str | None = None) -> list[dict]:
    """Uma linha por entrada que falta; critérios que a mesma entrada destrava ficam juntos em `criterios`."""
    itens: dict[str, dict] = {}
    for c in ficha["criterios"]:
        if c["situacao"] not in FALTANTES:
            continue
        f = _faltante(_tipo(c), c)
        item = itens.setdefault(f["entrada"], {**f, "criterios": [], "situacoes": []})
        item["criterios"].append(c["criterio"])
        item["situacoes"].append(c["situacao"])
    saida = [{**i, "situacoes": sorted(set(i["situacoes"]))} for i in itens.values()]
    area = ficha.get("area_producao")
    if ficha.get("geometria_car") and not (area and area.get("usada")):
        saida.append(dict(entrada="Área de produção (KML ou GeoJSON do talhão)",
                          destrava="desmatamento no talhão (hoje cruzado com o imóvel inteiro)", quem="produtor",
                          onde="Arquivo do talhão no GPS, no app de campo ou no projeto técnico; coluna area_producao "
                               "da carteira ou --area-producao",
                          link=None, criterios=[], situacoes=[]))
    if eh_gado(commodity):
        saida.append(dict(entrada="Fornecedores indiretos e trânsito animal (GTA) não verificados",
                          destrava="origem dos animais (fornecedores indiretos)", quem="produtor",
                          onde="GTAs de entrada dos animais, emitidas pelo órgão estadual de defesa agropecuária",
                          link=MAPA_TRANSITO_ANIMAL, criterios=[], situacoes=["não verificado"]))
    return saida


def montar(ficha: dict, commodity: str | None = None) -> dict:
    """{"plano_de_acao": [...], "o_que_falta": [...]} da ficha. Não muda a ficha. Sem `commodity`, vale a da
    consulta (ficha["consulta"]["commodity"], gravada pela linha de comando --commodity)."""
    commodity = commodity or (ficha.get("consulta") or {}).get("commodity")
    return {"plano_de_acao": plano(ficha), "o_que_falta": o_que_falta(ficha, commodity)}


# --- Saída em Markdown -----------------------------------------------------------------------------------------------

def _md_link(texto: str | None, link: str | None) -> str:
    return f"[{texto or link}]({link})" if link else (texto or "")


def markdown(blocos: dict) -> list[str]:
    md = ["", "## Plano de ação", ""]
    if not blocos["plano_de_acao"]:
        md.append("Nenhuma pendência nem indício nas fontes verificadas; veja abaixo o que falta para fechar o "
                  "diagnóstico.")
    for n, c in enumerate(blocos["plano_de_acao"], 1):
        b = c["bloqueia"]
        md += [f"### {n}. {c['criterio']} — {c['situacao']}", "",
               f"**Bloqueia:** crédito rural: {b['credito']} · EUDR: {b['eudr']}", "",
               f"**Por quê:** {c['por_que']}", ""]
        for p in c["passos"]:
            onde = f" ({_md_link(p['orgao'], p['link'])})" if p["orgao"] or p["link"] else ""
            md.append(f"{p['ordem']}. **{p['quem']}**: {p['acao']}{onde}")
        md.append("")
        if c["orgao"]:
            md.append(f"**Órgão:** {_md_link(c['orgao'], c['link'])} (link conferido em {c['link_conferido_em']})")
        if c["prazo_ou_condicao"]:
            md.append(f"**Prazo ou condição:** {c['prazo_ou_condicao']}")
        md += [f"**Evidência:** {c['evidencia']} — fonte {c['fonte']}, {c['data_evidencia']}", ""]
    md += ["## O que falta para fechar o diagnóstico", ""]
    if not blocos["o_que_falta"]:
        md.append("Nenhuma entrada faltando.")
        return md
    md += ["| Entrada que falta | Destrava | Quem traz | Onde obter |", "|---|---|---|---|"]
    md += [f"| {i['entrada']} | {i['destrava']} | {i['quem']} | {_md_link(i['onde'], i['link'])} |"
           for i in blocos["o_que_falta"]]
    return md
