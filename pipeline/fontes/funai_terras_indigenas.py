"""Fonte em lote: terras indígenas da FUNAI (critério 5 do AB+S), pelo WFS público `Funai:tis_poligonais`.

Particularidades do serviço (testadas em 30/10/2026):
- responde 403 a GetFeature sem `count` e a `resultType=hits`: o pedido vai sempre com `count`, e a contagem
  anunciada é o `numberMatched` da própria resposta;
- não envia o certificado intermediário: a sessão completa a cadeia com o certificado do endereço AIA, com a
  verificação ligada (download.sessao_com_intermediario).
"""

import json

import pandas as pd
import shapely

from pipeline import config, download, vetor, wfs
from pipeline.armazenamento import lago
from pipeline.validacao import Marcas, ResultadoFonte

LIMITE = 5000  # o Brasil tem menos de mil terras indígenas com polígono
COLUNAS_SAIDA = ["terrai_codigo", "nome", "etnia", "fase", "modalidade", "uf", "municipio", "superficie_ha",
                 "data_atualizacao", "geometria_wkt", "alertas"]


def transformar(resposta: dict, resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    problema = wfs.problema_estrutural(resposta)
    resultado.validar("TI_ESTRUTURA_RESPOSTA", "Resposta é FeatureCollection com lista de features"
                      + (f" ({problema})" if problema else ""), "erro", "interrompe a fonte", int(bool(problema)), 1)
    resultado.validar("TI_RESPOSTA_INCOMPLETA", "Recebido diferente do numberMatched anunciado pelo serviço", "erro",
                      "interrompe a fonte; repetir", int(wfs.incompleta(resposta)), 1)
    resultado.validar("TI_CRS_INESPERADO", f"CRS diferente de {config.CRS_ESPERADO_WFS} (SIRGAS 2000)", "erro",
                      "interrompe a fonte", int(bool(resposta["features"]) and not wfs.crs_esperado(resposta)), 1)
    feicoes = resposta["features"]
    df = pd.DataFrame([f.get("properties") or {} for f in feicoes])
    geoms = pd.Series([shapely.geometry.shape(f["geometry"]) if f.get("geometry") else None for f in feicoes],
                      dtype=object).to_numpy()
    resultado.entrada["registros_recebidos"] = len(df)
    resultado.transformar("Conversão de cada feature GeoJSON em linha: propriedades e geometria")

    geoms, fica = vetor.validar_geometrias("TI", geoms, resultado)
    duplicado = df["terrai_codigo"].duplicated(keep="first") & fica
    resultado.validar("TI_CODIGO_DUPLICADO", "terrai_codigo repetido", "descarte", "registro vai para descartados",
                      duplicado, len(df))
    fica &= ~duplicado
    descartados = df[~fica].assign(motivo="geometria ausente ou código repetido")
    df, geoms = df[fica].reset_index(drop=True), geoms[fica.to_numpy()]
    n = len(df)

    marcas = Marcas(df.index)
    fase_fora = ~df["fase_ti"].isin(config.FUNAI_FASES)
    resultado.validar("TI_FASE_FORA_DO_DOMINIO", f"fase_ti fora de {', '.join(config.FUNAI_FASES)}", "alerta",
                      "mantida; tratada como terra indígena delimitada", fase_fora, n)
    marcas.marcar("FASE_FORA_DO_DOMINIO", fase_fora)
    uf_invalida = ~df["uf_sigla"].fillna("").str.split(",").map(
        lambda ufs: bool(ufs) and all(u.strip() in config.UFS for u in ufs))
    resultado.validar("TI_UF_INVALIDA", "uf_sigla vazia ou com sigla que não é UF (a TI pode ter mais de uma UF)",
                      "alerta", "mantida; a UF vem do contorno no cruzamento", uf_invalida, n)
    marcas.marcar("UF_INVALIDA", uf_invalida)
    data = pd.to_datetime(df["data_atualizacao"], format="%d/%m/%Y", errors="coerce")
    sem_data = data.isna()
    resultado.validar("TI_DATA_ATUALIZACAO_AUSENTE", "data_atualizacao vazia ou fora do formato DD/MM/AAAA",
                      "alerta", "mantida; a ficha cita a data da coleta", sem_data, n)
    marcas.marcar("DATA_ATUALIZACAO_AUSENTE", sem_data)

    saida = pd.DataFrame({
        "terrai_codigo": df["terrai_codigo"].astype("string"), "nome": df["terrai_nome"].astype("string"),
        "etnia": df["etnia_nome"].astype("string"), "fase": df["fase_ti"].astype("string"),
        "modalidade": df["modalidade_ti"].astype("string"), "uf": df["uf_sigla"].astype("string"),
        "municipio": df["municipio_nome"].astype("string"),
        "superficie_ha": pd.to_numeric(df["superficie_perimetro_ha"], errors="coerce"), "data_atualizacao": data,
        "geometria_wkt": shapely.to_wkt(geoms, rounding_precision=-1) if n else [], "alertas": marcas.coluna()})
    return saida[COLUNAS_SAIDA], descartados


def executar(atualizar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("funai_terras_indigenas", "API (WFS/GeoJSON)")
    destino = config.DADOS_BRUTOS / "funai" / "tis_poligonais.json.gz"
    sessao = download.sessao_com_intermediario("https://geoserver.funai.gov.br", config.FUNAI_INTERMEDIARIO)
    parametros = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeName": config.CAMADA_FUNAI_TIS,
                  "outputFormat": "application/json", "count": LIMITE}
    conteudo, meta = download.consultar(config.URL_WFS_FUNAI, destino, parametros, sessao, atualizar)
    if meta["status_http"] != 200:
        raise RuntimeError(f"FUNAI respondeu HTTP {meta['status_http']}")
    resposta = json.loads(conteudo)
    resultado.entrada = {"servico": config.URL_WFS_FUNAI, "camada": config.CAMADA_FUNAI_TIS,
                         "arquivo": str(destino.relative_to(config.RAIZ)), "consultado_em_utc": meta["consultado_em_utc"],
                         "sha256": meta["sha256"], "anunciado": resposta.get("numberMatched")}
    resultado.transformar("Uma requisição com count (o serviço recusa pedido sem count); cadeia de certificado "
                          "completada pelo endereço AIA, com verificação")
    saida, descartados = transformar(resposta, resultado)
    lago.gravar("ref.terra_indigena", saida, resultado)
    resultado.saida.update({"arquivo": lago.relativo(lago.pasta("ref.terra_indigena")),
                            "registros_produzidos": len(saida), "registros_descartados": len(descartados),
                            "registros_com_alerta": int((saida["alertas"] != "").sum()),
                            "por_fase": saida["fase"].value_counts().to_dict(), "colunas": COLUNAS_SAIDA})
    resultado.status = "ok"
    return resultado
