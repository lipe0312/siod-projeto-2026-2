"""Apoio dos testes que gravam no lago: relógio que avança um segundo a cada carga (o carga_id tem resolução de
segundo, e duas execuções no mesmo segundo gravariam na mesma pasta)."""

from datetime import datetime, timedelta

from pipeline import config


def usar_lago_temporario(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(config, "LAGO", tmp_path / "data" / "lago")
    monkeypatch.setattr(config, "DADOS_BRUTOS", tmp_path / "data" / "raw")
    monkeypatch.setattr(config, "DADOS_PROCESSADOS", tmp_path / "data" / "processed")


def relogio_que_avanca(monkeypatch):
    class Relogio(datetime):
        passos = 0

        @classmethod
        def now(cls, tz=None):
            cls.passos += 1
            return datetime(2026, 11, 3, 10, 0, 0) + timedelta(seconds=cls.passos)

    monkeypatch.setattr("pipeline.validacao.datetime", Relogio)
