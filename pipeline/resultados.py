"""Resultado do pré-diagnóstico no lago (esquema diag): execução, resultado por imóvel, critério e evidência, e as
mudanças entre as duas últimas execuções de cada imóvel (ADR 0017).

    execucao = resultados.Execucao("carteira", organizacao_id=..., carteira_id=...)
    execucao.acrescentar(ficha, imovel_id=..., prioridade=1, ficha_arquivo="fichas/X.html")
    execucao.encerrar()                      # grava tudo de uma vez
    resultados.mudancas(organizacao_id)      # o que mudou desde a execução anterior

A evidência guarda a tabela e o registro de ref que a sustentam, a carga de origem quando o registro a traz, as
medidas da interseção e a geometria da interseção com o imóvel (o mapa da ficha sem depender das camadas pesadas).
"""

import json
import logging
import subprocess
import uuid
from datetime import datetime

import pandas as pd
import shapely

from pipeline import config, vetor
from pipeline.armazenamento import cargas, contratos, lago

log = logging.getLogger("pipeline")

# Chave em ficha["evidencias"]: (critério, tabela de ref, coluna que identifica o registro).
EVIDENCIAS = {
    "embargos": ("embargo", "ref.embargo_ibama", "id_embargo"),
    "alertas": ("desmatamento", "ref.alerta_deter", "id_alerta"),
    "prodes": ("desmatamento", "ref.desmatamento_prodes", "uuid"),
    "lista_suja": ("lista_suja", "ref.lista_suja", "chave_registro"),
    "terra_indigena": ("terra_indigena", "ref.terra_indigena", "terrai_codigo"),
    "quilombola": ("quilombola", "ref.territorio_quilombola", "codigo"),
    "unidade_conservacao": ("unidade_conservacao", "ref.unidade_conservacao", "cd_cnuc"),
}
CONTAGEM = {"pendência": "n_pendencias", "indício": "n_indicios", "inconclusivo": "n_inconclusivos",
            "não verificado": "n_nao_verificados", "sem ocorrência": "n_sem_ocorrencia"}
MEDIDAS = ("classe", "inter_ha", "fracao_objeto", "fracao_car", "largura_m")
# Organização das execuções de demonstração (CARs públicos, CPF fictício): a única visível a todos no banco. A consulta
# avulsa fica sem organização e não é visível ao papel da aplicação (banco/migracoes/0004).
DEMONSTRACAO = "demonstracao"


def _versao_codigo() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.RAIZ, capture_output=True,
                              text=True, timeout=5, check=True).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _numero(valor):
    return None if valor is None or pd.isna(valor) else float(valor)


def _intersecao(wkt, car_geom) -> str | None:
    if car_geom is None or not isinstance(wkt, str):
        return None
    inter = shapely.intersection(vetor.tornar_valida(shapely.from_wkt(wkt)), car_geom)
    return None if inter.is_empty else shapely.to_wkt(inter, rounding_precision=7)


class Execucao:
    """Uma rodada do pré-diagnóstico. As linhas ficam em memória e vão ao lago de uma vez em encerrar()."""

    def __init__(self, tipo: str, organizacao_id: str | None = None, carteira_id: str | None = None,
                 comando: str | None = None):
        self.id = str(uuid.uuid4())
        self.inicio = datetime.now()
        if tipo == "demonstracao" and organizacao_id is None:
            organizacao_id = DEMONSTRACAO
        self.tipo, self.organizacao_id, self.carteira_id, self.comando = tipo, organizacao_id, carteira_id, comando
        self.ano_mes = f"{self.inicio:%Y-%m}"
        self.resultados, self.criterios, self.evidencias = [], [], []

    def acrescentar(self, ficha: dict, imovel_id: str | None = None, prioridade: int | None = None,
                    ficha_arquivo: str | None = None) -> str:
        """Guarda a ficha (com as evidências ainda em DataFrame, antes de para_json). Devolve o resultado_id."""
        resultado_id = str(uuid.uuid4())
        im, res = ficha.get("imovel") or {}, ficha["resultado"]
        contagem = res.get("contagem", {})
        base = {"resultado_id": resultado_id, "organizacao_id": self.organizacao_id, "ano_mes": self.ano_mes}
        self.resultados.append({
            **base, "execucao_id": self.id, "imovel_id": imovel_id, "cod_imovel": im.get("cod_imovel"),
            "uf": im.get("uf"), "cod_municipio": im.get("cod_municipio"), "area_ha": _numero(im.get("area_geom_ha")),
            "situacao": res["situacao"], "resumo": res.get("resumo"), "prioridade": prioridade,
            **{coluna: contagem.get(s, 0) for s, coluna in CONTAGEM.items()},
            "gerado_em": ficha.get("consulta", {}).get("gerado_em") or datetime.now(), "ficha": ficha_arquivo})
        for c in ficha["criterios"]:
            self.criterios.append({**base, **{k: c.get(k) for k in ("chave", "criterio", "criterio_ab_s",
                                                                      "situacao", "evidencia", "encaminhamento",
                                                                      "fonte", "aviso")}})
        car_geom = None
        if ficha.get("geometria_car"):
            car_geom = vetor.tornar_valida(shapely.from_wkt(ficha["geometria_car"]))
        for nome, achados in (ficha.get("evidencias") or {}).items():
            if nome not in EVIDENCIAS or not isinstance(achados, pd.DataFrame) or achados.empty:
                continue
            chave_criterio, tabela, ident = EVIDENCIAS[nome]
            for _, linha in achados.iterrows():
                outros = linha.drop(labels=[ident, "geometria_wkt", "carga_id", *MEDIDAS, "data_imagem"],
                                    errors="ignore")
                detalhes = json.loads(outros.to_json(date_format="iso", force_ascii=False))
                self.evidencias.append({
                    **base, "evidencia_id": str(uuid.uuid4()), "chave_criterio": chave_criterio, "tabela": tabela,
                    "registro_id": str(linha.get(ident)), "carga_id": linha.get("carga_id"),
                    "classe": linha.get("classe"), **{m: _numero(linha.get(m)) for m in MEDIDAS if m != "classe"},
                    "data_imagem": linha.get("data_imagem"),
                    "detalhes_json": json.dumps(detalhes, ensure_ascii=False) if detalhes else None,
                    "geometria_wkt": _intersecao(linha.get("geometria_wkt"), car_geom)})
        return resultado_id

    def encerrar(self) -> dict:
        """Grava a execução, as cargas em uso e as linhas acumuladas em diag."""
        carga_id = f"pipeline:{self.inicio:%Y%m%dT%H%M%S}"
        execucao = {"execucao_id": self.id, "organizacao_id": self.organizacao_id, "tipo": self.tipo,
                    "carteira_id": self.carteira_id, "iniciada_em": self.inicio, "terminada_em": datetime.now(),
                    "comando": self.comando, "versao_codigo": _versao_codigo(), "ano_mes": self.ano_mes}
        fontes = [f["fonte"] for f in contratos.catalogo_fontes() if f.get("acesso") == "lote"]
        em_uso = [{"execucao_id": self.id, "fonte": f, "carga_id": (cargas.ultima(f) or {}).get("carga_id")}
                  for f in fontes]
        resumo = {}
        for tabela, linhas in (("diag.execucao", [execucao]), ("diag.execucao_carga", em_uso),
                               ("diag.resultado_imovel", self.resultados), ("diag.criterio", self.criterios),
                               ("diag.evidencia", self.evidencias)):
            if linhas:
                resumo[tabela] = lago.gravar(tabela, lago.quadro(tabela, linhas), carga_id=carga_id,
                                             momento=self.inicio)["inseridos"]
        log.info("[diag] execução %s (%s): %d imóvel(is), %d critério(s), %d evidência(s)", self.id, self.tipo,
                 len(self.resultados), len(self.criterios), len(self.evidencias))
        return resumo


def _pares(organizacao_id: str | None, cod_imoveis=None) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Resultados das duas últimas execuções de cada imóvel da organização que tem pelo menos duas (coluna `ordem`:
    anterior/atual) e os critérios do lago. `cod_imoveis` restringe aos imóveis informados (ex.: a carteira atual)."""
    res, crit = lago.ler_ou_none("diag.resultado_imovel"), lago.ler_ou_none("diag.criterio")
    if res is None or crit is None:
        return None, crit
    mesma_org = res["organizacao_id"].isna() if organizacao_id is None else res["organizacao_id"] == organizacao_id
    res = res[mesma_org & res["cod_imovel"].notna()]
    if cod_imoveis is not None:
        res = res[res["cod_imovel"].isin(list(cod_imoveis))]
    ultimos = res.sort_values("gerado_em", kind="stable").groupby("cod_imovel").tail(2)
    pares = ultimos.groupby("cod_imovel").filter(lambda g: len(g) == 2)
    if pares.empty:
        return None, crit
    return pares.assign(ordem=pares.groupby("cod_imovel").cumcount().map({0: "anterior", 1: "atual"})), crit


def anteriores(organizacao_id: str | None = DEMONSTRACAO, cod_imoveis=None) -> pd.Series:
    """Data da execução anterior de cada imóvel da organização que já tem duas execuções (índice: cod_imovel)."""
    pares, _ = _pares(organizacao_id, cod_imoveis)
    if pares is None:
        return pd.Series(dtype="datetime64[ns]", name="gerado_em_anterior")
    anterior = pares[pares["ordem"] == "anterior"]
    return pd.Series(anterior["gerado_em"].values, index=anterior["cod_imovel"].values, name="gerado_em_anterior")


def ha_execucao_anterior(organizacao_id: str | None, execucao_id: str | None = None) -> bool:
    """A organização já tinha alguma execução gravada além de `execucao_id`?"""
    execucoes = lago.ler_ou_none("diag.execucao")
    if execucoes is None:
        return False
    mesma_org = (execucoes["organizacao_id"].isna() if organizacao_id is None
                 else execucoes["organizacao_id"] == organizacao_id)
    return bool((mesma_org & (execucoes["execucao_id"] != execucao_id)).any())


def mudancas(organizacao_id: str | None = DEMONSTRACAO, cod_imoveis=None) -> pd.DataFrame:
    """Critérios cuja situação mudou entre as duas últimas execuções de cada imóvel da organização (padrão: a
    demonstração; None: as consultas avulsas, sem organização). Critério que apareceu ou sumiu também conta.
    `cod_imoveis` restringe a comparação a esses imóveis (a carteira atual)."""
    colunas = ["cod_imovel", "chave", "criterio", "situacao_anterior", "situacao_atual", "gerado_em_anterior",
               "gerado_em_atual", "evidencia_atual"]
    pares, crit = _pares(organizacao_id, cod_imoveis)
    if pares is None or crit is None:
        return pd.DataFrame(columns=colunas)
    crit = crit.merge(pares[["resultado_id", "cod_imovel", "gerado_em", "ordem"]], on="resultado_id")
    largo = crit.pivot_table(index=["cod_imovel", "chave"], columns="ordem",
                             values=["situacao", "gerado_em", "evidencia", "criterio"], aggfunc="first")
    largo.columns = [f"{v}_{o}" for v, o in largo.columns]
    largo = largo.reset_index()
    for c in ("situacao_anterior", "situacao_atual"):
        if c not in largo:
            largo[c] = None
    mudou = largo["situacao_anterior"].fillna("—") != largo["situacao_atual"].fillna("—")
    largo["criterio"] = largo.get("criterio_atual", pd.Series(dtype=object)).fillna(
        largo.get("criterio_anterior", pd.Series(dtype=object)))
    # As datas de cada execução valem para todos os critérios do imóvel.
    datas = pares.pivot(index="cod_imovel", columns="ordem", values="gerado_em")
    largo["gerado_em_anterior"] = largo["cod_imovel"].map(datas["anterior"])
    largo["gerado_em_atual"] = largo["cod_imovel"].map(datas["atual"])
    return largo.loc[mudou].reindex(columns=colunas).reset_index(drop=True)
