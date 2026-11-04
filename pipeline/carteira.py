"""Carteira: a planilha de uma cooperativa ou de um técnico (uma linha por imóvel) vira a lista de atendimento em
ordem de prioridade, com uma ficha de pré-diagnóstico por imóvel.

    python -m pipeline.carteira minha_carteira.xlsx [--saida pasta] [--sem-baixar-prodes]

Colunas da planilha (CSV ou XLSX; modelo em docs/modelos/carteira_modelo.csv):
- `id_produtor` (obrigatória): identificador da própria cooperativa, nunca o CPF;
- `cod_car`, ou `lat` e `lon` da sede ou da área de produção: um dos dois localiza o imóvel;
- `documento` (opcional): CPF ou CNPJ do titular. É pseudonimizado e nunca gravado; sem ele, a Lista Suja fica
  "não verificado" e o embargo é procurado só no polígono;
- `ccir`, `codigo_sigef`, `relatorio_ab_s` (opcionais): o que o produtor trouxe para os critérios 1, 2 e 8 e para a
  conferência com o AB+S (ADR 0012). Entram na saída como "informado", ainda sem conferência automática;
- as demais colunas (nome da área, commodity...) passam direto para a saída.

Saída: carteira.csv e carteira.html na pasta, e as fichas (HTML, MD, JSON) de cada imóvel. A ordem é
pendência > inconclusivo > indício > sem pendência; dentro de cada grupo, mais pendências primeiro, depois maior área.
As colunas `mudou` e `o_que_mudou` comparam cada imóvel com a execução anterior da mesma organização
(resultados.mudancas); sem cod_imovel ou sem execução anterior, a linha fica "sem comparação".
"""

import argparse
import logging
import sys
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

from pipeline import cadastro, config, prediagnostico, relatorio, resultados
from pipeline.documentos import cnpj_valido, cpf_valido, sem_documento

log = logging.getLogger("pipeline")

ORDEM = {"com pendência": 1, "inconclusivo": 2, "com indício": 3, "sem pendência nas fontes verificadas": 4}
INFORMADOS = ("ccir", "codigo_sigef", "relatorio_ab_s")
COLUNAS_SAIDA = ["prioridade", "id_produtor", "cod_car", "uf", "municipio", "area_ha", "resultado", "pendencias",
                 "indicios", "inconclusivos", "primeiro_encaminhamento", "mudou", "o_que_mudou", "documento_informado", *INFORMADOS, "ficha",
                 "problema_na_linha"]


def ler_planilha(caminho: Path) -> pd.DataFrame:
    df = (pd.read_excel(caminho, dtype=str) if caminho.suffix.lower() in (".xlsx", ".xls")
          else pd.read_csv(caminho, dtype=str, sep=None, engine="python", encoding="utf-8-sig"))
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _valor(linha: pd.Series, coluna: str) -> str | None:
    """Texto da célula, ou None se vazia (no pandas 3, a célula vazia vem como NaN, que é verdadeiro em Python)."""
    v = linha.get(coluna)
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return str(v).strip() or None


def problema(linha: pd.Series) -> str | None:
    """Motivo pelo qual a linha não pode ser consultada como está (None se pode)."""
    linha = pd.Series({k: _valor(linha, k) for k in linha.index}, dtype=object)
    if not linha.get("id_produtor"):
        return "sem id_produtor"
    tem_ponto = linha.get("lat") is not None and linha.get("lon") is not None
    if not linha.get("cod_car") and not tem_ponto:
        return "sem cod_car e sem lat/lon"
    if tem_ponto and not linha.get("cod_car"):
        try:
            lat, lon = float(str(linha["lat"]).replace(",", ".")), float(str(linha["lon"]).replace(",", "."))
        except ValueError:
            return "lat/lon não numéricos"
        if not (-34 <= lat <= 6 and -74 <= lon <= -28):
            return "lat/lon fora do Brasil (conferir se não estão trocados)"
    doc = "".join(ch for ch in str(linha.get("documento") or "") if ch.isdigit())
    if doc and not ((len(doc) == 11 and cpf_valido(doc)) or (len(doc) == 14 and cnpj_valido(doc))):
        return "documento com dígito verificador inválido"
    return None


def resumir(ficha: dict) -> dict:
    """Uma linha da carteira a partir da ficha."""
    criterios = ficha["criterios"]
    nomes = lambda s: "; ".join(c["criterio"] for c in criterios if c["situacao"] == s)
    pend = [c for c in criterios if c["situacao"] == "pendência"]
    inc = [c for c in criterios if c["situacao"] == "inconclusivo"]
    im = ficha["imovel"]
    return {"cod_car": im.get("cod_imovel"), "uf": im.get("uf"), "municipio": im.get("municipio"),
            "area_ha": round(im["area_geom_ha"], 1) if im.get("area_geom_ha") is not None else None,
            "resultado": ficha["resultado"]["situacao"], "pendencias": nomes("pendência"), "indicios": nomes("indício"),
            "inconclusivos": nomes("inconclusivo"),
            "primeiro_encaminhamento": (pend or inc or [{"encaminhamento": ""}])[0]["encaminhamento"],
            "_n_pendencias": len(pend)}


def processar(df: pd.DataFrame, pasta: Path, baixar_prodes: bool = True, consultar=prediagnostico.executar,
              execucao=None, ids: dict | None = None) -> pd.DataFrame:
    """Uma linha por imóvel, em ordem de prioridade. Com `execucao` (resultados.Execucao), cada ficha vai também para
    o esquema diag, ligada ao imóvel do cadastro (`ids`, de cadastro.importar_carteira)."""
    linhas = []
    for i, linha in df.iterrows():
        linha = pd.Series({k: _valor(linha, k) for k in df.columns}, dtype=object)
        base = sem_documento({k: linha.get(k) for k in df.columns if k not in ("documento", "lat", "lon")},
                             preservar=("id_produtor", "cod_car", *INFORMADOS))
        base["documento_informado"] = "sim" if linha.get("documento") else "não"
        motivo = problema(linha)
        if motivo:
            linhas.append({**base, "resultado": "inconclusivo", "problema_na_linha": motivo, "_n_pendencias": 0})
            continue
        lat = lon = None
        if not linha.get("cod_car"):
            lat, lon = (float(str(linha[c]).replace(",", ".")) for c in ("lat", "lon"))
        try:
            ficha = consultar(linha.get("cod_car"), lat, lon, linha.get("documento"), baixar_prodes=baixar_prodes)
        except Exception as e:  # serviço fora do ar etc.: a linha fica inconclusiva e a carteira segue
            log.exception("[carteira] linha %s (%s) falhou", i + 2, linha.get("id_produtor"))
            linhas.append({**base, "resultado": "inconclusivo", "problema_na_linha": f"{type(e).__name__}: {e}"[:200],
                           "_n_pendencias": 0})
            continue
        caminhos = prediagnostico.escrever(ficha, pasta / "fichas")
        resultado_id = execucao.acrescentar(ficha, imovel_id=(ids or {}).get(i, {}).get("imovel_id"),
                                            ficha_arquivo=f"fichas/{caminhos['html'].name}") if execucao else None
        linhas.append({**base, **resumir(ficha), "ficha": f"fichas/{caminhos['html'].name}",
                       "_resultado_id": resultado_id,
                       "problema_na_linha": None if ficha["imovel"].get("cod_imovel") else
                       ficha["criterios"][0]["evidencia"]})
    saida = pd.DataFrame(linhas)
    for coluna in [c for c in COLUNAS_SAIDA if c != "prioridade"]:
        if coluna not in saida:
            saida[coluna] = None
    saida["_ordem"] = saida["resultado"].map(ORDEM).fillna(2)
    saida = saida.sort_values(["_ordem", "_n_pendencias", "area_ha"], ascending=[True, False, False],
                              na_position="last", kind="stable").reset_index(drop=True)
    saida.insert(0, "prioridade", range(1, len(saida) + 1))
    if execucao and "_resultado_id" in saida:
        prioridade = dict(zip(saida["_resultado_id"], saida["prioridade"]))
        for r in execucao.resultados:
            r["prioridade"] = prioridade.get(r["resultado_id"])
    extras = [c for c in saida.columns if c not in COLUNAS_SAIDA and not c.startswith("_")]
    return saida.reindex(columns=[*COLUNAS_SAIDA, *extras])


def _texto(valor) -> str:
    """Texto da célula para o HTML ("" se vazia: NaN é verdadeiro em Python e quebraria o escape)."""
    return "" if valor is None or (not isinstance(valor, str) and pd.isna(valor)) else str(valor)


def _situacao(valor, faltando: str) -> str:
    return faltando if valor is None or pd.isna(valor) else str(valor)


def comparar(saida: pd.DataFrame, organizacao_id: str, execucao_id: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Preenche `mudou` (sim/não/vazio) e `o_que_mudou` comparando cada imóvel da carteira com a execução anterior da
    mesma organização. Chame depois de execucao.encerrar(): a execução atual precisa estar no lago. Devolve também o
    resumo para o topo do HTML: primeira execução da organização, quantos mudaram e desde quando."""
    saida = saida.copy()
    comparavel = saida["problema_na_linha"].isna() & saida["cod_car"].notna()
    cods = set(saida.loc[comparavel, "cod_car"])
    datas = resultados.anteriores(organizacao_id, cods)
    textos = {}
    for cod, grupo in resultados.mudancas(organizacao_id, cods).groupby("cod_imovel", sort=False):
        texto = "; ".join(f"{_situacao(m.criterio, m.chave)}: {_situacao(m.situacao_anterior, '(não avaliado)')} → "
                          f"{_situacao(m.situacao_atual, '(não avaliado)')}" for m in grupo.itertuples())
        textos[cod] = sem_documento({"o_que_mudou": texto})["o_que_mudou"]
    def marca(ok, cod):
        if not ok:
            return None, "sem comparação"
        if cod not in datas.index:
            return None, "sem comparação (primeira execução do imóvel)"
        return ("sim", textos[cod]) if cod in textos else ("não", None)

    marcas = [marca(ok, cod) for ok, cod in zip(comparavel, saida["cod_car"])]
    saida["mudou"] = [m for m, _ in marcas]
    saida["o_que_mudou"] = [t for _, t in marcas]
    mudou = saida["mudou"].tolist()
    desde = datas.max() if len(datas) else None
    return saida, {"primeira": datas.empty and not resultados.ha_execucao_anterior(organizacao_id, execucao_id),
                   "comparados": len(datas), "mudaram": mudou.count("sim"),
                   "desde": None if desde is None or pd.isna(desde) else pd.Timestamp(desde)}


def _faixa_mudancas(comparacao: dict | None) -> str:
    if comparacao is None:
        return ""
    if comparacao["primeira"]:
        texto = "Primeira execução, sem comparação: no próximo mês esta faixa mostra o que mudou."
    elif not comparacao["comparados"]:
        texto = "Nenhum imóvel desta planilha estava em uma execução anterior: sem comparação."
    else:
        n = comparacao["mudaram"]
        texto = (f"<b>{n} {'imóvel mudou' if n == 1 else 'imóveis mudaram'} desde "
                 f"{comparacao['desde']:%d/%m/%Y}</b> (execução anterior), entre {comparacao['comparados']} comparados."
                 + (" Linhas marcadas com ↻." if n else ""))
    return f'<section class="aviso mudancas">{texto}</section>'


def html(saida: pd.DataFrame, origem: str, comparacao: dict | None = None) -> str:
    from pipeline.ficha_html import CSS, _badge, _td

    contagem = saida["resultado"].value_counts()
    placar = "".join(f'<div><b>{int(contagem.get(s, 0))}</b><br><span class="mut">{escape(s)}</span></div>'
                     for s in ORDEM)
    linhas = []
    for r in saida.itertuples(index=False):
        ficha = f'<a href="{escape(r.ficha)}">ficha</a>' if isinstance(r.ficha, str) else ""
        o_que = (escape(_texto(r.pendencias)) or escape(_texto(r.inconclusivos)) or escape(_texto(r.indicios))
                 or ('<span class="mut">nada nas fontes verificadas</span>'))
        if isinstance(r.problema_na_linha, str):
            o_que += f'<div class="cobertura">⚠ {escape(r.problema_na_linha)}</div>'
        mudou = getattr(r, "mudou", None) == "sim"
        if mudou:
            o_que += f'<div class="mudou">↻ mudou: {escape(_texto(r.o_que_mudou))}</div>'
        linhas.append(('<tr class="mudou">' if mudou else "<tr>") + _td(str(r.prioridade), True) +
                      _td(f"<b>{escape(str(r.id_produtor))}</b>"
                          f'<div class="mono mut">{escape(_texto(r.cod_car))}</div>') +
                      _td(escape(f"{_texto(r.municipio)}/{_texto(r.uf)}".strip("/"))) +
                      _td("" if pd.isna(r.area_ha) else f"{r.area_ha:,.1f}".replace(",", "."), True) +
                      _td(_badge(r.resultado)) + _td(o_que) + _td(escape(_texto(r.primeiro_encaminhamento))) +
                      _td(ficha) + "</tr>")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Carteira priorizada</title>
<style>{CSS}
tr.mudou td:first-child{{box-shadow:inset 4px 0 var(--inc)}}div.mudou{{font-size:12.5px;color:var(--inc);margin-top:6px}}
</style></head><body><main><div class="eyebrow">Carteira</div><h1>Quem atender primeiro</h1>
<p class="mut">Planilha {escape(origem)}, {len(saida)} imóveis, gerada em {datetime.now():%d/%m/%Y %H:%M}. Pré-diagnóstico
com fontes públicas: não é atestado de conformidade. O CPF/CNPJ não é gravado.</p>
{_faixa_mudancas(comparacao)}
<section class="card"><div class="placar">{placar}</div></section>
<section class="card"><div class="tabela"><table><thead><tr><th>#</th><th>Produtor / CAR</th><th>Município</th>
<th>ha</th><th>Resultado</th><th>O que apareceu</th><th>Primeiro passo</th><th></th></tr></thead>
<tbody>{''.join(linhas)}</tbody></table></div></section></main></body></html>"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Carteira priorizada a partir de uma planilha de imóveis.")
    parser.add_argument("planilha", type=Path, help="CSV ou XLSX com id_produtor e cod_car ou lat/lon")
    parser.add_argument("--saida", type=Path, help="pasta de saída (padrão: data/saidas/carteiras/<nome>/<AAAA-MM>)")
    parser.add_argument("--organizacao", help="nome da cooperativa ou empresa no cadastro (padrão: nome da planilha)")
    parser.add_argument("--sem-baixar-prodes", action="store_true")
    args = parser.parse_args(argv)
    relatorio.configurar_log(config.LOGS / f"carteira_{datetime.now():%Y%m%d_%H%M%S}.log")
    pasta = args.saida or config.SAIDAS / "carteiras" / args.planilha.stem / f"{datetime.now():%Y-%m}"
    pasta.mkdir(parents=True, exist_ok=True)
    planilha = ler_planilha(args.planilha)
    # Cadastro (cad) e resultado (diag) no lago: é o que permite ver, no mês seguinte, o que mudou (ADR 0017).
    organizacao_id = cadastro.organizacao(args.organizacao or args.planilha.stem)
    problemas = {i: m for i, linha in planilha.iterrows() if (m := problema(
        pd.Series({k: _valor(linha, k) for k in planilha.columns}, dtype=object)))}
    carteira_id, ids = cadastro.importar_carteira(planilha, organizacao_id, args.planilha, problemas)
    execucao = resultados.Execucao("carteira", organizacao_id, carteira_id,
                                   "python -m pipeline.carteira " + " ".join(argv if argv is not None else sys.argv[1:]))
    saida = processar(planilha, pasta, not args.sem_baixar_prodes, execucao=execucao, ids=ids)
    execucao.encerrar()
    # Só depois de encerrar(): a execução atual precisa estar no lago para ser a "atual" da comparação.
    saida, comparacao = comparar(saida, organizacao_id, execucao.id)
    saida.to_csv(pasta / "carteira.csv", index=False)
    (pasta / "carteira.html").write_text(html(saida, args.planilha.name, comparacao), encoding="utf-8")
    log.info("Carteira: %d imóveis; %s", len(saida), pasta / "carteira.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
