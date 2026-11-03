"""meta.carga, meta.validacao e meta.fonte: o registro de cada execução de fonte no lago, com histórico.

Substitui aos poucos o procedencia_fontes.json, que guarda só a última execução de cada fonte.
"""

import json
from datetime import datetime

import pandas as pd

from pipeline.armazenamento import contratos, lago
from pipeline.validacao import ResultadoFonte


def _json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


def _inteiro(valor):
    return int(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else None


def linha_carga(r: ResultadoFonte) -> dict:
    e, s = r.entrada or {}, r.saida or {}
    return {"carga_id": r.carga_id, "fonte": r.fonte, "tipo_dado": r.tipo_dado,
            "iniciada_em": pd.Timestamp(lago.momento_da_carga(r.carga_id)), "status": r.status,
            "mensagem": r.mensagem or None, "url": e.get("url") or e.get("servico"), "sha256_entrada": e.get("sha256"),
            "registros_recebidos": _inteiro(e.get("registros_recebidos")),
            "registros_produzidos": _inteiro(s.get("registros_produzidos")),
            "registros_descartados": _inteiro(s.get("registros_descartados")),
            "registros_com_alerta": _inteiro(s.get("registros_com_alerta")),
            "tabelas_json": _json(s.get("tabelas", {})), "entrada_json": _json(e), "saida_json": _json(s),
            "transformacoes_json": _json(r.transformacoes)}


def registrar(resultados: list[ResultadoFonte]) -> None:
    """Grava uma linha por resultado em meta.carga e as validações em meta.validacao."""
    if not resultados:
        return
    agora = datetime.now()
    carga_id = f"pipeline:{agora:%Y%m%dT%H%M%S}"
    cargas = pd.DataFrame([linha_carga(r) for r in resultados])
    cargas["iniciada_em"] = pd.to_datetime(cargas["iniciada_em"])
    for c in ("registros_recebidos", "registros_produzidos", "registros_descartados", "registros_com_alerta"):
        cargas[c] = cargas[c].astype("Int64")
    lago.gravar("meta.carga", cargas, carga_id=carga_id, momento=agora)
    validacoes = pd.DataFrame([{"carga_id": r.carga_id, "fonte": r.fonte, "codigo": v.codigo,
                                "descricao": v.descricao, "severidade": v.severidade, "tratamento": v.tratamento,
                                "verificados": v.verificados, "ocorrencias": v.ocorrencias}
                               for r in resultados for v in r.validacoes])
    if not validacoes.empty:
        # A mesma validação pode rodar mais de uma vez numa carga (ex.: por partição); vale a soma.
        validacoes = validacoes.groupby(["carga_id", "fonte", "codigo"], as_index=False, sort=False).agg(
            descricao=("descricao", "first"), severidade=("severidade", "first"), tratamento=("tratamento", "first"),
            verificados=("verificados", "sum"), ocorrencias=("ocorrencias", "sum"))
        lago.gravar("meta.validacao", validacoes, carga_id=carga_id, momento=agora)


def registrar_catalogo() -> dict:
    """meta.fonte a partir de contratos/fontes.yaml (fotografia: só grava quando o catálogo muda)."""
    agora = datetime.now()
    df = pd.DataFrame(contratos.catalogo_fontes())
    df["tabelas"] = df["tabelas"].map(lambda t: ", ".join(t))
    return lago.gravar("meta.fonte", df, carga_id=f"pipeline:{agora:%Y%m%dT%H%M%S}", momento=agora)


def ultima(fonte: str, so_ok: bool = True) -> dict | None:
    """Última carga de uma fonte (a mais recente em meta.carga), como dicionário; None se não houver."""
    df = lago.ler_ou_none("meta.carga")
    if df is None:
        return None
    df = df[(df["fonte"] == fonte) & ((df["status"] == "ok") if so_ok else True)]
    if df.empty:
        return None
    return df.sort_values("iniciada_em").iloc[-1].to_dict()
