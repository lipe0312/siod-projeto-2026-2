-- GERADO por `python -m pipeline.armazenamento.ddl` a partir de contratos/. Não edite à mão:
-- mude o contrato e gere de novo (o teste tests/test_banco_ddl.py acusa o arquivo desatualizado).

-- Perfil completo: acrescenta ao lite as tabelas pesadas e as geometrias de perfil completo.

-- ref.alerta_deter
CREATE TABLE ref.alerta_deter (
    id_alerta                 text NOT NULL,
    camada                    text,
    gid                       text,
    classe                    text,
    data_imagem               timestamp,
    mes_publicacao            timestamp,
    uf                        text,
    cod_municipio             text,
    municipio                 text,
    area_km2                  double precision,
    satelite                  text,
    sensor                    text,
    geometria                 geometry(Geometry, 4674),
    alertas                   text,
    carga_id                  text,
    hash_linha                text,
    PRIMARY KEY (id_alerta)
);
COMMENT ON TABLE ref.alerta_deter IS 'Alertas de desmatamento do DETER (Amazônia, Cerrado e Pantanal), identificados pelo conteúdo (ADR 0004) [histórico: acrescimo]';
COMMENT ON COLUMN ref.alerta_deter.geometria IS 'Declarado no contrato: Geometry, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_ref_alerta_deter_geometria ON ref.alerta_deter USING gist (geometria);
CREATE INDEX ix_ref_alerta_deter_carga_id ON ref.alerta_deter (carga_id);

-- ref.desmatamento_prodes
CREATE TABLE ref.desmatamento_prodes (
    uuid                      text NOT NULL,
    bioma                     text,
    ano_prodes                bigint,
    data_imagem               timestamp,
    uf                        text NOT NULL,
    uf_fonte                  text,
    data_publicacao           timestamp,
    classe                    text,
    area_km2_fonte            double precision,
    area_km2                  double precision,
    satelite                  text,
    sensor                    text,
    geometria                 geometry(Geometry, 4674),
    alertas                   text,
    carga_id                  text,
    hash_linha                text,
    PRIMARY KEY (uuid, uf)
);
COMMENT ON TABLE ref.desmatamento_prodes IS 'Desmatamento anual do PRODES por UF; o polígono na divisa entra nas duas UFs (ADR 0013 e 0015) [histórico: acrescimo]';
COMMENT ON COLUMN ref.desmatamento_prodes.geometria IS 'Declarado no contrato: Geometry, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_ref_desmatamento_prodes_geometria ON ref.desmatamento_prodes USING gist (geometria);
CREATE INDEX ix_ref_desmatamento_prodes_carga_id ON ref.desmatamento_prodes (carga_id);

-- ref.quilombola_ibge
CREATE TABLE ref.quilombola_ibge (
    cod_tq                    text NOT NULL,
    nome                      text,
    situacao                  text,
    uf                        text,
    data_referencia           timestamp,
    geometria                 geometry(Geometry, 4674),
    alertas                   text,
    carga_id                  text,
    PRIMARY KEY (cod_tq)
);
COMMENT ON TABLE ref.quilombola_ibge IS 'Territórios quilombolas do Censo 2022 (IBGE) [histórico: fotografia]';
COMMENT ON COLUMN ref.quilombola_ibge.geometria IS 'Declarado no contrato: MultiPolygon, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_ref_quilombola_ibge_geometria ON ref.quilombola_ibge USING gist (geometria);
CREATE INDEX ix_ref_quilombola_ibge_carga_id ON ref.quilombola_ibge (carga_id);

-- ref.quilombola_incra
CREATE TABLE ref.quilombola_incra (
    id_incra                  text NOT NULL,
    nome                      text,
    situacao                  text,
    uf                        text,
    municipio                 text,
    processo                  text,
    superintendencia          text,
    area_ha                   double precision,
    data_publicacao           timestamp,
    data_cadastro             timestamp,
    geometria                 geometry(Geometry, 4674),
    alertas                   text,
    carga_id                  text,
    PRIMARY KEY (id_incra)
);
COMMENT ON TABLE ref.quilombola_incra IS 'Áreas quilombolas do INCRA, republicadas pelo CMR/FUNAI (ADR 0016) [histórico: fotografia]';
COMMENT ON COLUMN ref.quilombola_incra.geometria IS 'Declarado no contrato: MultiPolygon, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_ref_quilombola_incra_geometria ON ref.quilombola_incra USING gist (geometria);
CREATE INDEX ix_ref_quilombola_incra_carga_id ON ref.quilombola_incra (carga_id);

-- ref.embargo_ibama: geometria só do perfil completo
ALTER TABLE ref.embargo_ibama ADD COLUMN geometria geometry(Geometry, 4674);
COMMENT ON COLUMN ref.embargo_ibama.geometria IS 'Declarado no contrato: Geometry, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_ref_embargo_ibama_geometria ON ref.embargo_ibama USING gist (geometria);

-- visões das tabelas acima
CREATE OR REPLACE VIEW ref.embargo_ibama_vigente AS
SELECT * FROM ref.embargo_ibama
WHERE valido_ate IS NULL;
