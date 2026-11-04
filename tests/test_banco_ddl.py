"""DDL do banco gerado dos contratos: offline, sem Postgres."""

import re

from pipeline.armazenamento import contratos, ddl
from pipeline.armazenamento.contratos import Coluna, Contrato


def contrato(historico="registro", perfil="lite", geometria=None, chave=("id",)):
    colunas = [Coluna("id", "texto", False), Coluna("valor", "decimal"), Coluna("quando", "data_hora"),
               Coluna("dado", "json"), Coluna("ativo", "logico"), Coluna("n", "inteiro"), Coluna("dia", "data")]
    if geometria:
        colunas.append(Coluna("geometria_wkt", "geometria"))
    return Contrato("ref.teste", "Tabela de 'teste'", "teste", chave, historico, perfil, tuple(colunas),
                    ("valor",) if historico == "validade" else (), geometria=geometria)


def test_migracoes_commitadas_estao_em_dia_com_os_contratos():
    for nome, texto in ddl.gerar().items():
        arquivo = ddl.MIGRACOES / nome
        assert arquivo.exists(), f"{nome} não existe; rode python -m pipeline.armazenamento.ddl"
        assert arquivo.read_text(encoding="utf-8") == texto, \
            f"{nome} desatualizado; rode python -m pipeline.armazenamento.ddl"


def test_tipos_e_comentario_da_geometria():
    geom = {"coluna": "geometria_wkt", "tipo": "MultiPolygon", "srid": 4674}
    sql = ddl.criar_tabela(contrato(geometria=geom))
    for coluna, tipo in (("valor", "double precision"), ("quando", "timestamp"), ("dado", "jsonb"),
                         ("ativo", "boolean"), ("n", "bigint"), ("dia", "date"),
                         ("geometria", "geometry(Geometry, 4674)")):
        assert re.search(rf"^\s+{coluna}\s+{re.escape(tipo)}", sql, re.M), coluna
    assert "COMMENT ON COLUMN ref.teste.geometria IS 'Declarado no contrato: MultiPolygon" in sql
    assert "COMMENT ON TABLE ref.teste IS 'Tabela de ''teste''" in sql
    assert "USING gist (geometria)" in sql


def test_chave_primaria_e_controle_por_historico():
    assert "PRIMARY KEY (id)" in ddl.criar_tabela(contrato("registro"))
    validade = ddl.criar_tabela(contrato("validade"))
    assert "PRIMARY KEY (id, valido_de)" in validade
    assert all(c in validade for c in ("carga_id", "valido_de", "valido_ate", "hash_linha"))
    assert re.search(r"valido_de\s+timestamp NOT NULL", validade)
    assert re.search(r"valido_ate\s+timestamp,", validade)
    consulta = ddl.criar_tabela(contrato("por_consulta"))
    assert "PRIMARY KEY (id, consultado_em)" in consulta and "carga_id" in consulta
    assert "valido_de" not in consulta
    assert "carga_id" not in ddl.criar_tabela(contrato("registro"))
    assert "PRIMARY KEY (id)" in ddl.criar_tabela(contrato("fotografia"))


def test_indices_btree_so_nas_colunas_que_existem():
    c = contrato("fotografia")
    assert "(carga_id)" in ddl.criar_tabela(c)
    assert "organizacao_id" not in ddl.criar_tabela(c)
    com_org = Contrato("cad.teste", "", "cadastro", ("id",), "registro", "lite",
                       (Coluna("id", "texto", False), Coluna("organizacao_id", "texto", False),
                        Coluna("documento_hash", "texto")))
    sql = ddl.criar_tabela(com_org)
    assert "ix_cad_teste_organizacao_id" in sql and "ix_cad_teste_documento_hash" in sql
    assert "USING gist" not in sql


def test_geometria_de_perfil_completo_so_aparece_no_completo():
    geom = {"coluna": "geometria_wkt", "tipo": "Geometry", "srid": 4674, "perfil_banco": "completo"}
    c = contrato("validade", geometria=geom)
    assert "geometria" not in ddl.criar_tabela(c)
    assert "ALTER TABLE ref.teste ADD COLUMN geometria geometry(Geometry, 4674)" in ddl.acrescentar_geometria(c)
    assert [n for n, _ in ddl.colunas_banco(c, "lite") if n == "geometria"] == []
    assert [n for n, _ in ddl.colunas_banco(c, "completo") if n == "geometria"] == ["geometria"]


def test_tabela_fora_nunca_vai_ao_banco():
    fora = contrato(perfil="fora")
    assert not ddl.na_tabela(fora, "lite") and not ddl.na_tabela(fora, "completo")
    pesada = contrato(perfil="completo")
    assert not ddl.na_tabela(pesada, "lite") and ddl.na_tabela(pesada, "completo")


def test_perfis_dos_contratos_reais():
    lite = {c.tabela for c in ddl.tabelas("lite")}
    completo = {c.tabela for c in ddl.tabelas("completo")}
    assert lite < completo
    assert {"ref.alerta_deter", "ref.desmatamento_prodes"} <= completo - lite
    embargo = contratos.carregar("ref.embargo_ibama")
    assert "ref.embargo_ibama" in lite
    assert not ddl.geometria_no_perfil(embargo, "lite") and ddl.geometria_no_perfil(embargo, "completo")
    lite_sql, completo_sql = ddl.gerar()["0002_tabelas_lite.sql"], ddl.gerar()["0003_tabelas_completo.sql"]
    assert "CREATE TABLE ref.desmatamento_prodes" not in lite_sql
    assert "CREATE TABLE ref.desmatamento_prodes" in completo_sql
    assert "ALTER TABLE ref.embargo_ibama ADD COLUMN geometria" in completo_sql
    assert "ref.embargo_ibama" in lite_sql and "geometria" not in lite_sql.split("CREATE TABLE ref.embargo_ibama")[1] \
        .split("CREATE TABLE")[0]


def test_rls_em_todas_as_tabelas_de_cad_e_diag_com_organizacao():
    sql = ddl.gerar()["0004_seguranca_por_linha.sql"]
    for c in contratos.todos().values():
        if c.esquema in ("cad", "diag") and "organizacao_id" in c.nomes:
            assert f"ALTER TABLE {c.tabela} ENABLE ROW LEVEL SECURITY;" in sql, c.tabela
    assert "FORCE ROW LEVEL SECURITY;" not in sql
    assert "organizacao_id = 'demonstracao' OR organizacao_id = current_setting('app.organizacao_id', true)" in sql
    assert "organizacao_id IS NULL OR" not in sql  # consulta avulsa (sem organização) não fica visível a todos
    assert "CREATE ROLE agrovalid_app NOLOGIN" in sql


def test_visoes_vigentes_para_validade_e_por_consulta():
    sql = ddl.gerar()["0005_visoes.sql"]
    for c in contratos.todos().values():
        if c.perfil_banco == "lite":
            assert (f"CREATE OR REPLACE VIEW {c.tabela}_vigente" in sql) == (c.historico in ("validade", "por_consulta"))
    assert "diag.mudanca" in sql
