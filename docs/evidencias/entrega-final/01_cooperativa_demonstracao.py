"""Carteira de demonstração da "Cooperativa Vale do Cerrado (demonstração)": 12 imóveis, 7 de café e 5 de gado.

Roda da raiz, sem rede (o SICAR vem do cache em data/raw/sicar/ e o PRODES, do lote já baixado):

    .venv/bin/python docs/evidencias/entrega-final/01_cooperativa_demonstracao.py [--ao-vivo]

O que faz, nesta ordem:
  1. Desenha os talhões sintéticos (docs/modelos/talhoes/*.kml) DENTRO do CAR, a partir da geometria do CAR e dos
     alertas que ele já tem: o mesmo CAR e o mesmo cache dão o mesmo KML, byte a byte.
  2. Lê docs/modelos/cooperativa_demonstracao.csv (sem CPF/CNPJ) e injeta, em memória, o documento de
     demonstração (prediagnostico.DOCUMENTO_DEMONSTRACAO) em três linhas. A planilha nunca o recebe.
  3. Cadastra a organização `demonstracao` e roda a carteira (pipeline.carteira.processar, o mesmo caminho de
     `python -m pipeline.carteira --sem-baixar-prodes`), gravando em cad e diag.
  4. Grava as fichas e a carteira em data/saidas/console/demonstracao/ e reescreve o LEIA-ME.md ao lado, com a
     tabela "caso → o que mostra → situação obtida" e a execução (rastreabilidade).

Sem cache do SICAR para um imóvel, o caso vira "inconclusivo" com o motivo e o script avisa (nunca vai à rede,
a não ser com --ao-vivo). Duas execuções dão o mesmo resultado; só mudam os ids e os horários da execução.
Nenhum CPF/CNPJ é escrito: o documento de demonstração entra pseudonimizado (documento_hash) pelo pipeline.
"""

import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import shapely

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
from pipeline import cadastro, carteira, config, prediagnostico, relatorio, resultados, territorio, vetor, wfs  # noqa: E402
from pipeline.armazenamento import lago  # noqa: E402
from pipeline.fontes import sicar  # noqa: E402

PASTA = Path(__file__).resolve().parent
PLANILHA = RAIZ / "docs" / "modelos" / "cooperativa_demonstracao.csv"
SAIDA = config.SAIDAS / "console" / "demonstracao"
ORGANIZACAO_ID = resultados.DEMONSTRACAO  # 'demonstracao': a única visível a todos (RLS)
ORGANIZACAO_NOME = "Cooperativa Vale do Cerrado (demonstração)"
# Linhas que recebem o documento de demonstração na hora (as outras ficam sem documento: Lista Suja "não verificado").
COM_DOCUMENTO = ("CVC-06", "CVC-08", "CVC-10")

# id_produtor -> (o que o caso mostra). A situação obtida vem da execução, nunca é escrita aqui.
CASOS = {
    "CVC-01": "Talhão desenhado longe do desmatamento: o critério EUDR limpa na área de produção, mas o desmatamento do resto do imóvel continua como indício",
    "CVC-02": "Embargo do IBAMA e alertas confirmados pelo PRODES, em Serra do Salitre",
    "CVC-03": "Talhão sobre os alertas DETER de ago. 2026 (ainda sem PRODES): o indício cai na área de produção e o técnico confere em imagem",
    "CVC-04": "Embargo do IBAMA e alerta sobre área já suprimida antes: o alerta fica como indício, não como pendência",
    "CVC-05": "CAR com notificação pendente, embargos e alerta confirmado: o caso mais pesado do café",
    "CVC-06": "Imóvel analisado e sem achado nas fontes, com documento informado: o limite do sistema (nunca diz \"conforme\")",
    "CVC-07": "Coordenada com latitude e longitude trocadas: a linha não é consultada e diz por quê",
    "CVC-08": "Pantanal: PRODES após 2020 em Corumbá, com documento informado e item do gado no plano de ação",
    "CVC-09": "Amazônia: PRODES de 2021 com data incerta diante do corte (indício, não pendência)",
    "CVC-10": "Sobreposição com território quilombola (Santarém), com documento informado",
    "CVC-11": "Sobreposição com terra indígena declarada e APA (Paranhos)",
    "CVC-12": "Localização só por coordenada em Goiás: o ponto precisa cair em um único CAR",
}

DEGRAU = 0.0008  # ~90 m em graus: folga entre o talhão, a borda do CAR e os alertas


# --- 1. Talhões ---------------------------------------------------------------------------------------------------

def _cache_sicar(cod: str | None, lat, lon) -> Path | None:
    """Arquivo do cache do SICAR que `sicar.consultar_*` leria para esta linha (a regra de nome é a do pipeline)."""
    if cod:
        cod = cod.strip().upper()
        tipo, cql, uf = "codigo", f"cod_imovel='{cod}'", cod[:2]
    else:
        uf = territorio.uf_do_ponto(lat, lon)
        if not uf:
            return None  # fora do Brasil: a ficha inconclusiva sai sem consultar o SICAR
        tipo, cql = "ponto", wfs.filtro_ponto(sicar.CAMPO_GEOMETRIA, lat, lon)
    nome = f"{tipo}_{hashlib.sha1(cql.encode()).hexdigest()[:16]}"
    return config.DADOS_BRUTOS / "sicar" / uf.lower() / f"{nome}.geojson.gz"


def consultar_do_cache(ao_vivo: bool, sem_cache: list):
    """`consultar=` da carteira: só consulta se o SICAR está no cache (ou com --ao-vivo). Sem cache, levanta com o
    motivo, que a carteira transforma em linha inconclusiva."""
    def consultar(cod, lat=None, lon=None, documento=None, **kwargs):
        arquivo = _cache_sicar(cod, lat, lon)
        if not ao_vivo and arquivo is not None and not arquivo.exists():
            sem_cache.append(cod or f"{lat},{lon}")
            raise RuntimeError("SICAR sem cache local em data/raw/sicar/ e modo offline (use --ao-vivo para consultar)")
        return prediagnostico.executar(cod, lat, lon, documento, **kwargs)
    return consultar


def _poligonos(geom) -> list:
    return [g for g in shapely.get_parts(geom) if g.geom_type == "Polygon" and not g.is_empty]


def _alvos(ficha: dict, car) -> object:
    """Onde há desmatamento no CAR: PRODES e alertas DETER que cruzam o imóvel."""
    partes = []
    for nome in ("prodes", "alertas"):
        achados = ficha["evidencias"].get(nome)
        if isinstance(achados, pd.DataFrame) and not achados.empty:
            partes += [vetor.tornar_valida(shapely.from_wkt(w)) for w in achados["geometria_wkt"]]
    return shapely.intersection(shapely.union_all(partes), car) if partes else shapely.Polygon()


def talhao_fora(car, alvos):
    """Maior área livre do CAR, com folga da borda e dos alertas, simplificada a poucos vértices."""
    livre = car.buffer(-DEGRAU).difference(alvos.buffer(DEGRAU))
    peca = max(_poligonos(livre), key=lambda p: p.area)
    return peca.simplify(DEGRAU / 4)


def talhao_sobre(car, alvos):
    """Envoltória dos alertas com folga, cortada pelo CAR encolhido: o talhão cobre o alerta."""
    envoltoria = alvos.buffer(DEGRAU).convex_hull.intersection(car.buffer(-DEGRAU / 2))
    return max(_poligonos(envoltoria), key=lambda p: p.area).simplify(DEGRAU / 8)


TALHOES = {  # id_produtor -> (arquivo, função que desenha, condição verificada)
    "CVC-01": ("cvc-01_fora_do_desmatamento.kml", talhao_fora, "fora"),
    "CVC-03": ("cvc-03_sobre_o_alerta.kml", talhao_sobre, "sobre"),
}


def _kml(poligono, nome: str, descricao: str) -> str:
    anel = shapely.geometry.polygon.orient(poligono, 1.0).exterior.coords
    coordenadas = " ".join(f"{x:.6f},{y:.6f},0" for x, y, *_ in anel)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n'
            f"<name>{nome}</name>\n<Placemark>\n<name>{nome}</name>\n<description>{descricao}</description>\n"
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
            f"{coordenadas}</coordinates></LinearRing></outerBoundaryIs></Polygon>\n</Placemark>\n</Document>\n</kml>\n")


def gerar_talhoes(planilha: pd.DataFrame, consultar) -> list[str]:
    """Reescreve os KML. Devolve os avisos (CAR sem cache: o KML existente é mantido)."""
    avisos = []
    pasta = PLANILHA.parent / "talhoes"
    pasta.mkdir(exist_ok=True)
    for id_produtor, (arquivo, desenhar, condicao) in TALHOES.items():
        cod = planilha.loc[planilha["id_produtor"] == id_produtor, "cod_car"].iloc[0]
        try:
            ficha = consultar(cod, documento=None, baixar_prodes=False)
        except Exception as e:  # sem cache: o caso fica inconclusivo adiante e o KML não muda
            avisos.append(f"{id_produtor}: talhão não regerado ({carteira._erro(e)})")
            continue
        car = shapely.from_wkt(ficha["geometria_car"])
        alvos = _alvos(ficha, car)
        if alvos.is_empty:
            avisos.append(f"{id_produtor}: o CAR não tem desmatamento no cache; talhão não regerado")
            continue
        talhao = shapely.from_wkt(shapely.to_wkt(desenhar(car, alvos), rounding_precision=6))
        dentro = car.contains(talhao)
        confere = (not shapely.intersects(talhao, alvos)) if condicao == "fora" else shapely.intersects(talhao, alvos)
        if not (dentro and confere):
            avisos.append(f"{id_produtor}: o talhão desenhado não cumpre o desenho pedido; KML não gravado")
            continue
        descricao = ("Talhão sintético de demonstração, desenhado dentro do CAR "
                     + ("sem tocar nenhum alerta" if condicao == "fora" else "sobre os alertas")
                     + " (docs/evidencias/entrega-final/01_cooperativa_demonstracao.py).")
        (pasta / arquivo).write_text(_kml(talhao, f"Talhão de demonstração {id_produtor}", descricao), encoding="utf-8")
        print(f"talhão {arquivo}: {shapely.area(sicar.projetar(talhao)) / 1e4:.1f} ha de "
              f"{shapely.area(sicar.projetar(car)) / 1e4:.1f} ha do CAR")
    return avisos


# --- 2 e 3. Carteira ----------------------------------------------------------------------------------------------

def cadastrar_organizacao() -> None:
    """Organização `demonstracao` com o nome da cooperativa (cadastro.organizacao geraria um id aleatório)."""
    existentes = lago.ler_ou_none("cad.organizacao")
    if existentes is not None and (existentes["organizacao_id"] == ORGANIZACAO_ID).any():
        return
    momento = datetime.now()
    lago.gravar("cad.organizacao", lago.quadro("cad.organizacao", [{
        "organizacao_id": ORGANIZACAO_ID, "nome": ORGANIZACAO_NOME, "tipo": "cooperativa", "uf": "MG",
        "criado_em": momento}]), carga_id=f"cadastro:{momento:%Y%m%dT%H%M%S}", momento=momento)


def rodar(ao_vivo: bool) -> tuple[pd.DataFrame, dict, resultados.Execucao, str, list, list]:
    sem_cache: list = []
    consultar = consultar_do_cache(ao_vivo, sem_cache)
    planilha = carteira.ler_planilha(PLANILHA)
    avisos = gerar_talhoes(planilha, consultar)
    planilha.loc[planilha["id_produtor"].isin(COM_DOCUMENTO), "documento"] = prediagnostico.DOCUMENTO_DEMONSTRACAO
    SAIDA.mkdir(parents=True, exist_ok=True)
    cadastrar_organizacao()
    problemas = {i: m for i, linha in planilha.iterrows() if (m := carteira.problema(
        pd.Series({k: carteira._valor(linha, k) for k in planilha.columns}, dtype=object)))}
    areas = carteira.areas_de_producao(planilha, PLANILHA.parent)
    carteira_id, ids = cadastro.importar_carteira(planilha, ORGANIZACAO_ID, PLANILHA, problemas, areas)
    execucao = resultados.Execucao("carteira", ORGANIZACAO_ID, carteira_id,
                                   "python docs/evidencias/entrega-final/01_cooperativa_demonstracao.py "
                                   "(carteira --sem-baixar-prodes)")
    saida = carteira.processar(planilha, SAIDA, baixar_prodes=False, consultar=consultar, execucao=execucao, ids=ids,
                               areas=areas)
    execucao.encerrar()
    saida, comparacao = carteira.comparar(saida, ORGANIZACAO_ID, execucao.id)
    saida.to_csv(SAIDA / "carteira.csv", index=False)
    (SAIDA / "carteira.html").write_text(carteira.html(saida, PLANILHA.name, comparacao), encoding="utf-8")
    return saida, comparacao, execucao, carteira_id, avisos, sem_cache


# --- 4. LEIA-ME ---------------------------------------------------------------------------------------------------

def _situacao(linha: pd.Series) -> str:
    partes = [f"**{linha['resultado']}**"]
    for rotulo, coluna in (("pendência", "pendencias"), ("indício", "indicios"), ("inconclusivo", "inconclusivos")):
        if isinstance(linha.get(coluna), str) and linha[coluna]:
            partes.append(f"{rotulo}: {linha[coluna]}")
    if isinstance(linha.get("problema_na_linha"), str) and linha["problema_na_linha"]:
        partes.append(f"motivo: {linha['problema_na_linha']}")
    if isinstance(linha.get("aviso_area_producao"), str) and linha["aviso_area_producao"]:
        partes.append(f"talhão: {linha['aviso_area_producao']}")
    return "; ".join(partes).replace("|", "/")


def escrever_leia_me(saida: pd.DataFrame, execucao, carteira_id: str, avisos: list, sem_cache: list) -> None:
    planilha = pd.read_csv(PLANILHA, dtype=str).fillna("")
    por_produtor = saida.set_index("id_produtor")
    linhas = ["| Caso | Imóvel | O que mostra | Situação obtida |", "|---|---|---|---|"]
    for _, p in planilha.iterrows():
        s = por_produtor.loc[p["id_produtor"]]
        local = f"{s['municipio']}/{s['uf']}" if isinstance(s["municipio"], str) else "sem localização"
        talhao = " (com talhão)" if p["area_producao"] else ""
        linhas.append(f"| {p['id_produtor']} | {p['nome_area']}, {p['commodity']}, {local}{talhao} | "
                      f"{CASOS[p['id_produtor']]} | {_situacao(s)} |")
    cargas = lago.ler("diag.execucao_carga")
    cargas = cargas[cargas["execucao_id"] == execucao.id].sort_values("fonte")
    cad_carteira = lago.ler("cad.carteira")
    importada = cad_carteira.loc[(cad_carteira["carteira_id"] == carteira_id)
                                 & (cad_carteira["organizacao_id"] == ORGANIZACAO_ID), "importada_em"].iloc[0]
    contagem = saida["resultado"].value_counts().to_dict()
    alerta = (["", "> **Aviso:** " + "; ".join(avisos)] if avisos else []) + (
        ["", f"> **Aviso:** {len(set(sem_cache))} imóvel(is) sem cache do SICAR em `data/raw/sicar/`; ficaram "
             "inconclusivos com o motivo na linha. Rode com `--ao-vivo` para consultar."] if sem_cache else [])
    texto = [
        "# Entrega final: carteira de demonstração",
        "",
        f"**{ORGANIZACAO_NOME}**: 12 imóveis (7 de café, 5 de gado), `organizacao_id = '{ORGANIZACAO_ID}'`. Os 12 usam "
        "CARs públicos já conferidos (os mesmos da demonstração do pré-diagnóstico); os nomes, os ids de produtor e as "
        "commodities são fictícios. Nenhum CPF/CNPJ está na planilha nem aqui: três linhas "
        f"({', '.join(COM_DOCUMENTO)}) recebem o documento de demonstração em memória, na hora de rodar, e ele só "
        "aparece pseudonimizado no lago. Não há caso positivo de Lista Suja (decisão de 23/11/2026): "
        "um caso positivo exigiria o documento de uma pessoa real ou um lago sintético.",
        "",
        "| Arquivo | O que é |",
        "|---|---|",
        "| `01_cooperativa_demonstracao.py` | Desenha os talhões, roda a carteira sem rede e reescreve este arquivo |",
        "| `../../modelos/cooperativa_demonstracao.csv` | A planilha de 12 linhas (formato de `pipeline/carteira.py`) |",
        "| `../../modelos/talhoes/*.kml` | Talhões sintéticos, desenhados dentro do CAR a partir da geometria dele |",
        "| `data/saidas/console/demonstracao/` | Fichas (`fichas/`), `carteira.csv` e `carteira.html` (não versionada) |",
        "",
        "As camadas de mapa de cada ficha (`.camadas.geojson`) vêm da issue #31 e aparecem nessa pasta quando ela "
        "entrar; este script não as gera.",
        "",
        "## Caso → o que mostra → situação obtida",
        "",
        f"Carteira de {len(saida)} imóveis: " + ", ".join(f"{n} {r}" for r, n in contagem.items()) + ".",
        *alerta,
        "",
        *linhas,
        "",
        "Nos dois casos com talhão o cruzamento de desmatamento passa a ser com a área desenhada, e a ficha separa o que "
        "está na área de produção do que está no resto do imóvel. O talhão de CVC-01 deixa de fora todo o desmatamento "
        "do CAR (o resto vira indício); o de CVC-03 cobre os alertas (o indício cai na área de produção).",
        "",
        "## Rastreabilidade desta execução",
        "",
        f"- Execução de carteira `{execucao.id}` (`diag.execucao`, organização `{ORGANIZACAO_ID}`), "
        f"iniciada em {execucao.inicio:%d/%m/%Y %H:%M:%S} (horário de Brasília).",
        f"- Carteira importada `{carteira_id}` em `cad.carteira` ({importada:%d/%m/%Y %H:%M:%S}); "
        f"cargas: `cadastro:{importada:%Y%m%dT%H%M%S}` (cadastro) e `pipeline:{execucao.inicio:%Y%m%dT%H%M%S}` (diag).",
        "- Cargas das fontes em uso (`diag.execucao_carga`): "
        + (", ".join(f"{r.fonte} `{r.carga_id}`" for r in cargas.itertuples()) or "nenhuma registrada") + ".",
        "- SICAR: cache em `data/raw/sicar/` (um arquivo por consulta, com `.meta.json` e SHA-256); PRODES: lote em "
        "`data/` (`--sem-baixar-prodes`).",
        "",
        "## Como regerar",
        "",
        "```bash",
        ".venv/bin/python docs/evidencias/entrega-final/01_cooperativa_demonstracao.py",
        "```",
        "",
        "Leva menos de 30 s. Duas execuções dão a mesma tabela (o SICAR vem do cache); só mudam o id e o horário da "
        "execução, e a carteira passa a comparar com a execução anterior. Sem cache do SICAR, o imóvel fica "
        "inconclusivo com o motivo e o script avisa; `--ao-vivo` permite a consulta à rede.",
        "",
    ]
    (PASTA / "LEIA-ME.md").write_text("\n".join(texto), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ao-vivo", action="store_true", help="consulta o SICAR na rede quando falta cache")
    args = parser.parse_args(argv)
    relatorio.configurar_log(config.LOGS / f"demonstracao_cooperativa_{datetime.now():%Y%m%d_%H%M%S}.log")
    saida, _, execucao, carteira_id, avisos, sem_cache = rodar(args.ao_vivo)
    escrever_leia_me(saida, execucao, carteira_id, avisos, sem_cache)
    for aviso in avisos:
        print("AVISO:", aviso)
    if sem_cache:
        print(f"AVISO: {len(set(sem_cache))} imóvel(is) sem cache do SICAR; ficaram inconclusivos: "
              + ", ".join(sorted(set(sem_cache))))
    print(saida["resultado"].value_counts().to_string())
    print(f"{SAIDA / 'carteira.html'}\n{PASTA / 'LEIA-ME.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
