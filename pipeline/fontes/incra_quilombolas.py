"""Fonte em lote: áreas quilombolas do INCRA (critério 6 do AB+S), pela camada `CMR-PUBLICO:lim_quilombolas_a` que o
GeoServer do CMR/FUNAI republica sem login, e a camada quilombola combinada que o pré-diagnóstico usa.

Por que esta camada (testado em 02/11/2026):
- o acervo fundiário do INCRA segue sem endereço público (certificacao e acervofundiario.incra.gov.br sem DNS, também
  de uma máquina no Brasil);
- o CMR/FUNAI republica a base do INCRA: 446 áreas, com processo, superintendência regional e fase (RTID, portaria,
  decreto, título), cadastradas em 28/10/2026. Só 4 tocam terra indígena: é a base nacional, não um recorte;
- 37 dessas áreas não tocam nenhum território da base do IBGE de 31/07/2022 (22 em fase de RTID, mais recentes).

Camada combinada (ref.territorio_quilombola): todas as áreas do INCRA, mais os territórios do IBGE que não coincidem com nenhuma
delas (menos de LIMIAR_MESMO_TERRITORIO da área coberta pelo INCRA). Cada linha diz a base de onde veio.
"""

import json

import numpy as np
import pandas as pd
import shapely
from shapely.strtree import STRtree

from pipeline import config, download, vetor, wfs
from pipeline.armazenamento import lago
from pipeline.validacao import Marcas, ResultadoFonte

COLUNAS_INCRA = ["id_incra", "nome", "situacao", "uf", "municipio", "processo", "superintendencia", "area_ha",
                 "data_publicacao", "data_cadastro", "geometria_wkt", "alertas"]
COLUNAS_SAIDA = ["codigo", "nome", "situacao", "uf", "base", "data_referencia", "geometria_wkt", "alertas"]
LIMITE = 5000  # o INCRA tem menos de mil áreas quilombolas com polígono
LIMIAR_MESMO_TERRITORIO = 0.5
SEM_FASE = "FASE NÃO INFORMADA"


def transformar(resposta: dict, resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    problema = wfs.problema_estrutural(resposta)
    resultado.validar("QI_ESTRUTURA_RESPOSTA", "Resposta é FeatureCollection com lista de features"
                      + (f" ({problema})" if problema else ""), "erro", "interrompe a fonte", int(bool(problema)), 1)
    resultado.validar("QI_RESPOSTA_INCOMPLETA", "Recebido diferente do numberMatched anunciado pelo serviço", "erro",
                      "interrompe a fonte; repetir", int(wfs.incompleta(resposta)), 1)
    resultado.validar("QI_CRS_INESPERADO", f"CRS diferente de {config.CRS_ESPERADO_WFS} (SIRGAS 2000)", "erro",
                      "interrompe a fonte", int(bool(resposta["features"]) and not wfs.crs_esperado(resposta)), 1)
    feicoes = resposta["features"]
    df = pd.DataFrame([{**(f.get("properties") or {}), "id_feature": f.get("id")} for f in feicoes])
    geoms = pd.Series([shapely.geometry.shape(f["geometry"]) if f.get("geometry") else None for f in feicoes],
                      dtype=object).to_numpy()
    resultado.entrada["registros_recebidos"] = len(df)
    resultado.transformar("Conversão de cada feature GeoJSON em linha: propriedades e geometria")

    geoms, fica = vetor.validar_geometrias("QI", geoms, resultado)
    duplicado = df["id_feature"].duplicated(keep="first") & fica
    resultado.validar("QI_ID_DUPLICADO", "Identificador da feição repetido", "descarte",
                      "registro vai para descartados", duplicado, len(df))
    fica &= ~duplicado
    descartados = df[~fica].assign(motivo="geometria ausente ou identificador repetido")
    df, geoms = df[fica].reset_index(drop=True), geoms[fica.to_numpy()]
    n = len(df)

    marcas = Marcas(df.index)
    fase = df["ds_fase"].astype("string").str.strip().str.upper()
    sem_fase = fase.isna() | (fase == "")
    resultado.validar("QI_FASE_AUSENTE", "ds_fase vazia", "alerta", f"mantida como \"{SEM_FASE}\"; vira indício",
                      sem_fase, n)
    marcas.marcar("FASE_AUSENTE", sem_fase)
    fora = ~sem_fase & ~fase.isin(config.QUILOMBOLAS_INCRA_FASES)
    resultado.validar("QI_FASE_FORA_DO_DOMINIO", f"ds_fase fora de {', '.join(config.QUILOMBOLAS_INCRA_FASES)}",
                      "alerta", "mantida; tratada como área delimitada", fora, n)
    marcas.marcar("FASE_FORA_DO_DOMINIO", fora)
    caixa = fase.notna() & (fase != df["ds_fase"].astype("string").str.strip())
    resultado.validar("QI_FASE_CAIXA_DIFERENTE", "ds_fase fora da caixa alta", "correcao", "normalizada", caixa, n)
    uf_invalida = ~df["sg_uf"].isin(config.UFS)
    resultado.validar("QI_UF_INVALIDA", "sg_uf que não é sigla de UF", "alerta", "mantida", uf_invalida, n)
    marcas.marcar("UF_INVALIDA", uf_invalida)
    sem_processo = df["nu_processo"].isna()
    resultado.validar("QI_PROCESSO_AUSENTE", "Área sem número de processo no INCRA", "alerta", "mantida", sem_processo, n)
    marcas.marcar("PROCESSO_AUSENTE", sem_processo)

    data = lambda c: pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_localize(None) if c in df else pd.NaT
    saida = pd.DataFrame({
        "id_incra": df["id_feature"].astype("string"), "nome": df["no_comunidade"].astype("string"),
        "situacao": fase.fillna(SEM_FASE).replace("", SEM_FASE), "uf": df["sg_uf"].astype("string"),
        "municipio": df["no_municipio"].astype("string"), "processo": df["nu_processo"].astype("string"),
        "superintendencia": df["co_sr"].astype("string"), "area_ha": pd.to_numeric(df["nu_area_ha"], errors="coerce"),
        "data_publicacao": data("dt_publica"), "data_cadastro": data("dt_cadastro"),
        "geometria_wkt": shapely.to_wkt(geoms, rounding_precision=-1) if n else [], "alertas": marcas.coluna()})
    return saida[COLUNAS_INCRA], descartados


def combinar(incra: pd.DataFrame, ibge: pd.DataFrame, resultado: ResultadoFonte) -> pd.DataFrame:
    """INCRA inteiro mais o território do IBGE que o INCRA não cobre (o mesmo território nas duas bases fica uma vez,
    com os dados do INCRA, que são mais novos)."""
    g_incra = shapely.from_wkt(incra["geometria_wkt"].to_numpy())
    g_ibge = shapely.from_wkt(ibge["geometria_wkt"].to_numpy())
    arvore = STRtree(g_incra)
    mesmo = np.zeros(len(g_ibge), dtype=bool)
    for i, g in enumerate(g_ibge):
        vizinhos = arvore.query(g, predicate="intersects")
        if len(vizinhos) and g.area > 0:
            coberta = shapely.intersection(g, shapely.union_all(g_incra[vizinhos])).area / g.area
            mesmo[i] = coberta >= LIMIAR_MESMO_TERRITORIO
    resultado.validar("QUILOMBOLA_NAS_DUAS_BASES", f"Território do IBGE com ao menos {LIMIAR_MESMO_TERRITORIO:.0%} da "
                      "área coberta por área do INCRA", "correcao", "fica a do INCRA", int(mesmo.sum()), len(ibge))
    datas = incra["data_cadastro"].dropna()
    ref_incra = datas.max().normalize() if len(datas) else pd.NaT
    de_incra = pd.DataFrame({"codigo": "INCRA:" + incra["id_incra"], "nome": incra["nome"],
                             "situacao": incra["situacao"], "uf": incra["uf"], "base": "INCRA",
                             "data_referencia": ref_incra, "geometria_wkt": incra["geometria_wkt"],
                             "alertas": incra["alertas"]})
    so_ibge = ibge[~mesmo]
    de_ibge = pd.DataFrame({"codigo": "IBGE:" + so_ibge["cod_tq"], "nome": so_ibge["nome"],
                            "situacao": so_ibge["situacao"], "uf": so_ibge["uf"], "base": "IBGE 2022",
                            "data_referencia": so_ibge["data_referencia"], "geometria_wkt": so_ibge["geometria_wkt"],
                            "alertas": so_ibge["alertas"]})
    resultado.transformar(f"Camada combinada: INCRA inteiro e {len(so_ibge)} território(s) só do IBGE 2022")
    return pd.concat([de_incra, de_ibge], ignore_index=True)[COLUNAS_SAIDA]


def executar(atualizar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("incra_quilombolas", "API (WFS/GeoJSON), republicada pelo CMR/FUNAI")
    destino = config.DADOS_BRUTOS / "incra" / "lim_quilombolas_a.json.gz"
    parametros = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                  "typeNames": config.CAMADA_INCRA_QUILOMBOLAS, "outputFormat": "application/json", "count": LIMITE}
    conteudo, meta = download.consultar(config.URL_WFS_CMR, destino, parametros, atualizar=atualizar)
    if meta["status_http"] != 200:
        raise RuntimeError(f"CMR/FUNAI respondeu HTTP {meta['status_http']}")
    resposta = json.loads(conteudo)
    resultado.entrada = {"servico": config.URL_WFS_CMR, "camada": config.CAMADA_INCRA_QUILOMBOLAS,
                         "arquivo": str(destino.relative_to(config.RAIZ)), "consultado_em_utc": meta["consultado_em_utc"],
                         "sha256": meta["sha256"], "anunciado": resposta.get("numberMatched")}
    resultado.transformar("Uma requisição com count; a camada é a do INCRA, republicada pelo CMR/FUNAI")
    incra, descartados = transformar(resposta, resultado)
    try:
        ibge = lago.ler("ref.quilombola_ibge").drop(columns="carga_id", errors="ignore")
    except lago.TabelaAusente:
        raise RuntimeError("ref.quilombola_ibge ausente: rodar a fonte quilombolas do IBGE antes de combinar") from None
    lago.gravar("ref.quilombola_incra", incra, resultado)
    combinada = combinar(incra, ibge, resultado)
    lago.gravar("ref.territorio_quilombola", combinada, resultado)
    resultado.saida.update({"arquivo": lago.relativo(lago.pasta("ref.quilombola_incra")),
                            "registros_produzidos": len(incra), "registros_descartados": len(descartados),
                            "registros_com_alerta": int((incra["alertas"] != "").sum()),
                            "por_situacao": incra["situacao"].value_counts().to_dict(),
                            "arquivo_combinado": lago.relativo(lago.pasta("ref.territorio_quilombola")),
                            "combinado_por_base": combinada["base"].value_counts().to_dict(),
                            "colunas": COLUNAS_INCRA})
    resultado.status = "ok"
    return resultado
