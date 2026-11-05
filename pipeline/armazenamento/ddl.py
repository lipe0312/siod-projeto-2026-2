"""DDL do banco gerado dos contratos (ADR 0017): `python -m pipeline.armazenamento.ddl` regrava as migrações geradas.

    0002_tabelas_lite.sql      tabelas do perfil lite (geometria só se o perfil dela permitir)
    0003_tabelas_completo.sql  tabelas do perfil completo e as geometrias de perfil completo das tabelas lite
    0004_seguranca_por_linha.sql  RLS de cad e diag, papéis agrovalid_app e agrovalid_leitura, autenticação da chave de API
    0005_visoes.sql            <tabela>_vigente e diag.mudanca

A 0001 (extensões e esquemas) é escrita à mão. Tabelas com perfil `fora` nunca entram.

Convenções do banco:
- a coluna de geometria do contrato (`geometria_wkt`, WKT no lago) vira `geometria geometry(Geometry, 4674)`; o tipo
  declarado no contrato (MultiPolygon etc.) vai em COMMENT, porque os dados reais misturam Polygon e MultiPolygon;
- `data_hora` vira `timestamp` sem fuso, no horário de Brasília (o do pipeline, que grava `datetime.now()` local); o que
  vier com fuso é convertido para America/Sao_Paulo antes (o carregador faz isso);
- as colunas de controle do histórico (contratos.CONTROLE) vêm depois das colunas do contrato.
"""

import sys
from pathlib import Path

from pipeline import config
from pipeline.armazenamento import contratos
from pipeline.armazenamento.contratos import Contrato

MIGRACOES = config.RAIZ / "banco" / "migracoes"
SRID = 4674
COLUNA_GEOMETRIA = "geometria"
PAPEL_APP = "agrovalid_app"
PAPEL_LEITURA = "agrovalid_leitura"
ESQUEMAS_LEITURA = ("meta", "cad", "diag")
TABELA_CHAVE = "cad.chave_api"
ESQUEMAS = ("meta", "geo", "ref", "cad", "diag")
TIPOS_SQL = {"texto": "text", "inteiro": "bigint", "decimal": "double precision", "logico": "boolean",
             "data_hora": "timestamp", "data": "date", "json": "jsonb", "geometria": f"geometry(Geometry, {SRID})"}
TIPOS_CONTROLE = {"carga_id": "text", "valido_de": "timestamp", "valido_ate": "timestamp", "hash_linha": "text",
                  "consultado_em": "timestamp"}
# Colunas com índice btree, quando existirem na tabela.
INDICES_BTREE = ("documento_hash", "cod_imovel", "cod_car", "organizacao_id", "carga_id", "hash_sha256")
# Parte da chave primária que vem das colunas de controle.
CHAVE_CONTROLE = {"validade": ("valido_de",), "por_consulta": ("consultado_em",)}

ARQUIVOS = {"0002": "0002_tabelas_lite.sql", "0003": "0003_tabelas_completo.sql",
            "0004": "0004_seguranca_por_linha.sql", "0005": "0005_visoes.sql"}
CABECALHO = ("-- GERADO por `python -m pipeline.armazenamento.ddl` a partir de contratos/. Não edite à mão:\n"
             "-- mude o contrato e gere de novo (o teste tests/test_banco_ddl.py acusa o arquivo desatualizado).\n")


# ---------------------------------------------------------------------------------------------------------------
# Perfis
# ---------------------------------------------------------------------------------------------------------------

def perfil_da_geometria(c: Contrato) -> str | None:
    """Perfil mínimo que carrega a geometria da tabela (o da tabela, se o contrato não disser outro)."""
    return (c.geometria.get("perfil_banco") or c.perfil_banco) if c.geometria else None


def na_tabela(c: Contrato, perfil: str) -> bool:
    """A tabela existe no perfil? O completo inclui o lite."""
    return c.perfil_banco == "lite" or (c.perfil_banco == "completo" and perfil == "completo")


def geometria_no_perfil(c: Contrato, perfil: str) -> bool:
    g = perfil_da_geometria(c)
    return g is not None and (g == "lite" or (g == "completo" and perfil == "completo"))


def tabelas(perfil: str) -> list[Contrato]:
    return [c for c in contratos.todos().values() if na_tabela(c, perfil)]


def colunas_banco(c: Contrato, perfil: str) -> list[tuple[str, str]]:
    """(nome no banco, nome no contrato ou de controle) das colunas da tabela no perfil. A geometria de perfil
    completo de uma tabela lite não está no perfil lite (ver `acrescentar_geometria`)."""
    saida = []
    for col in c.colunas:
        if col.tipo != "geometria":
            saida.append((col.nome, col.nome))
        elif geometria_no_perfil(c, perfil):
            saida.append((COLUNA_GEOMETRIA, col.nome))
    return saida + [(n, n) for n in c.controle]


# ---------------------------------------------------------------------------------------------------------------
# Texto SQL
# ---------------------------------------------------------------------------------------------------------------

def _lit(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _indice(c: Contrato, coluna: str, metodo: str = "btree") -> str:
    usando = " USING gist" if metodo == "gist" else ""
    return f"CREATE INDEX ix_{c.esquema}_{c.nome}_{coluna} ON {c.tabela}{usando} ({coluna});"


def _comentario_geometria(c: Contrato) -> str:
    g = c.geometria
    return (f"COMMENT ON COLUMN {c.tabela}.{COLUNA_GEOMETRIA} IS "
            + _lit(f"Declarado no contrato: {g['tipo']}, SRID {g['srid']}. Os dados reais misturam "
                   "Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.")
            + ";")


def _tipo_e_nulo(c: Contrato, origem: str) -> tuple[str, bool]:
    """Tipo SQL e se aceita nulo, da coluna do contrato ou de controle."""
    if origem in TIPOS_CONTROLE:
        return TIPOS_CONTROLE[origem], origem not in CHAVE_CONTROLE.get(c.historico, ())
    col = next(x for x in c.colunas if x.nome == origem)
    return TIPOS_SQL[col.tipo], col.nulo


def criar_tabela(c: Contrato) -> str:
    """CREATE TABLE, índices e comentários. A tabela lite nasce sem a geometria de perfil completo."""
    perfil = "lite" if c.perfil_banco == "lite" else "completo"
    chave = [*c.chave, *CHAVE_CONTROLE.get(c.historico, ())]
    colunas = colunas_banco(c, perfil)
    linhas = []
    for nome, origem in colunas:
        tipo, nulo = _tipo_e_nulo(c, origem)
        linhas.append(f"    {nome:<26}{tipo}{'' if nulo else ' NOT NULL'}")
    linhas.append(f"    PRIMARY KEY ({', '.join(chave)})")
    sql = [f"CREATE TABLE {c.tabela} (\n" + ",\n".join(linhas) + "\n);",
           f"COMMENT ON TABLE {c.tabela} IS {_lit(f'{c.descricao} [histórico: {c.historico}]')};"]
    nomes = [n for n, _ in colunas]
    if COLUNA_GEOMETRIA in nomes:
        sql += [_comentario_geometria(c), _indice(c, COLUNA_GEOMETRIA, "gist")]
    sql += [_indice(c, n) for n in INDICES_BTREE if n in nomes]
    return "\n".join(sql)


def acrescentar_geometria(c: Contrato) -> str:
    """ALTER TABLE que acrescenta, no perfil completo, a geometria que o lite não carrega."""
    obrigatoria = not next(x for x in c.colunas if x.nome == c.geometria["coluna"]).nulo
    return "\n".join([f"ALTER TABLE {c.tabela} ADD COLUMN {COLUNA_GEOMETRIA} {TIPOS_SQL['geometria']}"
                      f"{' NOT NULL' if obrigatoria else ''};",
                      _comentario_geometria(c), _indice(c, COLUNA_GEOMETRIA, "gist")])


def visao_vigente(c: Contrato) -> str | None:
    """<tabela>_vigente: versão aberta (validade) ou a consulta mais recente por chave (por_consulta)."""
    if c.historico == "validade":
        corpo = f"SELECT * FROM {c.tabela}\nWHERE valido_ate IS NULL"
    elif c.historico == "por_consulta":
        chave = ", ".join(c.chave)
        corpo = f"SELECT DISTINCT ON ({chave}) * FROM {c.tabela}\nORDER BY {chave}, consultado_em DESC"
    else:
        return None
    return f"CREATE OR REPLACE VIEW {c.tabela}_vigente AS\n{corpo};"


def tem_visao_vigente(c: Contrato) -> bool:
    return c.historico in ("validade", "por_consulta")


# --- segurança por linha ----------------------------------------------------------------------------------------

def _regra_rls(c: Contrato) -> tuple[str, str] | None:
    """(condição de leitura, condição de escrita) da tabela, ou None se ela não tem política."""
    atual = "current_setting('app.organizacao_id', true)"
    if c.esquema not in ("cad", "diag"):
        return None
    if "organizacao_id" in c.nomes:
        propria = f"organizacao_id = {atual}"
        # Só a demonstração (organizacao_id = 'demonstracao', CARs públicos e CPF fictício) é visível a todos. Linha sem
        # organização (consulta avulsa da equipe) não é visível ao papel da aplicação; a escrita exige a organização.
        leitura = f"organizacao_id = 'demonstracao' OR {propria}" if c.esquema == "diag" else propria
        return leitura, propria
    if c.esquema == "diag" and "execucao_id" in c.nomes:
        # Sem organizacao_id: segue a execução, que já passa pela política dela.
        regra = "execucao_id IN (SELECT execucao_id FROM diag.execucao)"
        return regra, regra
    return None


def politicas(c: Contrato) -> str | None:
    regra = _regra_rls(c)
    if not regra:
        return None
    leitura, escrita = regra
    return "\n".join([f"ALTER TABLE {c.tabela} ENABLE ROW LEVEL SECURITY;",
                      f"CREATE POLICY {c.nome}_leitura ON {c.tabela} FOR SELECT\n    USING ({leitura});",
                      f"CREATE POLICY {c.nome}_insercao ON {c.tabela} FOR INSERT\n    WITH CHECK ({escrita});"])


# ---------------------------------------------------------------------------------------------------------------
# Arquivos
# ---------------------------------------------------------------------------------------------------------------

def _bloco(titulo: str, sql: str) -> str:
    return f"-- {titulo}\n{sql}\n"


def gerar_0002() -> str:
    partes = [CABECALHO, "-- Perfil lite: cabe nos planos gratuitos do Supabase (500 MB) e do Neon (1 GB por projeto).\n"
              "-- Embargo do IBAMA entra sem geometria; ela vem na 0003, só no perfil completo.\n"
              "-- data_hora vira timestamp sem fuso, no horário de Brasília (America/Sao_Paulo).\n"]
    partes += [_bloco(c.tabela, criar_tabela(c)) for c in tabelas("lite")]
    return "\n".join(partes)


def gerar_0003() -> str:
    todas = contratos.todos().values()
    completo = [c for c in tabelas("completo") if c.perfil_banco == "completo"]
    acrescimos = [c for c in todas if c.perfil_banco == "lite" and perfil_da_geometria(c) == "completo"]
    partes = [CABECALHO, "-- Perfil completo: acrescenta ao lite as tabelas pesadas e as geometrias de perfil completo.\n"]
    partes += [_bloco(c.tabela, criar_tabela(c)) for c in completo]
    partes += [_bloco(f"{c.tabela}: geometria só do perfil completo", acrescentar_geometria(c)) for c in acrescimos]
    # A visão já criada pela 0005 (perfil lite) não enxerga a coluna nova; recriá-la a inclui (a coluna entra no fim).
    visoes = [v for c in acrescimos if tem_visao_vigente(c) and (v := visao_vigente(c))]
    visoes += [v for c in completo if tem_visao_vigente(c) and (v := visao_vigente(c))]
    if visoes:
        partes.append(_bloco("visões das tabelas acima", "\n\n".join(visoes)))
    return "\n".join(partes)


def gerar_0004() -> str:
    ativas = [c for c in tabelas("lite") if politicas(c)]
    partes = [CABECALHO, "-- Segurança por linha (ADR 0017), em Postgres puro: vale no Neon, no Supabase e no local.\n"
              "-- Quem usa a API define a organização da conexão: SET app.organizacao_id = '<uuid>'.\n"
              "-- Sem a variável, current_setting(..., true) dá NULL e nenhuma linha passa.\n"
              "-- O dono das tabelas (quem carrega) não é afetado: não há FORCE ROW LEVEL SECURITY.\n"]
    partes.append(_bloco("papel da futura API: só SELECT e INSERT", f"""\
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PAPEL_APP}') THEN
        CREATE ROLE {PAPEL_APP} NOLOGIN;
    END IF;
END
$$;

-- Deixa quem migra usar SET ROLE {PAPEL_APP} (testes e a API, que entra como esse papel).
GRANT {PAPEL_APP} TO CURRENT_USER;

GRANT USAGE ON SCHEMA {', '.join(ESQUEMAS)} TO {PAPEL_APP};
GRANT SELECT ON ALL TABLES IN SCHEMA {', '.join(ESQUEMAS)} TO {PAPEL_APP};
GRANT INSERT ON ALL TABLES IN SCHEMA cad, diag TO {PAPEL_APP};

-- Tabelas e visões criadas depois (a 0003, a 0005) herdam as mesmas permissões.
ALTER DEFAULT PRIVILEGES IN SCHEMA {', '.join(ESQUEMAS)} GRANT SELECT ON TABLES TO {PAPEL_APP};
ALTER DEFAULT PRIVILEGES IN SCHEMA cad, diag GRANT INSERT ON TABLES TO {PAPEL_APP};"""))
    partes.append(_bloco("papel da API de leitura (ADR 0019): só SELECT, sem BYPASSRLS", f"""\
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PAPEL_LEITURA}') THEN
        CREATE ROLE {PAPEL_LEITURA} NOLOGIN NOBYPASSRLS;
    END IF;
END
$$;

-- A API entra como esse papel por requisição: SET LOCAL ROLE {PAPEL_LEITURA}, dentro da transação.
GRANT {PAPEL_LEITURA} TO CURRENT_USER;

GRANT USAGE ON SCHEMA {', '.join(ESQUEMAS_LEITURA)} TO {PAPEL_LEITURA};
GRANT SELECT ON ALL TABLES IN SCHEMA {', '.join(ESQUEMAS_LEITURA)} TO {PAPEL_LEITURA};
ALTER DEFAULT PRIVILEGES IN SCHEMA {', '.join(ESQUEMAS_LEITURA)} GRANT SELECT ON TABLES TO {PAPEL_LEITURA};"""))
    partes.append(_bloco(f"{TABELA_CHAVE}: nenhum papel da aplicação lê o hash; só a função abaixo o confere", f"""\
REVOKE ALL ON {TABELA_CHAVE} FROM {PAPEL_APP}, {PAPEL_LEITURA};

-- Devolve a organização da chave válida (não revogada, não expirada, escopo leitura) e marca o último uso.
-- SECURITY DEFINER: roda como o dono da tabela, que não passa pela segurança por linha; search_path fixo.
CREATE OR REPLACE FUNCTION cad.autenticar_chave_api(p_hash text)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    agora timestamp := now() AT TIME ZONE 'America/Sao_Paulo';
    org text;
BEGIN
    UPDATE {TABELA_CHAVE}
       SET ultimo_uso_em = agora
     WHERE hash_sha256 = p_hash
       AND escopo = 'leitura'
       AND revogada_em IS NULL
       AND expira_em > agora
    RETURNING organizacao_id INTO org;
    RETURN org;
END
$fn$;

REVOKE ALL ON FUNCTION cad.autenticar_chave_api(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cad.autenticar_chave_api(text) TO {PAPEL_LEITURA};"""))
    partes += [_bloco(c.tabela, politicas(c)) for c in ativas]
    return "\n".join(partes)


MUDANCA = """\
-- Por organização e imóvel (cod_imovel): o critério cuja situação mudou entre as duas últimas execuções.
-- security_invoker faz a visão obedecer à segurança por linha de quem consulta (padrão do Postgres 15 em diante).
CREATE OR REPLACE VIEW diag.mudanca WITH (security_invoker = true) AS
WITH ordenado AS (
    SELECT organizacao_id, cod_imovel, resultado_id, gerado_em,
           row_number() OVER (PARTITION BY organizacao_id, cod_imovel
                              ORDER BY gerado_em DESC, resultado_id DESC) AS ordem
    FROM diag.resultado_imovel
    WHERE cod_imovel IS NOT NULL
)
SELECT atual.organizacao_id,
       atual.cod_imovel,
       m.chave,
       m.criterio,
       m.situacao_anterior,
       m.situacao_atual,
       antes.gerado_em  AS data_anterior,
       atual.gerado_em  AS data_atual,
       antes.resultado_id AS resultado_anterior_id,
       atual.resultado_id AS resultado_atual_id
FROM ordenado atual
JOIN ordenado antes
  ON antes.ordem = 2
 AND antes.cod_imovel = atual.cod_imovel
 AND antes.organizacao_id IS NOT DISTINCT FROM atual.organizacao_id
-- FULL JOIN: o critério que apareceu ou sumiu entre as duas execuções também é mudança.
CROSS JOIN LATERAL (
    SELECT coalesce(ca.chave, cb.chave)       AS chave,
           coalesce(ca.criterio, cb.criterio) AS criterio,
           cb.situacao AS situacao_anterior,
           ca.situacao AS situacao_atual
    FROM (SELECT chave, criterio, situacao FROM diag.criterio WHERE resultado_id = atual.resultado_id) ca
    FULL JOIN (SELECT chave, criterio, situacao FROM diag.criterio WHERE resultado_id = antes.resultado_id) cb
      ON cb.chave = ca.chave
) m
WHERE atual.ordem = 1
  AND m.situacao_anterior IS DISTINCT FROM m.situacao_atual;

COMMENT ON VIEW diag.mudanca IS 'Critério cuja situação mudou entre as duas últimas execuções de um imóvel, por organização.';"""


def gerar_0005() -> str:
    partes = [CABECALHO, "-- Visões. O estado vigente vem do lago; no banco as tabelas guardam todas as versões.\n"]
    partes += [_bloco(f"{c.tabela}_vigente", visao_vigente(c)) for c in tabelas("lite") if tem_visao_vigente(c)]
    partes.append(_bloco("diag.mudanca", MUDANCA))
    return "\n".join(partes)


GERADORES = {"0002": gerar_0002, "0003": gerar_0003, "0004": gerar_0004, "0005": gerar_0005}


def gerar() -> dict[str, str]:
    """Nome do arquivo -> texto das migrações geradas."""
    return {ARQUIVOS[k]: f().rstrip() + "\n" for k, f in GERADORES.items()}


def gravar(pasta: Path = MIGRACOES) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for nome, texto in gerar().items():
        (pasta / nome).write_text(texto, encoding="utf-8")
        caminhos.append(pasta / nome)
    return caminhos


if __name__ == "__main__":
    for caminho in gravar():
        print(f"gravado {caminho.relative_to(config.RAIZ)}", file=sys.stdout)
