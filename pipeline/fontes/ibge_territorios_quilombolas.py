"""Fonte em lote: territórios quilombolas oficialmente delimitados (IBGE, Censo 2022), para o critério 6 do AB+S.

O AB+S consulta o INCRA. O acervo fundiário do INCRA, que publicava as áreas quilombolas, não tem endereço público
desde outubro de 2026 (certificacao.incra.gov.br e acervofundiario.incra.gov.br sem resolução de DNS em 30/10/2026,
e o acervo passou a exigir login gov.br). O IBGE publica os territórios com alguma delimitação formal no INCRA ou em
órgão fundiário estadual ou municipal em 31/07/2022: é a base aberta mais próxima, parada nessa data (ADR 0014).
"""

import pandas as pd
import shapely

from pipeline import config, download, vetor
from pipeline.validacao import Marcas, ResultadoFonte

ARQ_SAIDA = config.DADOS_PROCESSADOS / "ibge_territorios_quilombolas.parquet"
BASE_SHAPEFILE = "Territorios_Quilombolas_oficialmente_delimitados_181023"
COLUNAS_SAIDA = ["cod_tq", "nome", "situacao", "uf", "data_referencia", "geometria_wkt", "alertas"]


def transformar(camada: tuple, resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    registros, geoms, prj, trocados = camada
    vetor.validar_crs_sirgas("TQ", prj, resultado)
    resultado.validar("TQ_TEXTO_TRUNCADO", "Texto do DBF cortado no meio de um caractere UTF-8", "correcao",
                      "lido com o caractere de substituição", trocados, len(registros))
    df = pd.DataFrame(registros)
    resultado.entrada["registros_recebidos"] = len(df)
    resultado.transformar("Leitura do shapefile; coordenada Z descartada (polígonos 2D)")
    geoms, fica = vetor.validar_geometrias("TQ", geoms, resultado)
    duplicado = df["COD_TQ"].duplicated(keep="first") & fica
    resultado.validar("TQ_CODIGO_DUPLICADO", "COD_TQ repetido", "descarte", "registro vai para descartados",
                      duplicado, len(df))
    fica &= ~duplicado
    descartados = df[~fica].assign(motivo="geometria ausente ou código repetido")
    df, geoms = df[fica].reset_index(drop=True), geoms[fica.to_numpy()]
    n = len(df)
    marcas = Marcas(df.index)
    situacao_fora = ~df["STATUS"].isin(config.QUILOMBOLAS_SITUACOES)
    resultado.validar("TQ_SITUACAO_FORA_DO_DOMINIO", f"STATUS fora de {', '.join(config.QUILOMBOLAS_SITUACOES)}",
                      "alerta", "mantido; tratado como território delimitado", situacao_fora, n)
    marcas.marcar("SITUACAO_FORA_DO_DOMINIO", situacao_fora)
    uf_invalida = ~df["SG_UF"].isin(config.UFS)
    resultado.validar("TQ_UF_INVALIDA", "SG_UF que não é sigla de UF", "alerta", "mantido", uf_invalida, n)
    marcas.marcar("UF_INVALIDA", uf_invalida)
    saida = pd.DataFrame({
        "cod_tq": df["COD_TQ"].astype("string"), "nome": df["NOM_TQ"].astype("string"),
        "situacao": df["STATUS"].astype("string"), "uf": df["SG_UF"].astype("string"),
        "data_referencia": pd.Timestamp(config.QUILOMBOLAS_DATA_REFERENCIA),
        "geometria_wkt": shapely.to_wkt(geoms, rounding_precision=-1) if n else [], "alertas": marcas.coluna()})
    return saida[COLUNAS_SAIDA], descartados


def executar(atualizar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("ibge_territorios_quilombolas", "tabular geoespacial (shapefile)")
    destino = config.DADOS_BRUTOS / "ibge_territorios_quilombolas.zip"
    resultado.entrada = download.baixar(config.URL_IBGE_QUILOMBOLAS, destino, atualizar)
    resultado.entrada["data_referencia"] = config.QUILOMBOLAS_DATA_REFERENCIA
    saida, descartados = transformar(vetor.ler_shapefile_zip(destino, BASE_SHAPEFILE), resultado)
    config.DADOS_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    saida.to_parquet(ARQ_SAIDA, index=False)
    resultado.saida = {"arquivo": str(ARQ_SAIDA.relative_to(config.RAIZ)), "registros_produzidos": len(saida),
                       "registros_descartados": len(descartados),
                       "registros_com_alerta": int((saida["alertas"] != "").sum()),
                       "por_situacao": saida["situacao"].value_counts().to_dict(), "colunas": COLUNAS_SAIDA}
    resultado.status = "ok"
    return resultado
