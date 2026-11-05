"""Cadastro do cliente no lago (esquema cad): organização, produtor, imóvel, documento trazido e carteira importada.

O CPF ou CNPJ informado na planilha só entra pseudonimizado (documento_hash, ADR 0002). Produtor e imóvel já
cadastrados na organização são reaproveitados: a carteira do mês seguinte aponta para os mesmos ids, e é isso que
permite comparar execuções. O consentimento LGPD (cad.consentimento) entra no piloto, pelo atendimento.
"""

import hashlib
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline import vetor
from pipeline.armazenamento import lago
from pipeline.documentos import carregar_chave, pseudonimizar, sem_documento, somente_digitos, tipo_documento

INFORMADOS = ("ccir", "codigo_sigef", "relatorio_ab_s")
EXTRAS_IMOVEL = ("nome_area", "commodity")


def _carga(momento: datetime) -> str:
    return f"cadastro:{momento:%Y%m%dT%H%M%S}"


def _gravar(tabela: str, linhas: list[dict], momento: datetime) -> None:
    if linhas:
        lago.gravar(tabela, lago.quadro(tabela, linhas), carga_id=_carga(momento), momento=momento)


def organizacao(nome: str, tipo: str = "cooperativa", uf: str | None = None) -> str:
    """Id da organização com esse nome; cadastra se ainda não existe."""
    existentes = lago.ler_ou_none("cad.organizacao")
    if existentes is not None:
        achada = existentes[existentes["nome"] == nome]
        if not achada.empty:
            return achada["organizacao_id"].iloc[0]
    momento = datetime.now()
    novo = str(uuid.uuid4())
    _gravar("cad.organizacao", [{"organizacao_id": novo, "nome": nome, "tipo": tipo, "uf": uf,
                                 "criado_em": momento}], momento)
    return novo


def _texto(valor) -> str | None:
    return None if valor is None or pd.isna(valor) or str(valor).strip() == "" else str(valor).strip()


def _coordenada(valor) -> float | None:
    """Coordenada decimal (vírgula ou ponto); None se não for número (a carteira já marca a linha com o problema)."""
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None


def importar_carteira(df: pd.DataFrame, organizacao_id: str, arquivo: Path,
                      problemas: dict[int, str] | None = None,
                      areas: dict[int, dict] | None = None) -> tuple[str, dict[int, dict]]:
    """Grava a planilha em cad (carteira, itens, produtores, imóveis, documentos trazidos, área de produção). Devolve
    o carteira_id e, por índice da linha, {"produtor_id", "imovel_id"}. `problemas`: motivo de recusa por índice
    (linha sem localização etc.), que fica no item da carteira. `areas`: área de produção lida por índice
    (carteira.areas_de_producao); só a que foi lida entra, e a mesma área do mesmo imóvel não se repete."""
    momento = datetime.now()
    problemas, areas = problemas or {}, areas or {}
    chave = carregar_chave()
    org = lambda tabela: (lambda d: d[d["organizacao_id"] == organizacao_id] if d is not None else None)(
        lago.ler_ou_none(tabela))
    produtores_ant, imoveis_ant = org("cad.produtor"), org("cad.imovel")
    por_produtor = {} if produtores_ant is None else dict(zip(produtores_ant["id_produtor"],
                                                              produtores_ant["produtor_id"]))
    por_car = {} if imoveis_ant is None else dict(zip(imoveis_ant["cod_car"].dropna(),
                                                      imoveis_ant.loc[imoveis_ant["cod_car"].notna(), "imovel_id"]))
    carteira_id = str(uuid.uuid4())
    areas_ant = org("cad.area_producao") if areas else None
    ja_gravadas = set() if areas_ant is None else set(zip(areas_ant["imovel_id"], areas_ant["geometria_wkt"]))
    novos = {"cad.produtor": [], "cad.imovel": [], "cad.produtor_imovel": [], "cad.documento_trazido": [],
             "cad.area_producao": []}
    itens, ids = [], {}
    for i, linha in df.iterrows():
        id_produtor, cod_car = _texto(linha.get("id_produtor")), _texto(linha.get("cod_car"))
        produtor_id = imovel_id = None
        if id_produtor:
            produtor_id = por_produtor.get(id_produtor)
            if produtor_id is None:
                produtor_id = por_produtor[id_produtor] = str(uuid.uuid4())
                numeros = somente_digitos(pd.Series([_texto(linha.get("documento"))], dtype="object"))
                novos["cad.produtor"].append({
                    "produtor_id": produtor_id, "organizacao_id": organizacao_id, "id_produtor": id_produtor,
                    "documento_hash": pseudonimizar(numeros, chave).iloc[0] if numeros.notna().iloc[0] else None,
                    "tipo_documento": tipo_documento(numeros).iloc[0], "criado_em": momento})
        if cod_car or (_texto(linha.get("lat")) and _texto(linha.get("lon"))):
            imovel_id = por_car.get(cod_car) if cod_car else None
            if imovel_id is None:
                imovel_id = str(uuid.uuid4())
                if cod_car:
                    por_car[cod_car] = imovel_id
                coordenada = lambda c: None if cod_car else _coordenada(linha.get(c))
                novos["cad.imovel"].append({
                    "imovel_id": imovel_id, "organizacao_id": organizacao_id, "cod_car": cod_car,
                    "lat": coordenada("lat"), "lon": coordenada("lon"), "criado_em": momento,
                    **{c: _texto(linha.get(c)) for c in EXTRAS_IMOVEL}})
                if produtor_id:
                    novos["cad.produtor_imovel"].append({"organizacao_id": organizacao_id,
                                                         "produtor_id": produtor_id, "imovel_id": imovel_id,
                                                         "vinculo": None})
            for tipo in INFORMADOS:
                if _texto(linha.get(tipo)):
                    novos["cad.documento_trazido"].append({
                        "documento_id": str(uuid.uuid4()), "organizacao_id": organizacao_id, "imovel_id": imovel_id,
                        "tipo": tipo, "valor": _texto(linha.get(tipo)), "informado_em": momento})
            area = areas.get(i) or {}
            if area.get("geometria") is not None and (imovel_id, area["geometria"].wkt) not in ja_gravadas:
                ja_gravadas.add((imovel_id, area["geometria"].wkt))
                novos["cad.area_producao"].append({
                    "area_id": str(uuid.uuid4()), "organizacao_id": organizacao_id, "imovel_id": imovel_id,
                    "commodity": sem_documento({"commodity": _texto(linha.get("commodity"))})["commodity"],
                    "origem": vetor.nome_sem_documento(f"planilha {Path(arquivo).name}: {area['arquivo']} "
                                                       f"({area['crs']})"),
                    "criado_em": momento, "geometria_wkt": area["geometria"].wkt})
        extras = sem_documento({k: _texto(v) for k, v in linha.items()
                                if k not in ("documento", "lat", "lon", "id_produtor", "cod_car", *INFORMADOS)
                                and _texto(v)})
        if extras.get("area_producao"):
            extras["area_producao"] = vetor.nome_sem_documento(extras["area_producao"])
        itens.append({"carteira_id": carteira_id, "organizacao_id": organizacao_id, "linha": int(i) + 2,
                      "produtor_id": produtor_id, "imovel_id": imovel_id, "problema_na_linha": problemas.get(i),
                      "extras_json": pd.Series(extras).to_json(force_ascii=False) if extras else None})
        ids[i] = {"produtor_id": produtor_id, "imovel_id": imovel_id}
    sha = hashlib.sha256(Path(arquivo).read_bytes()).hexdigest() if Path(arquivo).exists() else None
    _gravar("cad.carteira", [{"carteira_id": carteira_id, "organizacao_id": organizacao_id,
                              "arquivo_origem": vetor.nome_sem_documento(Path(arquivo).name), "sha256": sha,
                              "importada_em": momento,
                              "linhas": len(df), "linhas_com_problema": len(problemas)}], momento)
    for tabela, linhas in novos.items():
        _gravar(tabela, linhas, momento)
    _gravar("cad.carteira_item", itens, momento)
    return carteira_id, ids
