import pandas as pd
import shapely

from conftest import ocorrencias
from pipeline import cruzamento

X0, Y0 = -46.99, -18.95
METRO = 1 / 105_000  # grau de longitude, aproximado, nesta latitude


def cars(*caixas):
    return pd.DataFrame({
        "cod_imovel": [f"MG-3148103-{i:032X}" for i in range(len(caixas))], "status_imovel": "AT",
        "condicao": "Aguardando análise", "cod_municipio": "3148103",
        "geometria_wkt": [shapely.box(*c).wkt for c in caixas]})


CAR_A = (X0, Y0, X0 + 0.01, Y0 + 0.01)
CAR_B = (X0 + 0.01, Y0, X0 + 0.02, Y0 + 0.01)


def classes(objeto, df):
    return cruzamento.pares_objeto_car(objeto, df).set_index("cod_imovel")["classe"].tolist()


def test_objeto_inteiro_num_car_e_principal_e_vizinho_na_divisa_e_tangente():
    # Objeto dentro de A, invadindo B numa faixa de 10 m.
    objeto = shapely.box(X0 + 0.005, Y0 + 0.002, X0 + 0.01 + 10 * METRO, Y0 + 0.008)
    assert classes(objeto, cars(CAR_A, CAR_B)) == ["principal", "tangente"]


def test_objeto_dividido_entre_dois_cars_e_parcial_no_menor_pedaco():
    objeto = shapely.box(X0 + 0.003, Y0 + 0.002, X0 + 0.013, Y0 + 0.008)  # 70% em A, 30% em B
    assert classes(objeto, cars(CAR_A, CAR_B)) == ["principal", "parcial"]


def test_objeto_estreito_inteiro_no_car_e_principal_nao_tangente():
    objeto = shapely.box(X0 + 0.002, Y0 + 0.002, X0 + 0.002 + 20 * METRO, Y0 + 0.008)  # 20 m de largura
    pares = cruzamento.pares_objeto_car(objeto, cars(CAR_A))
    assert pares.loc[0, "largura_m"] < cruzamento.LIMIAR_LARGURA_M and pares.loc[0, "classe"] == "principal"


def test_atribuir_car_resume_a_situacao_de_cada_objeto():
    objetos = pd.DataFrame({
        "tipo": "alerta DETER", "id_objeto": ["um", "fora"],
        "geometria_wkt": [shapely.box(X0 + 0.002, Y0 + 0.002, X0 + 0.008, Y0 + 0.008).wkt,
                          shapely.box(X0 + 0.5, Y0, X0 + 0.51, Y0 + 0.01).wkt]})

    def consultar(limites, uf, atualizar):
        class R:
            entrada = {"requisicoes": [{"anunciado": 2, "recebido": 2}]}
        return cars(CAR_A, CAR_B), R()

    obj, pares, r = cruzamento.atribuir_car(objetos, consultar=consultar)
    assert obj.set_index("id_objeto")["situacao"].to_dict() == {"um": "um CAR principal", "fora": "sem CAR localizado"}
    assert ocorrencias(r, "CRUZ_SEM_CAR_LOCALIZADO") == 1 and len(pares) == 1


def test_situacao():
    assert cruzamento.situacao(2, 0, 1) == "mais de um CAR principal"
    assert cruzamento.situacao(0, 0, 3) == "só tangentes"
    assert cruzamento.situacao(0, 1, 1) == "só parciais"
