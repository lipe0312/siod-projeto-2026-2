"""Uma consulta do console: confere a entrada, roda o pré-diagnóstico numa thread e guarda o estado para o navegador.

O documento (CPF/CNPJ) só existe aqui como argumento da chamada: não entra no estado da consulta, no log nem em
arquivo. O que fica é `documento_hash` encurtado (pipeline.documentos), para o técnico ver que virou código.
"""

import logging
import re
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from pipeline import config, prediagnostico, resultados, vetor
from pipeline.documentos import (FORMATO_CPF_CNPJ, OMITIDO, carregar_chave, cnpj_valido, cpf_valido, pseudonimizar,
                                 somente_digitos)
from pipeline.fontes.sicar import FORMATO_CODIGO

log = logging.getLogger("pipeline.console")

TAMANHO_MAXIMO_AREA = 2 * 1024 * 1024  # o KML/GeoJSON vem como texto num POST JSON
EXTENSOES_AREA = (".kml", ".geojson", ".json")
COMMODITIES = ("café", "gado", "outra")
COMANDO = "console"
GUARDAR = 20  # consultas antigas que o servidor ainda responde (o resto sai da memória)


class EntradaInvalida(ValueError):
    """Entrada recusada; a mensagem vai para a tela e nunca repete o documento."""


class ChaveIndisponivel(RuntimeError):
    """A chave de pseudonimização não pôde ser lida: sem ela o documento não vira código, e a consulta não começa."""


def pasta_saida() -> Path:
    """data/saidas/console/ (lida na hora: os testes trocam config.SAIDAS)."""
    return config.SAIDAS / "console"


def _sem_documento(texto: str) -> str:
    return FORMATO_CPF_CNPJ.sub(OMITIDO, str(texto))


def _numero(valor, nome: str, minimo: float, maximo: float) -> float:
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise EntradaInvalida(f"{nome} não é um número") from None
    if not minimo <= numero <= maximo:
        raise EntradaInvalida(f"{nome} fora do intervalo ({minimo} a {maximo})")
    return numero


def _area(area: dict | None) -> dict | None:
    """Área de produção enviada como texto: o mesmo leitor da carteira (vetor.ler_area_producao), num arquivo
    temporário que é apagado em seguida. Arquivo ilegível não derruba a consulta: vira o motivo na ficha."""
    if area in (None, "", {}):
        return None
    if not isinstance(area, dict):
        raise EntradaInvalida("área de produção mal formada (envie nome e texto do arquivo)")
    if not area.get("texto"):
        return None
    nome = Path(str(area.get("nome") or "area").replace("\\", "/")).name
    extensao = Path(nome).suffix.lower()
    if extensao not in EXTENSOES_AREA:
        raise EntradaInvalida("área de produção: use um arquivo .kml, .geojson ou .json")
    texto = str(area["texto"])
    if len(texto.encode("utf-8")) > TAMANHO_MAXIMO_AREA:
        raise EntradaInvalida("área de produção com mais de 2 MB")
    arquivo = vetor.nome_sem_documento(nome)
    with tempfile.TemporaryDirectory(prefix="agrovalid-console-") as pasta:
        caminho = Path(pasta) / f"area{extensao}"
        caminho.write_text(texto, encoding="utf-8")
        try:
            geometria, crs = vetor.ler_area_producao(caminho)
        except vetor.AreaIlegivel as e:
            return {"geometria": None, "arquivo": arquivo, "crs": None, "motivo": vetor.nome_sem_documento(str(e))}
    return {"geometria": geometria, "arquivo": arquivo, "crs": crs, "motivo": None}


def validar(dados: dict) -> dict:
    """Pedido do navegador → argumentos de prediagnostico.executar (+ commodity e hash encurtado do documento)."""
    if not isinstance(dados, dict):
        raise EntradaInvalida("pedido mal formado")
    car = str(dados.get("car") or "").strip().upper()
    lat, lon = dados.get("lat"), dados.get("lon")
    if car:
        if not re.fullmatch(FORMATO_CODIGO, car):
            raise EntradaInvalida("código do CAR fora do formato UF-IBGE-32 hexadecimais "
                                  "(ex.: MG-3148103-seguido de 32 letras e números)")
        lat = lon = None
    elif lat not in (None, "") and lon not in (None, ""):
        lat, lon = _numero(lat, "latitude", -34.0, 6.0), _numero(lon, "longitude", -74.0, -28.0)
        car = None
    else:
        raise EntradaInvalida("informe o código do CAR ou a latitude e a longitude da sede")

    documento, documento_curto = None, None
    bruto = str(dados.get("documento") or "").strip()
    if bruto:
        digitos = re.sub(r"\D", "", bruto)
        if not (cpf_valido(digitos) or cnpj_valido(digitos)):
            raise EntradaInvalida("CPF ou CNPJ com dígito verificador inválido")
        documento = digitos
        try:
            chave = carregar_chave()
        except (OSError, UnicodeDecodeError, ValueError) as e:
            raise ChaveIndisponivel(f"a chave de pseudonimização não pôde ser lida ({type(e).__name__}); confira "
                                    f"{config.CHAVE_ENV} ou o arquivo da chave em data/") from None
        documento_curto = pseudonimizar(somente_digitos(pd.Series([digitos])), chave).iloc[0][:12]

    commodity = dados.get("commodity") or None
    if commodity is not None and commodity not in COMMODITIES:
        raise EntradaInvalida("commodity: escolha café, gado ou outra")
    return {"cod_imovel": car, "lat": lat, "lon": lon, "documento": documento, "area_producao": _area(dados.get("area")),
            "commodity": commodity, "documento_curto": documento_curto}


# ---------------------------------------------------------------------------------------------------------------
# Etapas mostradas na tela (derivadas da ficha: executar ainda não avisa o progresso)
# ---------------------------------------------------------------------------------------------------------------

ETAPAS = ("SICAR", "PRODES da UF", "IBAMA", "DETER", "Lista Suja", "Áreas protegidas")
PROTEGIDAS = {"terra_indigena": "terra indígena", "quilombola": "quilombola", "unidade_conservacao": "UC"}


def _tem_lote_deter(ficha: dict) -> bool:
    """O lote do DETER aparece na procedência quando python -m pipeline o carregou (prediagnostico._procedencia_lote)."""
    return any(str(p.get("fonte", "")).startswith("INPE DETER") for p in ficha.get("procedencia") or [])


def _estado(situacao: str | None) -> str:
    """ok = fonte consultada (achou ou não); inco = não respondeu ou faltou dado; nao = não cruzada."""
    return {"inconclusivo": "inco", "não verificado": "nao", None: "nao"}.get(situacao, "ok")


def _curto(texto: str, limite: int = 140) -> str:
    texto = _sem_documento(texto or "").strip()
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _ha(valor) -> str:
    try:
        return f"{float(valor):.1f}".replace(".", ",") + " ha"
    except (TypeError, ValueError):
        return "área não informada"


def etapas(ficha: dict) -> list[dict]:
    """Uma linha por fonte, com o que achou. Sem imóvel localizado, as outras ficam como não cruzadas."""
    crit = {c["chave"]: c for c in ficha.get("criterios", [])}
    im = ficha.get("imovel") or {}
    car = crit.get("car", {})
    if not im.get("cod_imovel"):
        nao = "não cruzado: falta o imóvel no SICAR"
        return [{"nome": "SICAR", "estado": "inco", "texto": _curto(car.get("evidencia", "imóvel não localizado"))},
                *({"nome": n, "estado": "nao", "texto": nao} for n in ETAPAS[1:])]
    evid = ficha.get("evidencias") or {}
    n = {k: len(v) for k, v in evid.items() if v is not None}
    status = f"{im.get('status_texto', '')}".strip().lower() or "situação não informada"
    linhas = [{"nome": "SICAR", "estado": "ok",
               "texto": f"imóvel localizado: {_ha(im.get('area_geom_ha'))}, {status}, {im.get('municipio', '')}/"
                        f"{im.get('uf', '')}"}]

    desm = crit.get("desmatamento", {})
    prodes = (ficha.get("consulta") or {}).get("prodes") or {}
    if prodes.get("origem") == "falhou" or desm.get("situacao") == "inconclusivo":
        linhas.append({"nome": "PRODES da UF", "estado": "inco", "texto": _curto(desm.get("evidencia", ""))})
        linhas.append({"nome": "DETER", "estado": "inco", "texto": "alertas sem o PRODES para confirmar"})
    else:  # aviso de cobertura (bioma sem DETER, área não lida): a fonte respondeu, mas não cobre tudo (ADR 0013)
        aviso = desm.get("aviso")
        ano = prodes.get("ultimo_ano_do_imovel")
        p = n.get("prodes", 0)
        texto = (f"partição {im.get('uf', '')} lida" + (f" (até {ano})" if ano else "") + ", "
                 + (f"{p} polígono(s) no imóvel" if p else "nenhum polígono no imóvel"))
        linhas.append({"nome": "PRODES da UF", "estado": "inco" if aviso else "ok",
                       "texto": _curto(f"{texto}; atenção: {aviso}", 220) if aviso else texto})
        a = n.get("alertas", 0)
        texto = f"{a} alerta(s) no imóvel" if a else "nenhum alerta no imóvel"
        if not _tem_lote_deter(ficha):
            linhas.append({"nome": "DETER", "estado": "inco",
                           "texto": "lote do DETER não carregado; rodar python -m pipeline --fontes deter"})
        else:
            linhas.append({"nome": "DETER", "estado": "inco" if aviso else "ok",
                           "texto": _curto(f"{texto}; atenção: {aviso}", 220) if aviso else texto})
    linhas.insert(2, {"nome": "IBAMA", "estado": _estado(crit.get("embargo", {}).get("situacao")),
                      "texto": _curto(crit.get("embargo", {}).get("evidencia", ""))})
    ls = crit.get("lista_suja", {})
    linhas.append({"nome": "Lista Suja", "estado": _estado(ls.get("situacao")), "texto": _curto(ls.get("evidencia", ""))})
    prot = [crit[k] for k in PROTEGIDAS if k in crit]
    achados = [f"{PROTEGIDAS[c['chave']]}: {c['evidencia']}" for c in prot if c["situacao"] != "sem ocorrência"]
    incompleto = any(c["situacao"] in ("inconclusivo", "não verificado") for c in prot)
    estado = "inco" if incompleto or len(prot) < len(PROTEGIDAS) else "ok"
    linhas.append({"nome": "Áreas protegidas", "estado": estado,
                   "texto": _curto("; ".join(achados)) if achados else "nenhuma sobreposição"})
    return linhas


# ---------------------------------------------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------------------------------------------

def _motivo(e: Exception) -> str:
    if isinstance(e, requests.RequestException):
        return (f"SICAR fora do ar ou sem resposta agora ({type(e).__name__}); a consulta não foi concluída. "
                "Tente de novo em alguns minutos")
    return f"A consulta não terminou ({type(e).__name__}: {_curto(str(e), 160)}). Tente de novo"


def _motivo_inconclusivo(ficha: dict) -> str | None:
    if ficha["resultado"]["situacao"] != "inconclusivo":
        return None
    c = next((c for c in ficha["criterios"] if c["situacao"] == "inconclusivo"), None)
    return _curto(c["evidencia"], 300) if c else ficha["resultado"].get("resumo")


def _nome_unico(caminhos: dict[str, Path], ficha: dict, ident: str) -> dict[str, Path]:
    """Ficha sem CAR sai do pipeline como inconclusivo_<data>; no console ganha o id da consulta, para que dois
    inconclusivos no mesmo dia não gravem um por cima do outro."""
    if (ficha.get("imovel") or {}).get("cod_imovel"):
        return caminhos
    novos = {}
    for ext, caminho in caminhos.items():
        novos[ext] = caminho.with_name(f"{caminho.stem}_{ident[:12]}{caminho.suffix}")
        caminho.replace(novos[ext])
    return novos


class Consultas:
    """Uma consulta por vez (o trabalho é o da linha de comando, ~2 s por imóvel). O estado fica em memória."""

    def __init__(self, executar: Callable[..., dict] | None = None):
        self.executar = executar or prediagnostico.executar
        self._trava = threading.Lock()
        self._em_curso: str | None = None
        self.estados: dict[str, dict] = {}

    def iniciar(self, entrada: dict, sincrono: bool = False) -> str:
        with self._trava:
            if self._em_curso and self.estados[self._em_curso]["estado"] == "rodando":
                raise RuntimeError("já há uma consulta em andamento; espere ela terminar")
            ident = uuid.uuid4().hex
            self._em_curso = ident
            self.estados[ident] = {"id": ident, "estado": "rodando", "inicio": time.monotonic(),
                                   "iniciada_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   "alvo": entrada["cod_imovel"] or f"{entrada['lat']}, {entrada['lon']}",
                                   "documento_curto": entrada["documento_curto"],
                                   "area": bool(entrada["area_producao"]), "commodity": entrada["commodity"]}
            for velho in list(self.estados)[:-GUARDAR]:
                self.estados.pop(velho, None)
        args = {k: entrada[k] for k in ("cod_imovel", "lat", "lon", "documento", "area_producao")}
        trabalho = threading.Thread(target=self._rodar, args=(ident, args, entrada["commodity"]), daemon=True)
        trabalho.start()
        if sincrono:
            trabalho.join()
        return ident

    def _rodar(self, ident: str, args: dict, commodity: str | None) -> None:
        estado = self.estados[ident]
        inicio = time.monotonic()
        try:
            self._consultar(ident, estado, args, commodity, inicio)
        except Exception as e:  # noqa: BLE001 — nada deixa a consulta presa em "rodando"
            log.error("Consulta %s: %s", ident[:8], _sem_documento(f"{type(e).__name__}: {e}")[:300])
            estado.update(estado="erro", tempo_s=round(time.monotonic() - inicio, 1),
                          erro=f"A consulta não terminou ({type(e).__name__}). Tente de novo")
        finally:
            args.pop("documento", None)
            if estado["estado"] == "rodando":
                estado.update(estado="erro", erro="A consulta não terminou. Tente de novo")
            with self._trava:
                if self._em_curso == ident:
                    self._em_curso = None

    def _consultar(self, ident: str, estado: dict, args: dict, commodity: str | None, inicio: float) -> None:
        log.info("Consulta %s: %s; documento %s; área de produção %s", ident[:8],
                 f"CAR {args['cod_imovel']}" if args["cod_imovel"] else "ponto", "informado" if args["documento"]
                 else "não informado", "enviada" if args["area_producao"] else "não enviada")
        try:
            ficha = self.executar(args["cod_imovel"], args["lat"], args["lon"], args.pop("documento"),
                                  area_producao=args["area_producao"])
        except Exception as e:  # noqa: BLE001 — qualquer falha vira inconclusivo com motivo, nunca "sem ocorrência"
            log.error("Consulta %s não terminou: %s", ident[:8], _sem_documento(f"{type(e).__name__}: {e}")[:300])
            ficha = {"consulta": {"cod_imovel": args["cod_imovel"], "lat": args["lat"], "lon": args["lon"],
                                  "documento_informado": bool(estado["documento_curto"]),
                                  "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                     **prediagnostico.ficha_inconclusiva(_motivo(e)), "procedencia": []}
        tempo = time.monotonic() - inicio
        try:
            ficha.setdefault("consulta", {})["commodity"] = commodity
            caminhos = _nome_unico(prediagnostico.escrever(ficha, pasta_saida()), ficha, ident)
            execucao = resultados.Execucao("avulsa", organizacao_id=resultados.DEMONSTRACAO, comando=COMANDO)
            execucao.acrescentar(ficha, ficha_arquivo=caminhos["html"].name)
            execucao.encerrar()
            res = ficha["resultado"]
            pronto = dict(estado="pronto", tempo_s=round(tempo, 1), etapas=etapas(ficha), situacao=res["situacao"],
                          resumo=res.get("resumo"), contagem=res.get("contagem", {}),
                          motivo=_motivo_inconclusivo(ficha),
                          cod_imovel=(ficha.get("imovel") or {}).get("cod_imovel"),
                          ficha=caminhos["html"].name, ficha_json=caminhos["json"].name)
        except Exception as e:  # noqa: BLE001
            log.error("Consulta %s: ficha não gravada: %s", ident[:8], _sem_documento(f"{type(e).__name__}: {e}")[:300])
            estado.update(estado="erro", tempo_s=round(tempo, 1),
                          erro=f"A ficha não pôde ser gravada ({type(e).__name__}). Tente de novo")
            return
        estado.update(pronto)
        log.info("Consulta %s: %s em %.1f s; ficha %s", ident[:8], res["situacao"], tempo, caminhos["html"].name)

    def publico(self, ident: str) -> dict | None:
        """Estado para o navegador (sem o relógio interno)."""
        estado = self.estados.get(ident)
        if estado is None:
            return None
        saida = {k: v for k, v in estado.items() if k != "inicio"}
        if estado["estado"] == "rodando":
            saida["decorrido_s"] = round(time.monotonic() - estado["inicio"], 1)
        return saida
