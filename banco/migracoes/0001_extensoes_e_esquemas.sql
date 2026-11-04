-- Extensões e esquemas do AgroValid (ADR 0017). Escrita à mão; as migrações 0002 a 0005 são geradas dos contratos.
-- Postgres puro: vale no Postgres local (imresamu/postgis:17-3.5), no Neon e no Supabase.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS meta;   -- catálogo de fontes, cargas, validações e descartes
CREATE SCHEMA IF NOT EXISTS geo;    -- base territorial: UF, município, bioma e o imóvel do CAR consultado
CREATE SCHEMA IF NOT EXISTS ref;    -- fontes públicas de restrição socioambiental
CREATE SCHEMA IF NOT EXISTS cad;    -- cadastro do cliente (segurança por linha)
CREATE SCHEMA IF NOT EXISTS diag;   -- resultado do pré-diagnóstico (segurança por linha)

-- Migrações já aplicadas (o carregador consulta e acrescenta aqui).
CREATE TABLE IF NOT EXISTS meta.migracao (
    nome        text PRIMARY KEY,
    sha256      text NOT NULL,
    aplicada_em timestamptz NOT NULL DEFAULT now()
);
