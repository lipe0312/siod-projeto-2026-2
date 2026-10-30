"""Caminhos, endereços das fontes e constantes de domínio usadas pelo pipeline."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS_BRUTOS = RAIZ / "data" / "raw"
DADOS_PROCESSADOS = RAIZ / "data" / "processed"
LOGS = RAIZ / "data" / "logs"

CHAVE_ENV = "SIOD_CHAVE_PSEUDONIMIZACAO"
CHAVE_ARQUIVO = RAIZ / "data" / "chave_pseudonimizacao"

USER_AGENT = "siod-projeto-2026-2 (pipeline academico, PGCOMP/UFBA)"

URL_IBAMA_EMBARGOS = "https://servicos.ibama.gov.br/ctf/publico/areasembargadas/arquivos/areas_embargadas.csv"
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
# cada camada grava a UF: o Cerrado usa o nome por extenso ("MINAS GERAIS"), a Mata Atlântica a sigla ("MG").
CAMADAS_PRODES = {
    "cerrado": {"workspace": "prodes-cerrado-nb", "tipo": "prodes-cerrado-nb:yearly_deforestation",
                "uf_por_extenso": True},
    "mata_atlantica": {"workspace": "prodes-mata-atlantica-nb", "tipo": "prodes-mata-atlantica-nb:yearly_deforestation",
                       "uf_por_extenso": False},
}
PRODES_LIMITE_POR_REQUISICAO = 50000
# Fração mínima do alerta DETER coberta pelo PRODES para contar como confirmação (ADR 0009).
PRODES_LIMIAR_CONFIRMACAO = 0.10
# PRODES em lote (python -m pipeline --fontes prodes): anos desde PRODES_DESDE, recortados pelas UFs abaixo (o
# Brasil inteiro passa de 50 mil polígonos por ano e bioma). O PRODES sai uma vez por ano, em data que o INPE não
# fixa; por isso a publicação é verificada a cada PRODES_INTERVALO_VERIFICACAO_DIAS: o último ano publicado vem da
# contagem do próprio serviço, não de uma constante. Imóvel fora dessas UFs é consultado sob demanda.
PRODES_DESDE = 2019
PRODES_UFS_LOTE = ("MG",)
PRODES_INTERVALO_VERIFICACAO_DIAS = 30

# Pré-diagnóstico: pasta das fichas e CARs da demonstração (recorte de café de MG, todos com SICAR em cache).
PREDIAGNOSTICO = DADOS_PROCESSADOS / "prediagnostico"
# `esperado`: situação de cada critério verificado e do resultado, conferida na página da demonstração.
_LIMPO = {"car": "sem ocorrência", "embargo": "sem ocorrência", "desmatamento": "sem ocorrência",
          "lista_suja": "sem ocorrência"}
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
