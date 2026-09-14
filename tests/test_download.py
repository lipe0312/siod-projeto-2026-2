import pytest

from pipeline import config, download


class RespostaFalsa:
    def __init__(self, conteudo: bytes, tamanho_anunciado: int):
        self.conteudo = conteudo
        self.headers = {"Content-Length": str(tamanho_anunciado), "Content-Type": "text/csv"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self.conteudo


def test_download_truncado_e_repetido_e_depois_falha(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(download.time, "sleep", lambda s: None)
    chamadas = []

    def get(*args, **kwargs):
        chamadas.append(1)
        return RespostaFalsa(b"abc", tamanho_anunciado=10)

    monkeypatch.setattr(download.requests, "get", get)
    with pytest.raises(download.DownloadIncompleto):
        download.baixar("http://exemplo", tmp_path / "arquivo.csv")
    assert len(chamadas) == download.TENTATIVAS
    assert not (tmp_path / "arquivo.csv").exists() and not (tmp_path / "arquivo.csv.parcial").exists()


def test_download_completo_registra_procedencia(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(download.requests, "get", lambda *a, **k: RespostaFalsa(b"abc", tamanho_anunciado=3))
    meta = download.baixar("http://exemplo", tmp_path / "arquivo.csv")
    assert meta["tamanho_bytes"] == 3 and len(meta["sha256"]) == 64 and meta["arquivo"] == "arquivo.csv"
