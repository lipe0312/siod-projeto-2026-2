"""Cruzamento de embargos IBAMA e alertas DETER com o CAR: a que imóvel cada objeto pertence.

Para cada objeto, uma consulta BBOX ao SICAR (sem filtro de município, para pegar CAR registrado no vizinho) e a
interseção calculada localmente. Para cada par (objeto, CAR):
  fracao_objeto = área da interseção / área do objeto  (quanto do embargo ou alerta cai no CAR)
  fracao_car    = área da interseção / área do CAR     (quanto do CAR é atingido)
  largura_m     = 2 x área / perímetro da interseção   (largura média da faixa comum)

Classe do par (limiares tirados dos dados; ver docs/atividade-03/car.md, seção A3):
- principal: o CAR contém ao menos metade do objeto (vale da distribuição em U de fracao_objeto);
- tangente: o objeto quase não entra no CAR (< 5%) e a faixa comum é mais estreita que meio pixel das câmeras do
  DETER (64 m no CBERS-4 e no Amazonia-1, 55 m no CBERS-4A). As duas condições juntas, porque um objeto estreito pode
  ter faixa fina e ainda assim cair em boa parte dentro do CAR;
- parcial: o resto.
"""

import logging

import numpy as np
import pandas as pd
import shapely

from pipeline.fontes import sicar
from pipeline.validacao import ResultadoFonte

log = logging.getLogger("pipeline")

LIMIAR_PRINCIPAL = 0.50
LIMIAR_TANGENTE = 0.05
LIMIAR_LARGURA_M = 30
TOLERANCIA_FRACAO = 1e-6

SITUACOES = ("um CAR principal", "mais de um CAR principal", "só parciais", "só tangentes", "sem CAR localizado")


def objetos_do_recorte(embargos: pd.DataFrame, alertas: pd.DataFrame, cods_municipio) -> pd.DataFrame:
    """Embargos e alertas com geometria nos municípios dados, como saem do pipeline em lote (data/processed)."""
    cods = {str(c) for c in cods_municipio}
    emb = embargos[embargos["cod_municipio"].isin(cods) & embargos["geometria_wkt"].notna()]
    alt = alertas[alertas["cod_municipio"].isin(cods) & alertas["geometria_wkt"].notna()]
    return pd.concat([
        pd.DataFrame({"tipo": "embargo IBAMA", "id_objeto": emb["id_embargo"], "data": emb["data_embargo"],
                      "cod_municipio": emb["cod_municipio"], "municipio": emb["municipio"],
                      "geometria_wkt": emb["geometria_wkt"]}),
        pd.DataFrame({"tipo": "alerta DETER", "id_objeto": alt["id_alerta"], "data": alt["data_imagem"],
                      "cod_municipio": alt["cod_municipio"], "municipio": alt["municipio"],
                      "geometria_wkt": alt["geometria_wkt"]}),
    ], ignore_index=True)


def classificar(fracao_objeto, largura_m) -> np.ndarray:
    fracao_objeto, largura_m = np.asarray(fracao_objeto, dtype=float), np.asarray(largura_m, dtype=float)
    return np.select([fracao_objeto >= LIMIAR_PRINCIPAL,
                      (fracao_objeto < LIMIAR_TANGENTE) & (largura_m < LIMIAR_LARGURA_M)],
                     ["principal", "tangente"], "parcial")


def pares_objeto_car(objeto, cars: pd.DataFrame) -> pd.DataFrame:
    """Frações e classe de cada CAR (DataFrame tratado do SICAR) que toca o polígono `objeto`."""
    colunas = ["cod_imovel", "status_imovel", "condicao", "cod_municipio", "area_car_ha", "inter_ha",
               "fracao_objeto", "fracao_car", "largura_m", "classe"]
    if cars.empty:
        return pd.DataFrame(columns=colunas)
    cg = shapely.make_valid(sicar.geometrias(cars))
    toca = shapely.intersects(cg, objeto)
    cars, cg = cars[toca], cg[toca]
    pc, po = sicar.projetar(cg), sicar.projetar(objeto)
    ig = shapely.intersection(pc, po)
    inter, perimetro = shapely.area(ig), shapely.length(ig)
    area_car = shapely.area(pc)
    pares = pd.DataFrame({
        "cod_imovel": cars["cod_imovel"].to_numpy(), "status_imovel": cars["status_imovel"].to_numpy(),
        "condicao": cars["condicao"].to_numpy(), "cod_municipio": cars["cod_municipio"].to_numpy(),
        "area_car_ha": area_car / 1e4, "inter_ha": inter / 1e4, "fracao_objeto": inter / shapely.area(po),
        "fracao_car": inter / area_car,
        "largura_m": np.divide(2 * inter, perimetro, out=np.zeros_like(inter), where=perimetro > 0)})
    pares["classe"] = classificar(pares["fracao_objeto"], pares["largura_m"])
    return pares[colunas]


def situacao(principal: int, parcial: int, tangente: int) -> str:
    if principal + parcial + tangente == 0:
        return "sem CAR localizado"
    if principal > 1:
        return "mais de um CAR principal"
    if principal == 1:
        return "um CAR principal"
    return "só parciais" if parcial > 0 else "só tangentes"


def atribuir_car(objetos: pd.DataFrame, uf: str = "MG", consultar=sicar.consultar_bbox,
                 atualizar: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, ResultadoFonte]:
    """Para cada objeto (colunas id_objeto e geometria_wkt), consulta o SICAR pelo BBOX e classifica os pares.

    Devolve (objetos com a situação, pares objeto-CAR, ResultadoFonte do cruzamento).
    """
    resultado = ResultadoFonte("cruzamento_car", "cruzamento (SICAR por BBOX)")
    objetos = objetos.reset_index(drop=True).copy()
    geoms = shapely.make_valid(shapely.from_wkt(objetos["geometria_wkt"].to_numpy()))
    objetos["area_ha"] = sicar.area_ha(geoms)
    resultado.entrada = {"objetos": len(objetos), "por_tipo": objetos["tipo"].value_counts().to_dict()
                         if "tipo" in objetos else {}}
    sem_area = objetos["area_ha"] <= 0
    resultado.validar("CRUZ_OBJETO_SEM_AREA", "Objeto cuja geometria não tem área", "descarte",
                      "fora do cruzamento", sem_area, len(objetos))

    todos, consultas = [], []
    for k, geom in enumerate(geoms):
        if sem_area[k]:
            continue
        cars, r = consultar(geom.bounds, uf=uf, atualizar=atualizar)
        consultas.append({"objeto": k, "candidatos": len(cars), **r.entrada["requisicoes"][0]})
        pares = pares_objeto_car(geom, cars)
        todos.append(pares.assign(id_objeto=objetos.at[k, "id_objeto"]))
    resultado.transformar(f"Uma consulta BBOX ao SICAR por objeto ({len(consultas)} consultas), "
                          "interseção calculada localmente em projeção igual-área")
    pares = pd.concat(todos, ignore_index=True) if todos else pares_objeto_car(None, pd.DataFrame())
    pares = pares[["id_objeto"] + [c for c in pares.columns if c != "id_objeto"]]
    resultado.entrada["consultas"] = consultas

    fracoes = pares[["fracao_objeto", "fracao_car"]]
    fora = ((fracoes < -TOLERANCIA_FRACAO) | (fracoes > 1 + TOLERANCIA_FRACAO)).any(axis=1)
    resultado.validar("CRUZ_FRACAO_FORA_DE_0_A_1", "Fração do objeto ou do CAR fora de [0, 1]", "erro",
                      "interrompe o cruzamento", fora, len(pares))
    resultado.validar("CRUZ_PAR_REPETIDO", "Par objeto-CAR repetido", "erro", "interrompe o cruzamento",
                      pares.duplicated(["id_objeto", "cod_imovel"]), len(pares))

    contagem = (pd.crosstab(pares["id_objeto"], pares["classe"]) if len(pares) else pd.DataFrame()).reindex(
        columns=["principal", "parcial", "tangente"], fill_value=0)
    objetos = objetos.join(contagem, on="id_objeto")
    objetos[["principal", "parcial", "tangente"]] = objetos[["principal", "parcial", "tangente"]].fillna(0).astype(int)
    objetos["cars_tocados"] = objetos[["principal", "parcial", "tangente"]].sum(axis=1)
    objetos["situacao"] = [situacao(*v) for v in objetos[["principal", "parcial", "tangente"]].to_numpy()]
    objetos.loc[sem_area, "situacao"] = "geometria sem área"
    resultado.validar("CRUZ_SEM_CAR_LOCALIZADO", "Objeto sem nenhum CAR que o toque", "alerta",
                      "registrar 'sem CAR localizado', nunca 'sem CAR'", objetos["situacao"] == "sem CAR localizado",
                      len(objetos))
    resultado.validar("CRUZ_VARIOS_PRINCIPAIS", "Objeto com mais de um CAR principal (CARs sobrepostos)", "alerta",
                      "listar todos os CARs principais", objetos["situacao"] == "mais de um CAR principal",
                      len(objetos))
    resultado.saida = {"pares": len(pares), "por_classe": pares["classe"].value_counts().to_dict(),
                       "por_situacao": objetos["situacao"].value_counts().to_dict()}
    resultado.status = "ok"
    return objetos.drop(columns="geometria_wkt"), pares, resultado
