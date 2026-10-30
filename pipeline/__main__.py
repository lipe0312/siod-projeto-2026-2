"""Executa o pipeline: python -m pipeline [--fontes ...] [--desde AAAA-MM-DD] [--atualizar] [--verificar-prodes]
[--evidencia PASTA]"""

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline import config, relatorio
from pipeline.documentos import carregar_chave
from pipeline.fontes import ibama_embargos, inpe_deter, inpe_prodes, mte_lista_suja
from pipeline.municipios import carregar_referencia
from pipeline.validacao import ErroDeValidacao, ResultadoFonte

FONTES = ("ibama", "deter", "prodes", "lista_suja")
ARQ_PROCEDENCIA = config.DADOS_PROCESSADOS / "procedencia_fontes.json"
log = logging.getLogger("pipeline")


def _legivel(caminho: Path) -> str:
    return str(caminho.relative_to(config.RAIZ)) if caminho.is_relative_to(config.RAIZ) else str(caminho)


def atualizar_procedencia(resultados: list[ResultadoFonte], inicio: str) -> None:
    """Guarda entrada e saída da última execução bem-sucedida de cada fonte. O relatório de execução só traz as
    fontes da execução corrente; este arquivo junta todas (é o que o pré-diagnóstico cita na procedência)."""
    procedencia = json.loads(ARQ_PROCEDENCIA.read_text()) if ARQ_PROCEDENCIA.exists() else {}
    for r in resultados:
        if r.status == "ok":
            procedencia[r.fonte] = {"executado_em": inicio, "entrada": r.entrada, "saida": r.saida}
    ARQ_PROCEDENCIA.write_text(json.dumps(procedencia, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline de dados do projeto de SIOD.")
    parser.add_argument("--fontes", nargs="+", choices=FONTES, default=list(FONTES))
    parser.add_argument("--desde", default=config.DETER_DESDE_PADRAO, help="data inicial dos alertas DETER")
    parser.add_argument("--atualizar", action="store_true", help="baixa novamente os arquivos brutos")
    parser.add_argument("--verificar-prodes", action="store_true",
                        help="verifica a publicação do PRODES mesmo dentro do intervalo de verificação")
    parser.add_argument("--evidencia", type=Path, help="pasta onde copiar relatório e log desta execução")
    args = parser.parse_args(argv)

    inicio = datetime.now()
    carimbo = inicio.strftime("%Y%m%d_%H%M%S")
    arquivo_log = config.LOGS / f"pipeline_{carimbo}.log"
    relatorio.configurar_log(arquivo_log)
    comando = "python -m pipeline " + " ".join(argv if argv is not None else sys.argv[1:])
    log.info("Início: %s", comando.strip())
    hoje = pd.Timestamp(inicio)
    t0 = time.time()

    resultados: list[ResultadoFonte] = []

    def rodar(nome: str, tipo: str, funcao):
        try:
            resultado = funcao()
        except ErroDeValidacao as e:
            resultado = ResultadoFonte(nome, tipo, status="erro", mensagem=str(e))
            log.error("[%s] interrompida: %s", nome, e)
        except Exception as e:  # falha de rede, arquivo corrompido etc.
            resultado = ResultadoFonte(nome, tipo, status="erro", mensagem=f"{type(e).__name__}: {e}")
            log.exception("[%s] falhou", nome)
        resultados.append(resultado)
        return resultado

    chave = carregar_chave()
    ref = None
    if {"ibama", "deter"} & set(args.fontes):
        r_ibge = rodar("ibge_municipios", "API (JSON)", lambda: carregar_referencia(args.atualizar)[1])
        if r_ibge.status == "ok":
            ref = pd.read_parquet(config.DADOS_PROCESSADOS / "ibge_municipios.parquet")
    sem_referencia = "referência de municípios do IBGE indisponível"
    if "ibama" in args.fontes:
        if ref is None:
            resultados.append(ResultadoFonte("ibama_embargos", "tabular (CSV)", status="erro", mensagem=sem_referencia))
        else:
            rodar("ibama_embargos", "tabular (CSV)", lambda: ibama_embargos.executar(chave, ref, hoje, args.atualizar))
    if "deter" in args.fontes:
        if ref is None:
            resultados.append(ResultadoFonte("inpe_deter", "API (WFS/GeoJSON)", status="erro", mensagem=sem_referencia))
        else:
            rodar("inpe_deter", "API (WFS/GeoJSON)", lambda: inpe_deter.executar(ref, hoje, args.desde, args.atualizar))
    if "prodes" in args.fontes:
        rodar("inpe_prodes", "API (WFS/GeoJSON)",
              lambda: inpe_prodes.executar(hoje, args.atualizar, args.verificar_prodes))
    if "lista_suja" in args.fontes:
        rodar("mte_lista_suja", "documento (PDF)", lambda: mte_lista_suja.executar(chave, hoje, args.atualizar))

    status = "ok" if all(r.status == "ok" for r in resultados) else "erro"
    execucao = {"inicio": inicio.strftime("%Y-%m-%d %H:%M:%S"), "comando": comando.strip(),
                "duracao_segundos": round(time.time() - t0, 1), "status": status,
                "parametros": {"fontes": args.fontes, "desde": args.desde, "atualizar": args.atualizar,
                               "verificar_prodes": args.verificar_prodes}}
    arq_json, arq_md = relatorio.escrever(execucao, resultados, config.DADOS_PROCESSADOS, "relatorio_execucao")
    atualizar_procedencia(resultados, execucao["inicio"])
    log.info("Fim: status %s em %.1f s. Relatório: %s", status, execucao["duracao_segundos"], _legivel(arq_md))

    if args.evidencia:
        nome = f"execucao_{carimbo}"
        relatorio.escrever(execucao, resultados, args.evidencia, nome)
        for handler in log.handlers:
            handler.flush()
        shutil.copy(arquivo_log, args.evidencia / f"{nome}.log")
        log.info("Evidência gravada em %s", args.evidencia)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
