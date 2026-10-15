"""Download de arquivos brutos com registro de procedência."""

import gzip
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from pipeline import config

log = logging.getLogger("pipeline")

TENTATIVAS = 3
TIMEOUT = (30, 120)  # conexão, e espera máxima entre blocos recebidos


class DownloadIncompleto(Exception):
    """Arquivo recebido com tamanho diferente do informado pelo servidor."""


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _baixar_uma_vez(url: str, temporario: Path) -> dict:
    with requests.get(url, stream=True, timeout=TIMEOUT, headers={"User-Agent": config.USER_AGENT}) as r:
        r.raise_for_status()
        cabecalho = {k: r.headers.get(k) for k in ("Content-Type", "Last-Modified", "Content-Length")}
        with open(temporario, "wb") as f:
            for bloco in r.iter_content(chunk_size=1 << 20):
                f.write(bloco)
    esperado = cabecalho["Content-Length"]
    recebido = temporario.stat().st_size
    if esperado and r.headers.get("Content-Encoding") is None and int(esperado) != recebido:
        raise DownloadIncompleto(f"recebidos {recebido} de {esperado} bytes")
    return cabecalho


def consultar(url: str, destino: Path, parametros: dict | None = None, sessao: requests.Session | None = None,
              atualizar: bool = False, tratar=None, tentativas: int = 4, pausa: float = 0) -> tuple[bytes, dict]:
    """GET com cache, para as fontes consultadas sob demanda.

    Se `destino` já existe (e não se pediu `atualizar`), devolve o que está gravado sem ir à rede. Senão, faz a
    requisição e grava a resposta (compactada se `destino` termina em .gz) e o `.meta.json` ao lado, com URL,
    parâmetros, data UTC, status HTTP e SHA-256. Qualquer status HTTP é gravado: quem chama decide o que significa.
    `tratar(conteudo) -> (conteudo, nota)` é aplicado antes de gravar (ex.: pseudonimizar documentos).
    Só falha de rede é repetida. `pausa` (segundos) é respeitada depois de cada ida à rede.
    """
    meta_caminho = destino.parent / (destino.name.removesuffix(".gz").rsplit(".", 1)[0] + ".meta.json")
    if destino.exists() and meta_caminho.exists() and not atualizar:
        conteudo = destino.read_bytes()
        return (gzip.decompress(conteudo) if destino.suffix == ".gz" else conteudo), json.loads(meta_caminho.read_text())
    cliente = sessao or requests
    for tentativa in range(1, tentativas + 1):
        try:
            consultado_em = datetime.now(timezone.utc).isoformat(timespec="seconds")
            inicio = time.perf_counter()
            r = cliente.get(url, params=parametros, timeout=TIMEOUT, headers={"User-Agent": config.USER_AGENT})
            break
        except requests.RequestException as e:
            if tentativa == tentativas:
                raise
            log.warning("Falha na consulta a %s (%s); nova tentativa em %ds", url, type(e).__name__, 5 * tentativa)
            time.sleep(5 * tentativa)
    conteudo, nota = tratar(r.content) if tratar else (r.content, None)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(gzip.compress(conteudo, mtime=0) if destino.suffix == ".gz" else conteudo)
    meta = {"url": url, "parametros": parametros or {}, "url_completa": r.url, "consultado_em_utc": consultado_em,
            "status_http": r.status_code, "segundos": round(time.perf_counter() - inicio, 3),
            "content_type": r.headers.get("Content-Type"), "tamanho_bytes": len(conteudo),
            "sha256": hashlib.sha256(conteudo).hexdigest()}
    if nota:
        meta["tratamento_antes_de_gravar"] = nota
    meta_caminho.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    time.sleep(pausa)
    return conteudo, meta


def baixar(url: str, destino: Path, atualizar: bool = False) -> dict:
    """Baixa `url` para `destino` se ainda não existir (ou se `atualizar`) e devolve a procedência."""
    meta_caminho = destino.with_suffix(".meta.json")
    if atualizar or not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(destino.suffix + ".parcial")
        for tentativa in range(1, TENTATIVAS + 1):
            log.info("Baixando %s (tentativa %d de %d)", url, tentativa, TENTATIVAS)
            try:
                cabecalho = _baixar_uma_vez(url, temporario)
                break
            except (requests.RequestException, DownloadIncompleto) as e:
                temporario.unlink(missing_ok=True)
                if tentativa == TENTATIVAS:
                    raise
                log.warning("Download falhou (%s: %s); nova tentativa em %ds", type(e).__name__, e, 10 * tentativa)
                time.sleep(10 * tentativa)
        temporario.replace(destino)
        meta = {"url": url, "baixado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "cabecalho_http": cabecalho}
    else:
        meta = json.loads(meta_caminho.read_text()) if meta_caminho.exists() else {"url": url}
        log.info("Reutilizando arquivo já baixado: %s", destino.relative_to(config.RAIZ))
    meta["sha256"] = sha256(destino)
    meta["tamanho_bytes"] = destino.stat().st_size
    meta_caminho.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return {"arquivo": str(destino.relative_to(config.RAIZ)), **meta}
