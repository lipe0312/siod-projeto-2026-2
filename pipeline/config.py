"""Caminhos, endereços das fontes e constantes de domínio usadas pelo pipeline."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS_BRUTOS = RAIZ / "data" / "raw"
DADOS_PROCESSADOS = RAIZ / "data" / "processed"
LOGS = RAIZ / "data" / "logs"
# Lago: dado tratado por esquema e tabela, com histórico (ADR 0017); contratos de cada tabela em contratos/.
LAGO = RAIZ / "data" / "lago"
CONTRATOS = RAIZ / "contratos"
# Arquivos intermediários de uma fonte (peças antes da partição final); não são lidos por mais ninguém.
TRABALHO = RAIZ / "data" / "trabalho"
# Saídas para pessoas (HTML e Markdown das fichas e das carteiras).
SAIDAS = RAIZ / "data" / "saidas"

CHAVE_ENV = "SIOD_CHAVE_PSEUDONIMIZACAO"
CHAVE_ARQUIVO = RAIZ / "data" / "chave_pseudonimizacao"

USER_AGENT = "siod-projeto-2026-2 (pipeline academico, PGCOMP/UFBA)"

URL_IBAMA_EMBARGOS = "https://servicos.ibama.gov.br/ctf/publico/areasembargadas/arquivos/areas_embargadas.csv"
# Desde 02/11/2026 o CSV acima responde 403. A fonte passa a ser o termo de embargo do Portal de Dados Abertos do IBAMA
# (CKAN, conjunto fiscalizacao-termo-de-embargo), atualizado todo dia: traz também os termos cancelados e desembargados,
# que o CSV antigo já tirava.
URL_IBAMA_TERMO_EMBARGO = ("https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/TERMOS_DE_EMBARGO/"
                           "TERMO_EMBARGO/termo_de_embargo.csv")
URL_LISTA_SUJA = (
    "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/"
    "areas-de-atuacao/cadastro_de_empregadores.pdf"
)
URL_IBGE_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
URL_WFS_INPE = "https://terrabrasilis.dpi.inpe.br/geoserver/{workspace}/ows"

# Camadas DETER consultadas. Nas duas, cada feature é o trecho de um alerta dentro de um município.
CAMADAS_DETER = {
    "amazonia": {"workspace": "deter-amz", "tipo": "deter-amz:deter_amz"},
    "cerrado": {"workspace": "deter-cerrado-nb", "tipo": "deter-cerrado-nb:deter_cerrado"},
}
CLASSES_DESMATAMENTO = ("DESMATAMENTO_CR", "DESMATAMENTO_VEG")
# DETER do Pantanal (desde 08/2023): só na área de download do TerraBrasilis, em shapefile atualizado todo dia; o WFS
# não tem a camada. As classes de supressão equivalem às de desmatamento da Amazônia e do Cerrado (corte raso e com
# vegetação); queimada e mineração ficam fora, como lá (ADR 0015).
DETER_ARQUIVOS = {
    "pantanal": {"url": "https://terrabrasilis.dpi.inpe.br/file-delivery/download/deter-pantanal/shape",
                 "arquivo": "deter-pantanal-public.zip", "base_shapefile": "deter-public",
                 "classes": {"supressão com solo exposto": "DESMATAMENTO_CR",
                             "supressão com vegetação": "DESMATAMENTO_VEG"}},
}
BIOMAS_COM_DETER = frozenset(CAMADAS_DETER) | frozenset(DETER_ARQUIVOS)
DETER_DESDE_PADRAO = "2021-01-01"
# Cada mês é pedido em uma única requisição; o maior mês observado tem menos de 9 mil alertas.
DETER_LIMITE_POR_REQUISICAO = 50000
CRS_ESPERADO_DETER = "EPSG::4674"  # SIRGAS 2000

# Data de corte da EUDR: produção em área sem desmatamento após 31/12/2020.
DATA_CORTE_EUDR = "2020-12-31"

# Retângulo que envolve o território brasileiro, incluindo ilhas oceânicas.
LIMITES_BRASIL = {"lat_min": -34.0, "lat_max": 5.5, "lon_min": -74.1, "lon_max": -28.5}

UFS = frozenset(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)

# Prefixo de 2 dígitos do código IBGE do município -> sigla da UF.
CODIGO_UF_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI",
    "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

# Referência territorial (pipeline/territorio.py): contorno das UFs (IBGE) e dos biomas (INPE). A UF de um ponto, de
# um polígono PRODES ou de um imóvel vem do contorno, não de um campo de texto da fonte.
URL_IBGE_MALHA_UFS = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
                      "?formato=application/vnd.geo%2Bjson&intrarregiao=UF&qualidade=intermediaria")
URL_INPE_BIOMAS = ("https://terrabrasilis.dpi.inpe.br/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature"
                   "&typeName=prodes-brasil-nb:biomas_brasil&outputFormat=application/json")
# Nome do bioma no INPE -> chave usada no projeto (a mesma de CAMADAS_PRODES).
BIOMAS_INPE = {"Amazônia": "amazonia", "Caatinga": "caatinga", "Cerrado": "cerrado", "Mata Atlântica": "mata_atlantica",
               "Pampa": "pampa", "Pantanal": "pantanal"}

# Nome da UF por extenso (como o PRODES Cerrado grava o campo `state`) -> sigla.
NOMES_UF = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAZONAS": "AM", "AMAPA": "AP", "BAHIA": "BA", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA", "MINAS GERAIS": "MG",
    "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT", "PARA": "PA", "PARAIBA": "PB", "PERNAMBUCO": "PE", "PIAUI": "PI",
    "PARANA": "PR", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN", "RONDONIA": "RO", "RORAIMA": "RR",
    "RIO GRANDE DO SUL": "RS", "SANTA CATARINA": "SC", "SERGIPE": "SE", "SAO PAULO": "SP", "TOCANTINS": "TO",
}

# ---------------------------------------------------------------------------------------------------------------
# Fontes consultadas sob demanda (Atividade 03). Não entram na execução em lote: cada consulta grava a resposta
# bruta em data/raw/<fonte>/ com um .meta.json e devolve o DataFrame tratado e o ResultadoFonte.
# ---------------------------------------------------------------------------------------------------------------

# Ordem dos eixos nos filtros espaciais do CQL (BBOX e POINT sem SRS) nos WFS 2.0 em EPSG:4674 (SICAR e
# TerraBrasilis): latitude antes de longitude. Na ordem trocada o serviço devolve zero feições, sem erro.
# A resposta GeoJSON vem em (longitude, latitude).
ORDEM_EIXOS_FILTRO = ("lat", "lon")
CRS_ESPERADO_WFS = "EPSG::4674"  # SIRGAS 2000, o mesmo do DETER
PAUSA_ENTRE_CONSULTAS_S = 0.5

# SICAR: uma camada por UF. O servidor só aceita TLS antigo (ver pipeline/fontes/sicar.py).
URL_WFS_SICAR = "https://geoserver.car.gov.br/geoserver/sicar/wfs"
CAMADA_SICAR = "sicar:sicar_imoveis_{uf}"
STATUS_CAR = frozenset({"AT", "PE", "SU", "CA"})
URL_MALHA_MUNICIPIO = ("https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{cod}"
                       "?formato=application/vnd.geo%2Bjson&qualidade=maxima")

# Recorte da Atividade 03: os 10 maiores produtores de café de MG na PAM/IBGE 2025 (tabela 1613, café em grão).
MUNICIPIOS_CAFE_MG = {
    "3148103": "Patrocínio", "3139409": "Manhuaçu", "3143104": "Monte Carmelo", "3129707": "Ibiraci",
    "3111606": "Campos Gerais", "3169406": "Três Pontas", "3166808": "Serra do Salitre", "3103504": "Araguari",
    "3101607": "Alfenas", "3155504": "Rio Paranaíba",
}

# PRODES (incremento anual de desmatamento), um workspace por bioma no TerraBrasilis. `uf_por_extenso` diz como
# cada camada grava a UF (o Cerrado usa o nome por extenso, "MINAS GERAIS"; as demais, a sigla); só a consulta sob
# demanda filtra por esse campo: o lote recorta pelo contorno da UF. Na Amazônia vale a camada do bioma: a da Amazônia
# Legal repete o Cerrado de MT, MA e TO.
CAMADAS_PRODES = {
    "amazonia": {"workspace": "prodes-amazon-nb", "tipo": "prodes-amazon-nb:yearly_deforestation_biome",
                 "uf_por_extenso": False},
    "caatinga": {"workspace": "prodes-caatinga-nb", "tipo": "prodes-caatinga-nb:yearly_deforestation",
                 "uf_por_extenso": False},
    "cerrado": {"workspace": "prodes-cerrado-nb", "tipo": "prodes-cerrado-nb:yearly_deforestation",
                "uf_por_extenso": True},
    "mata_atlantica": {"workspace": "prodes-mata-atlantica-nb", "tipo": "prodes-mata-atlantica-nb:yearly_deforestation",
                       "uf_por_extenso": False},
    "pampa": {"workspace": "prodes-pampa-nb", "tipo": "prodes-pampa-nb:yearly_deforestation", "uf_por_extenso": False},
    "pantanal": {"workspace": "prodes-pantanal-nb", "tipo": "prodes-pantanal-nb:yearly_deforestation",
                 "uf_por_extenso": False},
}
PRODES_LIMITE_POR_REQUISICAO = 50000
# Polígonos por requisição no lote: acima disso o retângulo da UF é dividido em quatro. Respostas grandes (perto do
# limite do servidor) recebem 502 do gateway do TerraBrasilis; com até 8 mil polígonos, respondem.
PRODES_POLIGONOS_POR_PARTE = 8000
# Fração mínima do alerta DETER coberta pelo PRODES para contar como confirmação (ADR 0009).
PRODES_LIMIAR_CONFIRMACAO = 0.10
# PRODES em lote (python -m pipeline --fontes prodes): anos desde PRODES_DESDE, recortados por UF pelo contorno do
# IBGE (ADR 0013). O lote começa com PRODES_UFS_INICIAIS e cresce a cada imóvel de UF nova que entra no
# pré-diagnóstico (inpe_prodes.garantir_uf); as UFs ativas ficam no manifesto. O PRODES sai uma vez por ano, em data que
# o INPE não fixa; por isso a publicação é verificada a cada PRODES_INTERVALO_VERIFICACAO_DIAS: o último ano publicado
# vem da contagem do próprio serviço, não de uma constante.
PRODES_DESDE = 2019
PRODES_UFS_INICIAIS = ("MG",)
PRODES_INTERVALO_VERIFICACAO_DIAS = 30
# Forma padrão do lote desde 02/11/2026 (ADR 0015): o shapefile completo de cada bioma, da área de download do
# TerraBrasilis. O catálogo diz a versão de cada arquivo (sufixo vAAAAMMDD); a verificação mensal compara a versão, e
# só o bioma com versão nova é baixado e tratado de novo. O WFS fica como alternativa (--prodes-pelo-wfs).
URL_TERRABRASILIS = "https://terrabrasilis.dpi.inpe.br"
URL_CATALOGO_TERRABRASILIS = URL_TERRABRASILIS + "/business/api/v1/download/all"

# Sobreposição com áreas protegidas (critérios 5, 6 e 9 do AB+S; ADR 0014). Fontes nacionais, em lote.
URL_WFS_FUNAI = "https://geoserver.funai.gov.br/geoserver/Funai/ows"
CAMADA_FUNAI_TIS = "Funai:tis_poligonais"
# O servidor da FUNAI não envia o certificado intermediário; este é o endereço AIA do próprio certificado (Sectigo).
FUNAI_INTERMEDIARIO = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt"
FUNAI_FASES = ("Em Estudo", "Delimitada", "Declarada", "Homologada", "Regularizada", "Encaminhada RI")
URL_CKAN_MMA = "https://dados.mma.gov.br/api/3/action/package_show"
CNUC_CONJUNTO = "unidadesdeconservacao"
URL_IBGE_QUILOMBOLAS = ("https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Quilombolas_Primeiros_resultados_do_"
                        "universo/Arquivos_geoespaciais_vetoriais_2a_apuracao_20231222/BR_TQ_2a_apuracao_20231222.zip")
QUILOMBOLAS_DATA_REFERENCIA = "2022-07-31"  # data de referência do Censo 2022 para os territórios delimitados
QUILOMBOLAS_SITUACOES = ("ESTUDO TÉCNICO", "RTID", "DELIMITADO", "PORTARIA", "DECRETO", "TITULADO")
# Áreas quilombolas do INCRA, republicadas pelo GeoServer do CMR/FUNAI (o acervo do INCRA está fora do ar; ADR 0016).
URL_WFS_CMR = "https://cmr.funai.gov.br/geoserver/ows"
CAMADA_INCRA_QUILOMBOLAS = "CMR-PUBLICO:lim_quilombolas_a"
QUILOMBOLAS_INCRA_FASES = ("RTID", "PORTARIA", "DECRETO", "TITULADO", "TITULO PARCIAL", "CCDRU", "TITULO ANULADO")
# Situações que viram indício (e não pendência) na sobreposição com o CAR: em estudo, título anulado ou fase em branco.
QUILOMBOLAS_INDICIO = ("ESTUDO TÉCNICO", "TITULO ANULADO", "FASE NÃO INFORMADA")
# Categorias do SNUC (Lei 9.985/2000) em que a sobreposição é indício, não pendência: admitem propriedade privada.
# Proteção integral e as demais de uso sustentável (Floresta, RESEX, RDS, Reserva de Fauna) são de domínio público.
UC_CATEGORIAS_INDICIO = ("Área de Proteção Ambiental", "Área de Relevante Interesse Ecológico",
                         "Reserva Particular do Patrimônio Natural")
UC_GRUPOS = ("Proteção Integral", "Uso Sustentável")
UC_POLIGONO_ESQUEMATICO = "Polígono é uma representação esquemática da localização da UC"

# Pré-diagnóstico: pasta das fichas e CARs da demonstração (6 do café de MG, 1 por bioma no resto do país e 4 com sobreposição a área protegida).
PREDIAGNOSTICO = DADOS_PROCESSADOS / "prediagnostico"
# `esperado`: situação de cada critério verificado e do resultado, conferida na página da demonstração.
_LIMPO = {"car": "sem ocorrência", "embargo": "sem ocorrência", "desmatamento": "sem ocorrência",
          "lista_suja": "sem ocorrência", "terra_indigena": "sem ocorrência", "quilombola": "sem ocorrência",
          "unidade_conservacao": "sem ocorrência"}
CARS_DEMONSTRACAO = {
    "MG-3148103-6245AC9B371A4422B2FA8011CFCC5566": {
        "caso": "Patrocínio: desmatamento após 2020 confirmado pelo PRODES",
        "esperado": {**_LIMPO, "desmatamento": "pendência", "resultado": "com pendência"}},
    "MG-3166808-A726F93D7AFF4A0883BFDEA10D64B1F4": {
        # Até a verificação de 30/10/2026 os 8 alertas (ago./set. 2025) aguardavam o PRODES; o Cerrado 2026 os confirmou.
        "caso": "Serra do Salitre: embargo e 8 alertas DETER de 2025 confirmados pelo PRODES 2026",
        "esperado": {**_LIMPO, "embargo": "pendência", "desmatamento": "pendência", "resultado": "com pendência"}},
    "MG-3148103-A0B17B31272E42CEA4B4C06338C310AF": {
        "caso": "Patrocínio: 3 alertas DETER de ago. 2026, depois do último PRODES (aguardando)",
        "esperado": {**_LIMPO, "desmatamento": "indício", "resultado": "com indício"}},
    "MG-3148103-627F1606409049ABAB34A913E6F37010": {
        "caso": "Patrocínio: embargo e alerta sobre área já suprimida antes",
        "esperado": {**_LIMPO, "embargo": "pendência", "desmatamento": "indício", "resultado": "com pendência"}},
    "MG-3148103-A63D0A01090844CF89342D2544C5847F": {
        "caso": "Patrocínio: CAR com notificação pendente, embargos e alerta confirmado",
        "esperado": {"car": "indício", "embargo": "pendência", "desmatamento": "pendência",
                     "lista_suja": "sem ocorrência", "resultado": "com pendência"}},
    "MG-3148103-5527FB32FFB24B7F850B487724583043": {
        "caso": "Patrocínio: CAR analisado, nada encontrado nas fontes verificadas",
        "esperado": {**_LIMPO, "resultado": "sem pendência nas fontes verificadas"}},
    # Um imóvel por bioma fora de MG (teste de 30/10/2026, docs/evidencias/atividade-04/cobertura-e-persistencia/),
    # conferidos em 01/11/2026, com as 8 UFs no lote do PRODES. O esperado foi escrito depois de conferir a evidência de
    # cada ficha: teste de regressão, não gabarito.
    "PA-1505502-D0CAA14AD3D349D7BCA887F8A15D861E": {
        "caso": "Paragominas (PA), Amazônia: PRODES 2021 (data incerta diante do corte)",
        "esperado": {**_LIMPO, "desmatamento": "indício", "resultado": "com indício"}},
    "MT-5107925-7B98698040DE4C439D7B67CDA0EDDC60": {
        "caso": "Sorriso (MT), Cerrado", "esperado": {**_LIMPO, "resultado": "sem pendência nas fontes verificadas"}},
    "BA-2918407-1689993146174173AC37FC0818E09A85": {
        "caso": "Juazeiro (BA), Caatinga: sem DETER, com aviso de cobertura",
        "esperado": {**_LIMPO, "resultado": "sem pendência nas fontes verificadas"}},
    "RS-4317103-9D7ED9AE1A034779AF519FCDEE36FFB6": {
        "caso": "Rosário do Sul (RS), Pampa: sem DETER, com aviso de cobertura",
        "esperado": {**_LIMPO, "resultado": "sem pendência nas fontes verificadas"}},
    "MS-5003207-620BD0D082F34232BBBFCF2F71811690": {
        "caso": "Corumbá (MS), Pantanal: 342 ha de PRODES após 2020",
        "esperado": {**_LIMPO, "desmatamento": "pendência", "resultado": "com pendência"}},
    "SP-3543402-0381059FD0A5487594C09A887A5D2BC8": {
        "caso": "Ribeirão Preto (SP), Cerrado e Mata Atlântica",
        "esperado": {**_LIMPO, "resultado": "sem pendência nas fontes verificadas"}},
    "PR-4104808-358E3C8A7E234C429B2AA0F3F683B005": {
        "caso": "Cascavel (PR), Mata Atlântica: CAR com notificação",
        "esperado": {**_LIMPO, "car": "indício", "resultado": "com indício"}},
    # Sobreposição com área protegida (critérios 5, 6 e 9 do AB+S; ADR 0014).
    "MS-5006358-72D1C0B44C904850BD9F4A222CA93285": {
        "caso": "Paranhos (MS): CAR dentro da TI Ypoi/Triunfo (declarada) e de APA",
        "esperado": {**_LIMPO, "car": "indício", "terra_indigena": "pendência", "unidade_conservacao": "indício",
                     "resultado": "com pendência"}},
    "PA-1506807-C4579B9B17F64708B80882FC553E51FE": {
        "caso": "Santarém (PA): CAR dentro do território quilombola Saracura",
        "esperado": {**_LIMPO, "car": "indício", "quilombola": "pendência", "resultado": "com pendência"}},
    "MG-3164100-799AE47FE0684CDEB8107378921FB1B7": {
        "caso": "São Pedro do Suaçuí (MG): CAR dentro de APA (indício) e PRODES após 2020",
        "esperado": {**_LIMPO, "desmatamento": "pendência", "unidade_conservacao": "indício",
                     "resultado": "com pendência"}},
    "MG-3160207-F518ED7FF13744F8B6CC0E04B04CC63E": {
        "caso": "Santo Antônio do Itambé (MG): CAR dentro de parque estadual e de APA",
        "esperado": {**_LIMPO, "unidade_conservacao": "pendência", "resultado": "com pendência"}},
}

# AB+S (Agro Brasil + Sustentável): API pública de validação do relatório, consultada por código de autenticidade.
URL_AB_S_PUBLICO = "https://agrobrasil.agricultura.gov.br/abs/backend/api/public"
AB_S_ENDPOINTS = ("qualificacao", "habilitacao", "area-producao")

# Grafia encontrada na base do IBAMA -> grafia padronizada.
BIOMAS = {
    "Amazonia": "Amazônia",
    "Mata Atlantica": "Mata Atlântica",
    "Cerrado": "Cerrado",
    "Caatinga": "Caatinga",
    "Pampa": "Pampa",
    "Pantanal": "Pantanal",
    "Costeiro e Marinho": "Costeiro e Marinho",
}
