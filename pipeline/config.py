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
