"""Compara, UF por UF, o lote do PRODES pelo WFS (cópia de 01/11/2026 em data/processed/inpe_prodes_wfs_20261101/)
com o lote pelo arquivo do bioma (data/processed/inpe_prodes/). Grava 01_comparacao.csv e 01_comparacao.md.

Uso, da raiz: .venv/bin/python docs/evidencias/atividade-04/prodes-arquivo/01_comparar_wfs_e_arquivo.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from pipeline import config  # noqa: E402
from pipeline.fontes import inpe_prodes  # noqa: E402

PASTA = Path(__file__).resolve().parent
WFS = config.DADOS_PROCESSADOS / "inpe_prodes_wfs_20261101"


def comparar(uf: str) -> dict:
    w = pd.read_parquet(WFS / f"uf={uf}" / "part.parquet")
    a = inpe_prodes.ler_uf(uf)
    so_w, so_a = set(w["uuid"]) - set(a["uuid"]), set(a["uuid"]) - set(w["uuid"])
    m = w.merge(a, on="uuid", suffixes=("_w", "_a"))
    gw = shapely.make_valid(shapely.from_wkt(m["geometria_wkt_w"].to_numpy()))
    ga = shapely.from_wkt(m["geometria_wkt_a"].to_numpy())
    area_w, area_a = m["area_km2_w"].to_numpy(), m["area_km2_a"].to_numpy()
    dif_area = np.abs(area_w - area_a) / np.where(area_a > 0, area_a, np.nan)
    colecao = shapely.get_type_id(gw) == 7  # GEOMETRYCOLLECTION: polígono que o arredondamento do WFS degenerou
    return {
        "uf": uf, "wfs": len(w), "arquivo": len(a), "em_ambos": len(m), "so_wfs": len(so_w), "so_arquivo": len(so_a),
        "ano_igual": float((m["ano_prodes_w"] == m["ano_prodes_a"]).mean()),
        "data_imagem_igual": float((m["data_imagem_w"] == m["data_imagem_a"]).mean()),
        "bioma_igual": float((m["bioma_w"] == m["bioma_a"]).mean()),
        "uf_igual": float((m["uf_w"] == m["uf_a"]).mean()),
        "area_dif_mediana": float(np.nanmedian(dif_area)),
        "area_dif_acima_10pct": int(np.nansum(dif_area > 0.10)),
        "wfs_geometrycollection": int(colecao.sum()),
        "casas_wfs_mediana": int(m["geometria_wkt_w"].str.extract(r"\.(\d+)")[0].str.len().median()),
        "so_wfs_exemplos": ";".join(sorted(so_w)[:3]), "so_arquivo_exemplos": ";".join(sorted(so_a)[:3]),
    }


def main() -> None:
    ufs = sorted(p.name.removeprefix("uf=") for p in WFS.glob("uf=*"))
    df = pd.DataFrame([comparar(uf) for uf in ufs])
    df.to_csv(PASTA / "01_comparacao.csv", index=False)
    cols = ["uf", "wfs", "arquivo", "em_ambos", "so_wfs", "so_arquivo", "ano_igual", "data_imagem_igual", "uf_igual",
            "area_dif_mediana", "area_dif_acima_10pct", "wfs_geometrycollection", "casas_wfs_mediana"]
    total = df[["wfs", "arquivo", "em_ambos", "so_wfs", "so_arquivo", "area_dif_acima_10pct",
                "wfs_geometrycollection"]].sum()
    linhas = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df[cols].itertuples(index=False):
        linhas.append("| " + " | ".join(f"{v:.4f}" if isinstance(v, float) else str(v) for v in r) + " |")
    texto = "\n".join(linhas) + "\n\nTotal: " + ", ".join(f"{k} {int(v)}" for k, v in total.items()) + "\n"
    (PASTA / "01_comparacao.md").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
