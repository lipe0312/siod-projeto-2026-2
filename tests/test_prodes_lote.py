"""PRODES em lote: verificação mensal da publicação, com um serviço WFS falso (sem rede)."""

import gzip
import json
import re

import pandas as pd
import pytest

from conftest import ocorrencias
from pipeline import config, prediagnostico, wfs
from pipeline.fontes import inpe_prodes
from pipeline.validacao import ErroDeValidacao
from test_inpe_prodes import X0, Y0, poligono, quadrado, resposta

HOJE = pd.Timestamp("2026-10-30")


class ServicoFalso:
    """Polígonos por (bioma, ano). Conta as idas à rede para mostrar o que foi baixado de novo."""

    def __init__(self):
        self.poligonos = {("cerrado", 2024): 2, ("cerrado", 2025): 3, ("mata_atlantica", 2024): 1,
                          ("mata_atlantica", 2025): 1}
        self.contagens, self.baixados = 0, []
        self.versao = {}  # (bioma, ano) -> sufixo do uuid; trocar simula revisão do INPE com a mesma contagem

    @staticmethod
    def _bioma(tipo):
        return next(b for b, c in config.CAMADAS_PRODES.items() if c["tipo"] == tipo)

    def feicoes(self, bioma, ano):
        uf = "MINAS GERAIS" if bioma == "cerrado" else "MG"
        v = self.versao.get((bioma, ano), "")
        return [poligono(f"{bioma[:2]}{ano}-{i}{v}", ano=ano, data=f"{ano}-07-20", uf=uf,
                         geometria=quadrado(X0 + 0.02 * i, Y0)) for i in range(self.poligonos.get((bioma, ano), 0))]

    def contar(self, url, tipo, cql, sessao=None):
        self.contagens += 1
        return len(self.feicoes(self._bioma(tipo), int(re.search(r"year=(\d+)", cql).group(1))))

    def consultar_geojson(self, url, tipo, cql, destino, sessao=None, atualizar=False, limite=None):
        bioma, ano = self._bioma(tipo), int(re.search(r"year=(\d+)", cql).group(1))
        self.baixados.append((bioma, ano))
        r = resposta(self.feicoes(bioma, ano))
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(gzip.compress(json.dumps(r).encode()))
        return r, {"arquivo": str(destino.relative_to(config.RAIZ)), "consultado_em_utc": "2026-10-30T10:00:00",
                   "sha256": "0" * 64}


@pytest.fixture
def servico(tmp_path, monkeypatch):
    s = ServicoFalso()
    monkeypatch.setattr(wfs, "contar", s.contar)
    monkeypatch.setattr(wfs, "consultar_geojson", s.consultar_geojson)
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(config, "DADOS_PROCESSADOS", tmp_path / "processed")
    monkeypatch.setattr(config, "PRODES_DESDE", 2024)
    monkeypatch.setattr(inpe_prodes, "PASTA_LOTE", tmp_path / "raw" / "lote")
    for nome in ("ARQ_SAIDA", "ARQ_DESCARTADOS", "ARQ_PUBLICACAO"):
        monkeypatch.setattr(inpe_prodes, nome, tmp_path / "processed" / getattr(inpe_prodes, nome).name)
    return s


def test_primeira_execucao_baixa_os_anos_publicados_e_grava_o_parquet(servico):
    r = inpe_prodes.executar(HOJE)
    assert sorted(servico.baixados) == [("cerrado", 2024), ("cerrado", 2025), ("mata_atlantica", 2024),
                                        ("mata_atlantica", 2025)]
    assert r.entrada["ultimo_ano_publicado"] == {"cerrado": 2025, "mata_atlantica": 2025}
    saida = pd.read_parquet(inpe_prodes.ARQ_SAIDA)
    assert len(saida) == 7 and set(saida["uf"]) == {"MG"}
    pub = inpe_prodes.ler_publicacao()
    assert pub["proxima_verificacao"] == "2026-11-29"
    assert pub["anos"]["cerrado"]["2025/MG"]["data_imagem_max"] == "2025-07-20"


def test_dentro_do_mes_nao_consulta_o_servico(servico):
    inpe_prodes.executar(HOJE)
    servico.contagens, servico.baixados = 0, []
    r = inpe_prodes.executar(HOJE + pd.Timedelta(days=29))
    assert servico.contagens == 0 and servico.baixados == []
    assert r.entrada["verificacao"].startswith("reaproveitada")
    # --verificar-prodes força a verificação mesmo dentro do intervalo.
    inpe_prodes.executar(HOJE + pd.Timedelta(days=29), verificar=True)
    assert servico.contagens > 0


def test_ano_novo_e_detectado_e_so_ele_e_o_ultimo_sao_baixados(servico):
    inpe_prodes.executar(HOJE)
    servico.baixados = []
    servico.poligonos[("cerrado", 2026)] = 4
    r = inpe_prodes.executar(HOJE + pd.Timedelta(days=31))
    # Cerrado: 2026 é novo; 2025 deixou de ser o último e não mudou. Mata Atlântica: só o último (2025) é revisto.
    assert sorted(servico.baixados) == [("cerrado", 2026), ("mata_atlantica", 2025)]
    assert r.entrada["ultimo_ano_publicado"] == {"cerrado": 2026, "mata_atlantica": 2025}
    assert ocorrencias(r, "PRODES_NOVO_ANO_PUBLICADO") == 1
    assert len(pd.read_parquet(inpe_prodes.ARQ_SAIDA)) == 11
    historico = inpe_prodes.ler_publicacao()["historico"]
    assert len(historico) == 2 and historico[-1]["mudancas"][0]["tipo"] == "novo ano publicado"


def test_ano_consolidado_que_muda_gera_alerta(servico):
    inpe_prodes.executar(HOJE)
    servico.poligonos[("cerrado", 2024)] = 5
    r = inpe_prodes.executar(HOJE + pd.Timedelta(days=45))
    assert ocorrencias(r, "PRODES_ANO_CONSOLIDADO_ALTERADO") == 1


def test_ultimo_ano_revisado_com_a_mesma_contagem_e_registrado(servico):
    inpe_prodes.executar(HOJE)
    servico.versao[("cerrado", 2025)] = "-rev"
    r = inpe_prodes.executar(HOJE, verificar=True)
    assert [m["tipo"] for m in r.entrada["mudancas"]] == ["último ano revisado"]
    assert ocorrencias(r, "PRODES_ANO_CONSOLIDADO_ALTERADO") == 0


def test_ultimo_ano_que_recua_interrompe(servico):
    inpe_prodes.executar(HOJE)
    servico.poligonos.pop(("cerrado", 2025))
    with pytest.raises(ErroDeValidacao, match="PRODES_ULTIMO_ANO_RECUOU"):
        inpe_prodes.executar(HOJE, verificar=True)


def test_prediagnostico_le_o_parquet_do_lote_no_retangulo_do_imovel(servico):
    inpe_prodes.executar(HOJE)
    prediagnostico._prodes_lote.cache_clear()
    limites = (X0 - 0.001, Y0 - 0.001, X0 + 0.005, Y0 + 0.005)  # só o primeiro quadrado de cada ano
    prodes, situacao, procedencia = prediagnostico.obter_prodes("MG", limites)
    prediagnostico._prodes_lote.cache_clear()
    assert situacao["origem"] == "lote" and len(prodes) == 4
    assert procedencia[0]["sha256"] == inpe_prodes.ler_publicacao()["sha256"]


@pytest.mark.parametrize("biomas_em_volta, esperado", [({"cerrado"}, 2026), ({"cerrado", "mata_atlantica"}, 2025),
                                                       (set(), 2025)])
def test_ultimo_ano_do_imovel_segue_o_bioma(biomas_em_volta, esperado):
    prodes = pd.DataFrame({"bioma": sorted(biomas_em_volta)})
    assert prediagnostico.ultimo_ano_do_imovel(prodes, {"cerrado": 2026, "mata_atlantica": 2025}) == esperado


@pytest.mark.rede
def test_servico_real_tem_ano_publicado_recente():
    contagens = inpe_prodes.contagem_por_ano("cerrado", HOJE.year)
    assert inpe_prodes.ultimo_ano(contagens) >= 2025
