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
"""

import argparse
import logging
import sys
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

from pipeline import config, prediagnostico, relatorio
from pipeline.documentos import cpf_valido, cnpj_valido

log = logging.getLogger("pipeline")

ORDEM = {"com pendência": 1, "inconclusivo": 2, "com indício": 3, "sem pendência nas fontes verificadas": 4}
INFORMADOS = ("ccir", "codigo_sigef", "relatorio_ab_s")
COLUNAS_SAIDA = ["prioridade", "id_produtor", "cod_car", "uf", "municipio", "area_ha", "resultado", "pendencias",
                 "indicios", "inconclusivos", "primeiro_encaminhamento", "documento_informado", *INFORMADOS, "ficha",
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


def processar(df: pd.DataFrame, pasta: Path, baixar_prodes: bool = True, consultar=prediagnostico.executar) -> pd.DataFrame:
    linhas = []
    for i, linha in df.iterrows():
        linha = pd.Series({k: _valor(linha, k) for k in df.columns}, dtype=object)
        base = {k: linha.get(k) for k in df.columns if k not in ("documento", "lat", "lon")}
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
        linhas.append({**base, **resumir(ficha), "ficha": f"fichas/{caminhos['html'].name}",
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
    extras = [c for c in saida.columns if c not in COLUNAS_SAIDA and not c.startswith("_")]
    return saida.reindex(columns=[*COLUNAS_SAIDA, *extras])


def html(saida: pd.DataFrame, origem: str) -> str:
    from pipeline.ficha_html import CSS, _badge, _td

    contagem = saida["resultado"].value_counts()
    placar = "".join(f'<div><b>{int(contagem.get(s, 0))}</b><br><span class="mut">{escape(s)}</span></div>'
                     for s in ORDEM)
    linhas = []
    for r in saida.itertuples(index=False):
        ficha = f'<a href="{escape(r.ficha)}">ficha</a>' if isinstance(r.ficha, str) else ""
        o_que = (escape(r.pendencias or "") or escape(r.inconclusivos or "") or escape(r.indicios or "")
                 or ('<span class="mut">nada nas fontes verificadas</span>'))
        if isinstance(r.problema_na_linha, str):
            o_que += f'<div class="cobertura">⚠ {escape(r.problema_na_linha)}</div>'
        linhas.append("<tr>" + _td(str(r.prioridade), True) + _td(f"<b>{escape(str(r.id_produtor))}</b>"
                      f'<div class="mono mut">{escape(str(r.cod_car or ""))}</div>') +
                      _td(escape(f"{r.municipio or ''}/{r.uf or ''}".strip("/"))) +
                      _td("" if pd.isna(r.area_ha) else f"{r.area_ha:,.1f}".replace(",", "."), True) +
                      _td(_badge(r.resultado)) + _td(o_que) + _td(escape(r.primeiro_encaminhamento or "")) +
                      _td(ficha) + "</tr>")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Carteira priorizada</title>
<style>{CSS}</style></head><body><main><div class="eyebrow">Carteira</div><h1>Quem atender primeiro</h1>
<p class="mut">Planilha {escape(origem)}, {len(saida)} imóveis, gerada em {datetime.now():%d/%m/%Y %H:%M}. Pré-diagnóstico
com fontes públicas: não é atestado de conformidade. O CPF/CNPJ não é gravado.</p>
<section class="card"><div class="placar">{placar}</div></section>
<section class="card"><div class="tabela"><table><thead><tr><th>#</th><th>Produtor / CAR</th><th>Município</th>
<th>ha</th><th>Resultado</th><th>O que apareceu</th><th>Primeiro passo</th><th></th></tr></thead>
<tbody>{''.join(linhas)}</tbody></table></div></section></main></body></html>"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Carteira priorizada a partir de uma planilha de imóveis.")
    parser.add_argument("planilha", type=Path, help="CSV ou XLSX com id_produtor e cod_car ou lat/lon")
    parser.add_argument("--saida", type=Path, help="pasta de saída (padrão: data/processed/carteiras/<nome>)")
    parser.add_argument("--sem-baixar-prodes", action="store_true")
    args = parser.parse_args(argv)
    relatorio.configurar_log(config.LOGS / f"carteira_{datetime.now():%Y%m%d_%H%M%S}.log")
    pasta = args.saida or config.DADOS_PROCESSADOS / "carteiras" / args.planilha.stem
    pasta.mkdir(parents=True, exist_ok=True)
    saida = processar(ler_planilha(args.planilha), pasta, not args.sem_baixar_prodes)
    saida.to_csv(pasta / "carteira.csv", index=False)
    (pasta / "carteira.html").write_text(html(saida, args.planilha.name), encoding="utf-8")
    log.info("Carteira: %d imóveis; %s", len(saida), pasta / "carteira.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
