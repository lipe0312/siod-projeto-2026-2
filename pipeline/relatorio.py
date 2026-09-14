"""Log da execução e relatório final (JSON e Markdown)."""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from pipeline.validacao import ResultadoFonte


def configurar_log(arquivo: Path) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    raiz = logging.getLogger("pipeline")
    raiz.setLevel(logging.INFO)
    raiz.handlers.clear()
    for handler in (logging.StreamHandler(), logging.FileHandler(arquivo, encoding="utf-8")):
        handler.setFormatter(formato)
        raiz.addHandler(handler)


def _num(valor) -> str:
    return f"{valor:,}".replace(",", ".") if isinstance(valor, int) else "—"


def _tabela_validacoes(r: ResultadoFonte) -> list[str]:
    linhas = ["| Código | Verificação | Severidade | Tratamento | Verificados | Ocorrências |", "|---|---|---|---|---:|---:|"]
    for v in r.validacoes:
        linhas.append(f"| `{v.codigo}` | {v.descricao} | {v.severidade} | {v.tratamento} | {_num(v.verificados)} | {_num(v.ocorrencias)} |")
    return linhas


def escrever(execucao: dict, resultados: list[ResultadoFonte], pasta: Path, nome: str) -> tuple[Path, Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    arq_json, arq_md = pasta / f"{nome}.json", pasta / f"{nome}.md"
    arq_json.write_text(json.dumps({**execucao, "fontes": [asdict(r) for r in resultados]},
                                   indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md = [f"# Execução do pipeline — {execucao['inicio']}", "",
          f"Comando: `{execucao['comando']}`  ",
          f"Duração: {execucao['duracao_segundos']} s · Status geral: **{execucao['status']}**", "",
          "| Fonte | Tipo de dado | Status | Recebidos | Produzidos | Descartados | Com alerta |",
          "|---|---|---|---:|---:|---:|---:|"]
    for r in resultados:
        md.append(f"| {r.fonte} | {r.tipo_dado} | {r.status} | {_num(r.entrada.get('registros_recebidos'))} | "
                  f"{_num(r.saida.get('registros_produzidos'))} | {_num(r.saida.get('registros_descartados'))} | "
                  f"{_num(r.saida.get('registros_com_alerta'))} |")
    for r in resultados:
        md += ["", f"## {r.fonte}", ""]
        if r.mensagem:
            md += [f"**Falha:** {r.mensagem}", ""]
        entrada = {k: v for k, v in r.entrada.items() if k not in ("cabecalho_http",)}
        md += ["**Entrada**", "", "```json", json.dumps(entrada, indent=2, ensure_ascii=False, default=str), "```", "",
               "**Transformações**", ""]
        md += [f"{i}. {t}" for i, t in enumerate(r.transformacoes, 1)]
        md += ["", "**Validações**", ""] + _tabela_validacoes(r)
        saida = {k: v for k, v in r.saida.items() if k != "colunas"}
        md += ["", "**Saída**", "", "```json", json.dumps(saida, indent=2, ensure_ascii=False, default=str), "```"]
        if r.saida.get("colunas"):
            md += ["", "Colunas: " + ", ".join(f"`{c}`" for c in r.saida["colunas"])]
    arq_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    return arq_json, arq_md
