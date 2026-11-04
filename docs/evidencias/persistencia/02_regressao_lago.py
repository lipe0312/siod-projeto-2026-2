"""Regressão do lago: os 17 imóveis da demonstração lidos do lago dão a mesma situação, critério a critério, que as
fichas da Atividade 04 (docs/evidencias/atividade-04/prediagnostico/), lidas de data/processed.

Roda da raiz, depois de `python -m pipeline.prediagnostico --demo --sem-baixar-prodes`:

    .venv/bin/python docs/evidencias/persistencia/02_regressao_lago.py

Compara com a última execução de demonstração gravada em diag (resultado e critérios). Grava 02_regressao_lago.json
e .md ao lado. Sai com código 1 se algum imóvel mudar.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline.armazenamento import lago  # noqa: E402

PASTA = Path(__file__).parent
ANTES = Path("docs/evidencias/atividade-04/prediagnostico")


def main() -> int:
    execucoes = lago.ler("diag.execucao")
    ultima = execucoes[execucoes["tipo"] == "demonstracao"].sort_values("iniciada_em").iloc[-1]
    res = lago.ler("diag.resultado_imovel")
    res = res[res["execucao_id"] == ultima["execucao_id"]]
    crit = lago.ler("diag.criterio")
    crit = crit[crit["resultado_id"].isin(res["resultado_id"])].merge(res[["resultado_id", "cod_imovel"]])
    depois = {cod: dict(zip(g["chave"], g["situacao"])) for cod, g in crit.groupby("cod_imovel")}
    resultado_depois = dict(zip(res["cod_imovel"], res["situacao"]))

    linhas = []
    for arquivo in sorted(ANTES.glob("*.json")):
        ficha = json.loads(arquivo.read_text(encoding="utf-8"))
        cod = ficha["imovel"]["cod_imovel"]
        antes = {c["chave"]: c["situacao"] for c in ficha["criterios"]}
        diferentes = {k: [v, depois.get(cod, {}).get(k)] for k, v in antes.items() if depois.get(cod, {}).get(k) != v}
        linhas.append({"cod_imovel": cod, "resultado_antes": ficha["resultado"]["situacao"],
                       "resultado_depois": resultado_depois.get(cod), "criterios_diferentes": diferentes})
    iguais = sum(1 for l in linhas if not l["criterios_diferentes"] and l["resultado_antes"] == l["resultado_depois"])
    saida = {"execucao_id": ultima["execucao_id"], "execucao_em": str(ultima["iniciada_em"]),
             "imoveis": len(linhas), "iguais": iguais, "detalhe": linhas}
    (PASTA / "02_regressao_lago.json").write_text(json.dumps(saida, indent=2, ensure_ascii=False), encoding="utf-8")
    md = ["# Regressão do lago: demonstração dos 17 imóveis", "",
          f"Execução `{saida['execucao_id']}` de {saida['execucao_em']}: **{iguais} de {len(linhas)} imóveis iguais** "
          "às fichas da Atividade 04, critério a critério.", "",
          "| Imóvel | Resultado antes | Resultado depois | Critérios diferentes |", "|---|---|---|---|"]
    md += [f"| `{l['cod_imovel']}` | {l['resultado_antes']} | {l['resultado_depois']} | "
           f"{', '.join(f'{k}: {a} → {d}' for k, (a, d) in l['criterios_diferentes'].items()) or '—'} |" for l in linhas]
    (PASTA / "02_regressao_lago.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{iguais} de {len(linhas)} imóveis iguais")
    return 0 if iguais == len(linhas) else 1


if __name__ == "__main__":
    sys.exit(main())
