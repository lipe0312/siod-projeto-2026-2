"""Persistência: as mesmas consultas (polígonos PRODES, alertas DETER e embargos IBAMA que tocam cada CAR) em três
formas — parquet + STRtree em memória (como hoje), DuckDB spatial com índice R-tree e PostGIS com índice GiST.

Roda da raiz, com um PostGIS de teste (descartável) na porta 55439:
    docker run -d --rm --name siod-bench-postgis -e POSTGRES_PASSWORD=bench -p 127.0.0.1:55439:5432 imresamu/postgis:17-3.5
    .venv/bin/python docs/evidencias/atividade-04/cobertura-e-persistencia/04_persistencia_benchmark.py
    docker stop siod-bench-postgis

A imagem oficial postgis/postgis não tem build arm64; imresamu/postgis é a multiarquitetura. Arquivos temporários
(banco DuckDB e CSVs) ficam em data/benchmark_persistencia/, fora do repositório.
"""
import json, os, resource, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
PASTA = Path(__file__).resolve().parent
import duckdb, numpy as np, pandas as pd, shapely
from shapely.strtree import STRtree
from pipeline.fontes import sicar

S = "data/benchmark_persistencia"; os.makedirs(f"{S}/bench", exist_ok=True); R = {}
cars, _ = sicar.consultar_municipio("3148103")
cars = cars.sample(300, random_state=42).reset_index(drop=True)
R["cars"] = {"municipio": "Patrocínio (MG)", "amostra": len(cars)}
TAB = {"prodes": ("inpe_prodes", "uuid"), "deter": ("inpe_deter_alertas", "id_alerta"),
       "ibama": ("ibama_embargos", "id_embargo")}

# A. Atual: parquet + STRtree em memória (ru_maxrss em bytes no macOS)
mem0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
t0 = time.perf_counter()
dfs = {k: pd.read_parquet(f"data/processed/{a}.parquet", columns=[i, "geometria_wkt"]).dropna() for k, (a, i) in TAB.items()}
arv = {k: STRtree(shapely.from_wkt(d["geometria_wkt"].to_numpy())) for k, d in dfs.items()}
carga = time.perf_counter() - t0
memoria_mb = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - mem0) / 1e6
geoms = shapely.from_wkt(cars["geometria_wkt"].to_numpy())
t0 = time.perf_counter(); cont_a = []
for g in geoms:
    cont_a.append(sum(len(arv[k].query(g, predicate="intersects")) for k in TAB))
q = time.perf_counter() - t0
R["parquet_strtree"] = {"carga_s": round(carga, 2), "memoria_acrescida_mb": round(memoria_mb), "consulta_total_s": round(q, 3), "consulta_media_ms": round(q / len(cars) * 1000, 2),
                        "disco_mb": round(sum(os.path.getsize(f"data/processed/{a}.parquet") for a, _ in TAB.values()) / 1e6, 1),
                        "achados": int(sum(cont_a)),
                        "linhas": {k: len(d) for k, d in dfs.items()}}
print("A", R["parquet_strtree"], flush=True)

# B. DuckDB spatial (arquivo), índice R-tree
db = f"{S}/bench.duckdb"
if os.path.exists(db): os.remove(db)
c = duckdb.connect(db); c.execute("INSTALL spatial; LOAD spatial")
t0 = time.perf_counter()
for k, (a, i) in TAB.items():
    c.execute(f"CREATE TABLE {k} AS SELECT {i} AS id, ST_GeomFromText(geometria_wkt) AS geom "
              f"FROM read_parquet('data/processed/{a}.parquet') WHERE geometria_wkt IS NOT NULL")
    c.execute(f"CREATE INDEX {k}_rt ON {k} USING RTREE (geom)")
c.execute("CHECKPOINT"); carga = time.perf_counter() - t0
c.close(); c = duckdb.connect(db, read_only=True); c.execute("LOAD spatial")
t0 = time.perf_counter(); cont_b = []
for w in cars["geometria_wkt"]:
    cont_b.append(sum(c.execute(f"SELECT count(*) FROM {k} WHERE ST_Intersects(geom, ST_GeomFromText(?))", [w]).fetchone()[0] for k in TAB))
q = time.perf_counter() - t0
R["duckdb_spatial"] = {"carga_s": round(carga, 2), "consulta_total_s": round(q, 3), "consulta_media_ms": round(q / len(cars) * 1000, 2),
                       "disco_mb": round(os.path.getsize(db) / 1e6, 1), "achados": int(sum(cont_b))}
c.close(); print("B", R["duckdb_spatial"], flush=True)

# C. PostGIS (container), índice GiST
env = {**os.environ, "PGPASSWORD": "bench"}
psql = ["psql", "-h", "127.0.0.1", "-p", "55439", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-q"]
def sql(s): return subprocess.run(psql + ["-Atc", s], env=env, check=True, capture_output=True, text=True).stdout
t0 = time.perf_counter()
for k, (a, i) in TAB.items():
    csv = f"{S}/bench/{k}.csv"; dfs[k].to_csv(csv, index=False, header=False)
    sql(f"DROP TABLE IF EXISTS {k}_raw, {k}; CREATE TABLE {k}_raw (id text, wkt text)")
    subprocess.run(psql + ["-c", f"\\copy {k}_raw FROM '{csv}' CSV"], env=env, check=True)
    sql(f"CREATE TABLE {k} AS SELECT id, ST_GeomFromText(wkt, 4674) AS geom FROM {k}_raw; DROP TABLE {k}_raw;"
        f"CREATE INDEX {k}_gist ON {k} USING GIST (geom); ANALYZE {k}")
carga = time.perf_counter() - t0
arq = f"{S}/bench/consultas.sql"
with open(arq, "w") as f:
    for w in cars["geometria_wkt"]:
        f.write("SELECT " + " + ".join(f"(SELECT count(*) FROM {k} WHERE ST_Intersects(geom, ST_GeomFromText('{w}', 4674)))" for k in TAB) + ";\n")
t0 = time.perf_counter()
out = subprocess.run(psql + ["-At", "-f", arq], env=env, check=True, capture_output=True, text=True).stdout
q = time.perf_counter() - t0
cont_c = [int(x) for x in out.split()]
tam = int(sql("SELECT sum(pg_total_relation_size(t)) FROM unnest(array['prodes','deter','ibama']) t"))
R["postgis"] = {"carga_s": round(carga, 2), "consulta_total_s": round(q, 3), "consulta_media_ms": round(q / len(cars) * 1000, 2),
                "disco_mb": round(tam / 1e6, 1), "achados": int(sum(cont_c))}
print("C", R["postgis"], flush=True)
R["mesmos_achados_por_car"] = {"duckdb": cont_a == cont_b, "postgis": cont_a == cont_c}
(PASTA / "04_persistencia_benchmark.json").write_text(json.dumps(R, indent=1))
print(R["mesmos_achados_por_car"])
