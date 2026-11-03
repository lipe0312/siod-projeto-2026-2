"""Fonte em lote: unidades de conservação do CNUC/MMA (critério 9 do AB+S), pelo shapefile do portal de dados abertos.

O recurso é escolhido pela API do CKAN (package_show): o shapefile mais recente com endereço em dados.mma.gov.br. O
mais novo pode estar só num link do SharePoint, que não serve para coleta automática (30/10/2026: 2026_07); a
resposta do CKAN traz links pessoais de servidores e fica só em data/raw/.

O zip tem duas camadas: polígonos e pontos (UCs sem limite no CNUC). Ponto não permite medir sobreposição: entra na
tabela com a geometria de ponto e é marcado, para o pré-diagnóstico tratá-lo como indício se cair dentro do imóvel.
"""

import json

import pandas as pd
import shapely

from pipeline import config, download, vetor
from pipeline.armazenamento import lago
from pipeline.validacao import Marcas, ResultadoFonte

COLUNAS_SAIDA = ["cd_cnuc", "nome", "categoria", "grupo", "esfera", "uf", "orgao_gestor", "ano_criacao",
                 "qualidade_poligono", "so_ponto", "geometria_wkt", "alertas"]
GRUPO_PONTO = {"PI": "Proteção Integral", "US": "Uso Sustentável"}


def escolher_recurso(pacote: dict) -> dict:
    """Shapefile mais recente com URL estável (dados.mma.gov.br)."""
    shp = [r for r in pacote["result"]["resources"]
           if "shp" in (r.get("format") or "").lower() and r["url"].startswith("https://dados.mma.gov.br/")]
    if not shp:
        raise RuntimeError("nenhum shapefile do CNUC com endereço em dados.mma.gov.br")
    return max(shp, key=lambda r: r.get("created") or "")


def transformar(poligonos: tuple, pontos: tuple, resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    reg_pol, geo_pol, prj_pol, trocados_pol = poligonos
    reg_pt, geo_pt, prj_pt, _ = pontos
    vetor.validar_crs_sirgas("UC", prj_pol, resultado)
    if reg_pt:
        vetor.validar_crs_sirgas("UC_PONTOS", prj_pt, resultado)
    resultado.validar("UC_TEXTO_TRUNCADO", "Texto do DBF cortado no meio de um caractere UTF-8", "correcao",
                      "lido com o caractere de substituição", trocados_pol, len(reg_pol))
    pol = pd.DataFrame(reg_pol)
    pol = pd.DataFrame({
        "cd_cnuc": pol["cd_cnuc"], "nome": pol["nome_uc"], "categoria": pol["categoria"], "grupo": pol["grupo"],
        "esfera": pol["esfera"], "uf": pol["uf"], "orgao_gestor": pol["org_gestor"],
        "ano_criacao": pd.to_datetime(pol["cria_ano"], format="%d-%m-%Y", errors="coerce").dt.year.astype("Int64"),
        "qualidade_poligono": pol["quali_pol"], "so_ponto": False})
    pt = pd.DataFrame(reg_pt)
    pt = pd.DataFrame({
        "cd_cnuc": pt["codigo_uc"], "nome": pt["nome_uc"], "categoria": pt["categoria"],
        "grupo": pt["grupo"].map(GRUPO_PONTO).fillna(pt["grupo"]), "esfera": pt["esfera"].str.capitalize(),
        "uf": None, "orgao_gestor": pt["org_gestor"].str.strip(),
        "ano_criacao": pd.to_numeric(pt["ano_criaca"], errors="coerce").astype("Int64"),
        "qualidade_poligono": pt["qualidade"], "so_ponto": True})
    df = pd.concat([pol, pt], ignore_index=True)
    geoms = pd.Series(list(geo_pol) + list(geo_pt), dtype=object).to_numpy()
    resultado.entrada["registros_recebidos"] = len(df)
    resultado.entrada["poligonos"], resultado.entrada["pontos"] = len(pol), len(pt)
    resultado.transformar("Camadas de polígonos e de pontos juntas; grupo dos pontos (PI/US) por extenso")

    geoms, fica = vetor.validar_geometrias("UC", geoms, resultado)
    duplicado = df["cd_cnuc"].duplicated(keep="first") & fica
    resultado.validar("UC_CODIGO_DUPLICADO", "cd_cnuc repetido (entre polígonos e pontos)", "descarte",
                      "registro vai para descartados", duplicado, len(df))
    fica &= ~duplicado
    descartados = df[~fica].assign(motivo="geometria ausente ou código repetido")
    df, geoms = df[fica].reset_index(drop=True), geoms[fica.to_numpy()]
    n = len(df)

    marcas = Marcas(df.index)
    grupo_fora = ~df["grupo"].isin(config.UC_GRUPOS)
    resultado.validar("UC_GRUPO_FORA_DO_DOMINIO", f"grupo fora de {', '.join(config.UC_GRUPOS)}", "alerta",
                      "mantida; tratada como proteção integral (pendência)", grupo_fora, n)
    marcas.marcar("GRUPO_FORA_DO_DOMINIO", grupo_fora)
    so_ponto = df["so_ponto"]
    resultado.validar("UC_SO_PONTO", "UC sem limite no CNUC, só com um ponto de localização", "alerta",
                      "mantida; ponto dentro do imóvel é indício", so_ponto, n)
    marcas.marcar("SO_PONTO", so_ponto)
    esquematico = df["qualidade_poligono"].eq(config.UC_POLIGONO_ESQUEMATICO)
    resultado.validar("UC_POLIGONO_ESQUEMATICO", "Polígono é representação esquemática da localização da UC",
                      "alerta", "mantida; sobreposição vira indício", esquematico, n)
    marcas.marcar("POLIGONO_ESQUEMATICO", esquematico)

    df["geometria_wkt"] = shapely.to_wkt(geoms, rounding_precision=-1) if n else []
    df["alertas"] = marcas.coluna()
    return df[COLUNAS_SAIDA], descartados


def executar(atualizar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("mma_unidades_conservacao", "tabular geoespacial (shapefile)")
    pacote_bytes, meta_pacote = download.consultar(config.URL_CKAN_MMA, config.DADOS_BRUTOS / "cnuc" / "package_show.json",
                                                   {"id": config.CNUC_CONJUNTO}, atualizar=atualizar)
    recurso = escolher_recurso(json.loads(pacote_bytes))
    destino = config.DADOS_BRUTOS / "cnuc" / recurso["url"].rsplit("/", 1)[-1]
    resultado.entrada = {"conjunto": config.CNUC_CONJUNTO, "recurso": recurso["name"],
                         "recurso_criado_em": recurso.get("created"), "catalogo_consultado_em_utc":
                         meta_pacote["consultado_em_utc"], **download.baixar(recurso["url"], destino, atualizar)}
    resultado.transformar(f"Recurso escolhido pelo CKAN: o shapefile mais recente em dados.mma.gov.br "
                          f"({recurso['name']})")
    base = destino.stem.removeprefix("shp_")
    saida, descartados = transformar(vetor.ler_shapefile_zip(destino, base),
                                     vetor.ler_shapefile_zip(destino, base + "_pontos"), resultado)
    lago.gravar("ref.unidade_conservacao", saida, resultado)
    resultado.saida.update({"arquivo": lago.relativo(lago.pasta("ref.unidade_conservacao")),
                            "registros_produzidos": len(saida), "registros_descartados": len(descartados),
                            "registros_com_alerta": int((saida["alertas"] != "").sum()),
                            "por_grupo": saida["grupo"].value_counts().to_dict(), "colunas": COLUNAS_SAIDA})
    resultado.status = "ok"
    return resultado
