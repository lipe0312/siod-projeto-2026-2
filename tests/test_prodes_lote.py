"""PRODES em lote por UF: recorte pelo contorno, UF que entra com o imóvel e verificação mensal, com um serviço WFS
falso (sem rede) e contornos fictícios de UF e bioma."""

import gzip
import json
import re

import pandas as pd
import pytest
import shapely

from conftest import ocorrencias
from pipeline import config, prediagnostico, territorio, wfs
from pipeline.fontes import inpe_prodes
from pipeline.validacao import ErroDeValidacao
from test_inpe_prodes import poligono, quadrado, resposta

HOJE = pd.Timestamp("2026-10-30")
# MG a oeste de -45, SP a leste; Cerrado e Mata Atlântica nas duas. Polígonos fictícios ao longo de y = -18.
MG, SP = shapely.box(-48, -20, -45, -17), shapely.box(-45, -20, -42, -17)
CERRADO, MATA = shapely.box(-48, -18.5, -42, -17), shapely.box(-48, -20, -42, -18.5)
Y = -18.0


class ServicoFalso:
    """Polígonos por (bioma, ano), cada um com o x do canto e a UF gravada no campo state. Conta as idas à rede."""

    def __init__(self):
        # (bioma, ano) -> lista de (x, state)
        self.poligonos = {("cerrado", 2024): [(-47.0, "MINAS GERAIS"), (-46.0, "MINAS GERAIS")],
                          ("cerrado", 2025): [(-47.5, "MINAS GERAIS"), (-46.5, "MINAS GERAIS"), (-43.0, "SAO PAULO")],
                          ("mata_atlantica", 2024): [(-46.8, "MG")], ("mata_atlantica", 2025): [(-46.2, "MG")]}
        self.contagens, self.baixados = 0, []
        self.versao = {}  # (bioma, ano) -> sufixo do uuid; trocar simula revisão do INPE com a mesma contagem
        self.falhar = set()  # retângulos (bioma, ano, x0) que respondem 502 uma vez

    @staticmethod
    def _bioma(tipo):
        return next(b for b, c in config.CAMADAS_PRODES.items() if c["tipo"] == tipo)

    @staticmethod
    def _retangulo(cql):
        m = re.search(r"BBOX\(geom,([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\)", cql)
        if not m:
            return None
        lat0, lon0, lat1, lon1 = map(float, m.groups())
        return shapely.box(lon0, lat0, lon1, lat1)

    def feicoes(self, bioma, ano, cql):
        caixa = self._retangulo(cql)
        v = self.versao.get((bioma, ano), "")
        saida = []
        for i, (x, uf) in enumerate(self.poligonos.get((bioma, ano), [])):
            geometria = quadrado(x, Y, 0.05)
            if caixa is None or caixa.intersects(shapely.geometry.shape(geometria)):
                saida.append(poligono(f"{bioma[:2]}{ano}-{i}{v}", ano=ano, data=f"{ano}-07-20", uf=uf,
                                      geometria=geometria))
        return saida

    def contar(self, url, tipo, cql, sessao=None, tentativas=4):
        self.contagens += 1
        return len(self.feicoes(self._bioma(tipo), int(re.search(r"year=(\d+)", cql).group(1)), cql))

    def consultar_geojson(self, url, tipo, cql, destino, sessao=None, atualizar=False, limite=None, tentativas=4):
        bioma, ano = self._bioma(tipo), int(re.search(r"year=(\d+)", cql).group(1))
        caixa = self._retangulo(cql)
        chave = (bioma, ano, round(caixa.bounds[0], 4))
        if chave in self.falhar:
            self.falhar.discard(chave)
            raise wfs.requests.HTTPError(f"WFS respondeu HTTP 502 para {cql}")
        if destino.exists() and not atualizar:
            return json.loads(gzip.decompress(destino.read_bytes())), {
                "arquivo": str(destino.relative_to(config.RAIZ)), "consultado_em_utc": "2026-10-30T09:00:00",
                "sha256": "0" * 64}
        self.baixados.append((bioma, ano))
        r = resposta(self.feicoes(bioma, ano, cql))
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
    monkeypatch.setattr(config, "PRODES_UFS_INICIAIS", ("MG",))
    monkeypatch.setattr(inpe_prodes, "PASTA_LOTE", tmp_path / "raw" / "lote")
    monkeypatch.setattr(inpe_prodes, "PASTA_SAIDA", tmp_path / "processed" / "inpe_prodes")
    for nome in ("ARQ_DESCARTADOS", "ARQ_PUBLICACAO"):
        monkeypatch.setattr(inpe_prodes, nome, tmp_path / "processed" / getattr(inpe_prodes, nome).name)
    monkeypatch.setattr(territorio, "ARQ_UFS", tmp_path / "ufs.parquet")
    monkeypatch.setattr(territorio, "ARQ_BIOMAS", tmp_path / "biomas.parquet")
    pd.DataFrame({"uf": ["MG", "SP"], "cod_uf": ["31", "35"], "geometria_wkt": [MG.wkt, SP.wkt]}).to_parquet(
        territorio.ARQ_UFS)
    pd.DataFrame({"bioma": ["cerrado", "mata_atlantica"], "nome": ["Cerrado", "Mata Atlântica"],
                  "geometria_wkt": [CERRADO.wkt, MATA.wkt]}).to_parquet(territorio.ARQ_BIOMAS)
    territorio._ufs.cache_clear()
    territorio._biomas.cache_clear()
    yield s
    territorio._ufs.cache_clear()
    territorio._biomas.cache_clear()


def test_primeira_execucao_grava_a_particao_da_uf_pelo_contorno(servico):
    r = inpe_prodes.executar(HOJE)
    assert r.entrada["ultimo_ano_publicado"] == {"cerrado": 2025, "mata_atlantica": 2025}
    assert r.entrada["ufs_biomas"] == {"MG": ["cerrado", "mata_atlantica"]}
    mg = inpe_prodes.ler_uf("MG")
    # O polígono de SP (x = -43) está no Brasil, mas fora do retângulo de MG: não entra na partição.
    assert len(mg) == 6 and set(mg["uf"]) == {"MG"} and set(mg["uf_fonte"]) == {"MG"}
    pub = inpe_prodes.ler_publicacao()
    assert pub["proxima_verificacao"] == "2026-11-29" and list(pub["particoes"]) == ["MG"]
    assert pub["ultima_imagem"]["cerrado"] == "2025-07-20"


def test_poligono_de_divisa_entra_nas_duas_ufs_e_state_diferente_do_contorno_e_alerta(servico):
    servico.poligonos[("cerrado", 2025)].append((-45.03, "SAO PAULO"))  # 0,03° em MG e 0,02° em SP
    inpe_prodes.executar(HOJE)
    inpe_prodes.garantir_uf("SP", HOJE)
    mg, sp = inpe_prodes.ler_uf("MG"), inpe_prodes.ler_uf("SP")
    divisa = "ce2025-3"
    assert divisa in set(mg["uuid"]) and divisa in set(sp["uuid"])
    linha = mg.set_index("uuid").loc[divisa]
    assert linha["uf"] == "MG" and linha["uf_fonte"] == "SP" and "UF_DIFERE_DO_CONTORNO" in linha["alertas"]


def test_uf_entra_no_lote_quando_o_imovel_chega_e_so_ela_e_baixada(servico):
    inpe_prodes.executar(HOJE)
    servico.baixados = []
    pub = inpe_prodes.garantir_uf("SP", HOJE + pd.Timedelta(days=3))
    assert pub["ufs"] == ["MG", "SP"] and sorted(pub["particoes"]) == ["MG", "SP"]
    assert len(inpe_prodes.ler_uf("SP")) == 1 and inpe_prodes.ler_uf("SP")["uuid"].tolist() == ["ce2025-2"]
    assert all(b in ("cerrado", "mata_atlantica") for b, _ in servico.baixados)
    assert len(servico.baixados) == 4  # 2 biomas x 2 anos, só para SP
    # A UF já no lote não é baixada de novo.
    servico.baixados = []
    inpe_prodes.garantir_uf("SP", HOJE + pd.Timedelta(days=4))
    assert servico.baixados == []


def test_carga_interrompida_retoma_do_que_ja_foi_gravado(servico):
    inpe_prodes.executar(HOJE)
    servico.falhar.add(("cerrado", 2025, -45.0))  # SP, cerrado 2025: 1 polígono, não há o que dividir
    servico.baixados = []
    with pytest.raises(wfs.requests.HTTPError):
        inpe_prodes.garantir_uf("SP", HOJE)
    assert servico.baixados == [("cerrado", 2024)]
    servico.baixados = []
    pub = inpe_prodes.garantir_uf("SP", HOJE)
    # cerrado 2024 de SP já estava gravado e não é pedido de novo.
    assert servico.baixados == [("cerrado", 2025), ("mata_atlantica", 2024), ("mata_atlantica", 2025)]
    assert "SP" in pub["particoes"] and len(inpe_prodes.ler_uf("SP")) == 1


def test_parte_que_recebe_502_e_pedida_em_quatro(servico):
    servico.falhar.add(("cerrado", 2025, -48.0))  # o retângulo inteiro de MG, com 2 polígonos
    inpe_prodes.executar(HOJE)
    assert len(inpe_prodes.ler_uf("MG")) == 6
    chaves = inpe_prodes._ler_manifesto()["biomas"]["cerrado"]["anos"]
    assert any(c.startswith("2025/MG/0-") for c in chaves) and "2025/MG/0" not in chaves


def test_retangulo_acima_do_limite_e_dividido(servico, monkeypatch):
    monkeypatch.setattr(config, "PRODES_POLIGONOS_POR_PARTE", 1)
    r = inpe_prodes.executar(HOJE)
    assert ocorrencias(r, "PRODES_RETANGULO_DIVIDIDO") > 0
    assert len(inpe_prodes.ler_uf("MG")) == 6  # nenhum polígono perdido nem repetido


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
    servico.poligonos[("cerrado", 2026)] = [(-47.2, "MINAS GERAIS")]
    r = inpe_prodes.executar(HOJE + pd.Timedelta(days=45))
    # Cerrado: 2026 é novo; 2025 deixou de ser o último e não mudou. Mata Atlântica: só o último (2025) é revisto.
    assert sorted(servico.baixados) == [("cerrado", 2026), ("mata_atlantica", 2025)]
    assert r.entrada["ultimo_ano_publicado"] == {"cerrado": 2026, "mata_atlantica": 2025}
    assert ocorrencias(r, "PRODES_NOVO_ANO_PUBLICADO") == 1
    assert len(inpe_prodes.ler_uf("MG")) == 7
    historico = inpe_prodes.ler_publicacao()["historico"]
    assert len(historico) == 2 and historico[-1]["mudancas"][0]["tipo"] == "novo ano publicado"


def test_ano_consolidado_que_muda_gera_alerta(servico):
    inpe_prodes.executar(HOJE)
    servico.poligonos[("cerrado", 2024)].append((-46.4, "MINAS GERAIS"))
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


def test_prediagnostico_le_a_particao_da_uf_no_retangulo_do_imovel(servico):
    inpe_prodes.executar(HOJE)
    prediagnostico._prodes_uf.cache_clear()
    limites = (-47.01, Y - 0.01, -46.9, Y + 0.06)  # só o primeiro quadrado do cerrado 2024
    prodes, situacao, procedencia = prediagnostico.obter_prodes("MG", limites)
    assert situacao["origem"] == "lote" and prodes["uuid"].tolist() == ["ce2024-0"]
    assert procedencia[0]["sha256"] == inpe_prodes.ler_publicacao()["particoes"]["MG"]["sha256"]


@pytest.mark.parametrize("biomas, esperado", [(["cerrado"], 2026), (["cerrado", "mata_atlantica"], 2025), ([], 2025)])
def test_ultimo_ano_do_imovel_segue_o_bioma(biomas, esperado):
    assert prediagnostico.ultimo_ano_do_imovel(biomas, {"cerrado": 2026, "mata_atlantica": 2025}) == esperado


@pytest.mark.rede
def test_servico_real_tem_ano_publicado_recente():
    contagens = inpe_prodes.contagem_por_ano("cerrado", HOJE.year)
    assert inpe_prodes.ultimo_ano(contagens) >= 2025


def test_prediagnostico_sem_baixar_nao_vai_a_rede_para_uf_fora_do_lote(servico):
    inpe_prodes.executar(HOJE)
    servico.contagens, servico.baixados = 0, []
    with pytest.raises(prediagnostico.UFForaDoLote, match="SP ainda não carregada"):
        prediagnostico.obter_prodes("SP", (-43.0, -18.0, -42.9, -17.9), baixar=False)
    assert servico.contagens == 0 and servico.baixados == []
