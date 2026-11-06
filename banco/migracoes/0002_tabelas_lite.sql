-- GERADO por `python -m pipeline.armazenamento.ddl` a partir de contratos/. Não edite à mão:
-- mude o contrato e gere de novo (o teste tests/test_banco_ddl.py acusa o arquivo desatualizado).

-- Perfil lite: cabe nos planos gratuitos do Supabase (500 MB) e do Neon (1 GB por projeto).
-- Embargo do IBAMA entra sem geometria; ela vem na 0003, só no perfil completo.
-- data_hora vira timestamp sem fuso, no horário de Brasília (America/Sao_Paulo).

-- cad.area_producao
CREATE TABLE cad.area_producao (
    area_id                   text NOT NULL,
    organizacao_id            text NOT NULL,
    imovel_id                 text NOT NULL,
    commodity                 text,
    origem                    text,
    criado_em                 timestamp NOT NULL,
    geometria                 geometry(Geometry, 4674) NOT NULL,
    PRIMARY KEY (area_id)
);
COMMENT ON TABLE cad.area_producao IS 'Polígono da área de produção (EUDR), quando não é o imóvel inteiro [histórico: registro]';
COMMENT ON COLUMN cad.area_producao.geometria IS 'Declarado no contrato: MultiPolygon, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_cad_area_producao_geometria ON cad.area_producao USING gist (geometria);
CREATE INDEX ix_cad_area_producao_organizacao_id ON cad.area_producao (organizacao_id);

-- cad.carteira
CREATE TABLE cad.carteira (
    carteira_id               text NOT NULL,
    organizacao_id            text NOT NULL,
    arquivo_origem            text,
    sha256                    text,
    importada_em              timestamp NOT NULL,
    linhas                    bigint,
    linhas_com_problema       bigint,
    PRIMARY KEY (carteira_id)
);
COMMENT ON TABLE cad.carteira IS 'Planilha importada por uma organização [histórico: registro]';
CREATE INDEX ix_cad_carteira_organizacao_id ON cad.carteira (organizacao_id);

-- cad.carteira_item
CREATE TABLE cad.carteira_item (
    carteira_id               text NOT NULL,
    organizacao_id            text NOT NULL,
    linha                     bigint NOT NULL,
    produtor_id               text,
    imovel_id                 text,
    problema_na_linha         text,
    extras_json               jsonb,
    PRIMARY KEY (carteira_id, linha)
);
COMMENT ON TABLE cad.carteira_item IS 'Cada linha da planilha importada, com o problema encontrado na conferência [histórico: registro]';
CREATE INDEX ix_cad_carteira_item_organizacao_id ON cad.carteira_item (organizacao_id);

-- cad.chave_api
CREATE TABLE cad.chave_api (
    chave_id                  text NOT NULL,
    organizacao_id            text NOT NULL,
    identificador             text NOT NULL,
    hash_sha256               text NOT NULL,
    escopo                    text NOT NULL,
    criada_em                 timestamp NOT NULL,
    expira_em                 timestamp NOT NULL,
    revogada_em               timestamp,
    ultimo_uso_em             timestamp,
    PRIMARY KEY (chave_id)
);
COMMENT ON TABLE cad.chave_api IS 'Chave de API de uma organização (ADR 0021): só o SHA-256 da chave, escopo só leitura, validade de 90 dias, revogação e último uso. Vive só no banco (a API a mantém); nunca vai ao lago [histórico: registro]';
CREATE INDEX ix_cad_chave_api_organizacao_id ON cad.chave_api (organizacao_id);
CREATE INDEX ix_cad_chave_api_hash_sha256 ON cad.chave_api (hash_sha256);

-- cad.consentimento
CREATE TABLE cad.consentimento (
    consentimento_id          text NOT NULL,
    organizacao_id            text NOT NULL,
    produtor_id               text NOT NULL,
    finalidade                text NOT NULL,
    versao_termo              text NOT NULL,
    concedido_em              timestamp NOT NULL,
    revogado_em               timestamp,
    PRIMARY KEY (consentimento_id)
);
COMMENT ON TABLE cad.consentimento IS 'Consentimento LGPD do produtor para uso do documento e do CAR [histórico: registro]';
CREATE INDEX ix_cad_consentimento_organizacao_id ON cad.consentimento (organizacao_id);

-- cad.documento_trazido
CREATE TABLE cad.documento_trazido (
    documento_id              text NOT NULL,
    organizacao_id            text NOT NULL,
    imovel_id                 text NOT NULL,
    tipo                      text NOT NULL,
    valor                     text NOT NULL,
    informado_em              timestamp NOT NULL,
    PRIMARY KEY (documento_id)
);
COMMENT ON TABLE cad.documento_trazido IS 'O que o produtor trouxe: CCIR, código SIGEF, código do relatório AB+S [histórico: registro]';
CREATE INDEX ix_cad_documento_trazido_organizacao_id ON cad.documento_trazido (organizacao_id);

-- cad.imovel
CREATE TABLE cad.imovel (
    imovel_id                 text NOT NULL,
    organizacao_id            text NOT NULL,
    cod_car                   text,
    lat                       double precision,
    lon                       double precision,
    nome_area                 text,
    commodity                 text,
    criado_em                 timestamp NOT NULL,
    PRIMARY KEY (imovel_id)
);
COMMENT ON TABLE cad.imovel IS 'Imóvel atendido: o código do CAR ou, sem ele, a coordenada informada. O polígono fica em geo.imovel_car [histórico: registro]';
CREATE INDEX ix_cad_imovel_cod_car ON cad.imovel (cod_car);
CREATE INDEX ix_cad_imovel_organizacao_id ON cad.imovel (organizacao_id);

-- cad.organizacao
CREATE TABLE cad.organizacao (
    organizacao_id            text NOT NULL,
    nome                      text NOT NULL,
    tipo                      text NOT NULL,
    uf                        text,
    criado_em                 timestamp NOT NULL,
    PRIMARY KEY (organizacao_id)
);
COMMENT ON TABLE cad.organizacao IS 'Cliente: cooperativa, empresa de assistência técnica ou outra [histórico: registro]';
CREATE INDEX ix_cad_organizacao_organizacao_id ON cad.organizacao (organizacao_id);

-- cad.produtor
CREATE TABLE cad.produtor (
    produtor_id               text NOT NULL,
    organizacao_id            text NOT NULL,
    id_produtor               text NOT NULL,
    documento_hash            text,
    tipo_documento            text,
    criado_em                 timestamp NOT NULL,
    PRIMARY KEY (produtor_id)
);
COMMENT ON TABLE cad.produtor IS 'Produtor atendido; identificado pelo código da organização e pelo documento pseudonimizado, nunca pelo CPF (ADR 0002) [histórico: registro]';
CREATE INDEX ix_cad_produtor_documento_hash ON cad.produtor (documento_hash);
CREATE INDEX ix_cad_produtor_organizacao_id ON cad.produtor (organizacao_id);

-- cad.produtor_imovel
CREATE TABLE cad.produtor_imovel (
    organizacao_id            text NOT NULL,
    produtor_id               text NOT NULL,
    imovel_id                 text NOT NULL,
    vinculo                   text,
    PRIMARY KEY (produtor_id, imovel_id)
);
COMMENT ON TABLE cad.produtor_imovel IS 'Vínculo entre produtor e imóvel (proprietário, posseiro, arrendatário) [histórico: registro]';
CREATE INDEX ix_cad_produtor_imovel_organizacao_id ON cad.produtor_imovel (organizacao_id);

-- cad.usuario
CREATE TABLE cad.usuario (
    usuario_id                text NOT NULL,
    organizacao_id            text NOT NULL,
    nome                      text,
    email                     text,
    papel                     text NOT NULL,
    id_externo                text,
    criado_em                 timestamp NOT NULL,
    PRIMARY KEY (usuario_id)
);
COMMENT ON TABLE cad.usuario IS 'Técnico ou gestor de uma organização; id_externo liga ao provedor de login [histórico: registro]';
CREATE INDEX ix_cad_usuario_organizacao_id ON cad.usuario (organizacao_id);

-- diag.conferencia_ab_s
CREATE TABLE diag.conferencia_ab_s (
    conferencia_id            text NOT NULL,
    organizacao_id            text,
    imovel_id                 text,
    cod_imovel                text,
    uuid_relatorio            text NOT NULL,
    endpoint                  text,
    consultado_em             timestamp,
    status_resposta           text,
    criterio_ab_s             bigint,
    resultado_oficial         text,
    resultado_id              text,
    situacao_pipeline         text,
    concorda                  boolean,
    PRIMARY KEY (conferencia_id)
);
COMMENT ON TABLE diag.conferencia_ab_s IS 'Resultado oficial do AB+S ao lado do resultado do pipeline, por critério (ADR 0012) [histórico: registro]';
CREATE INDEX ix_diag_conferencia_ab_s_cod_imovel ON diag.conferencia_ab_s (cod_imovel);
CREATE INDEX ix_diag_conferencia_ab_s_organizacao_id ON diag.conferencia_ab_s (organizacao_id);

-- diag.criterio
CREATE TABLE diag.criterio (
    resultado_id              text NOT NULL,
    organizacao_id            text,
    chave                     text NOT NULL,
    criterio                  text,
    criterio_ab_s             bigint,
    situacao                  text NOT NULL,
    evidencia                 text,
    encaminhamento            text,
    fonte                     text,
    aviso                     text,
    ano_mes                   text NOT NULL,
    PRIMARY KEY (resultado_id, chave)
);
COMMENT ON TABLE diag.criterio IS 'Situação de cada critério de um resultado [histórico: registro]';
CREATE INDEX ix_diag_criterio_organizacao_id ON diag.criterio (organizacao_id);

-- diag.evidencia
CREATE TABLE diag.evidencia (
    evidencia_id              text NOT NULL,
    resultado_id              text NOT NULL,
    organizacao_id            text,
    chave_criterio            text NOT NULL,
    tabela                    text NOT NULL,
    registro_id               text NOT NULL,
    carga_id                  text,
    classe                    text,
    inter_ha                  double precision,
    fracao_objeto             double precision,
    fracao_car                double precision,
    largura_m                 double precision,
    data_imagem               timestamp,
    detalhes_json             jsonb,
    geometria                 geometry(Geometry, 4674),
    ano_mes                   text NOT NULL,
    PRIMARY KEY (evidencia_id)
);
COMMENT ON TABLE diag.evidencia IS 'Registro de ref que sustenta um critério, com a carga de origem e a geometria da interseção com o imóvel [histórico: registro]';
COMMENT ON COLUMN diag.evidencia.geometria IS 'Declarado no contrato: Geometry, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_diag_evidencia_geometria ON diag.evidencia USING gist (geometria);
CREATE INDEX ix_diag_evidencia_organizacao_id ON diag.evidencia (organizacao_id);
CREATE INDEX ix_diag_evidencia_carga_id ON diag.evidencia (carga_id);

-- diag.execucao
CREATE TABLE diag.execucao (
    execucao_id               text NOT NULL,
    organizacao_id            text,
    tipo                      text NOT NULL,
    carteira_id               text,
    iniciada_em               timestamp NOT NULL,
    terminada_em              timestamp,
    comando                   text,
    versao_codigo             text,
    ano_mes                   text NOT NULL,
    PRIMARY KEY (execucao_id)
);
COMMENT ON TABLE diag.execucao IS 'Uma rodada do pré-diagnóstico (carteira, demonstração ou consulta avulsa) [histórico: registro]';
CREATE INDEX ix_diag_execucao_organizacao_id ON diag.execucao (organizacao_id);

-- diag.execucao_carga
CREATE TABLE diag.execucao_carga (
    execucao_id               text NOT NULL,
    fonte                     text NOT NULL,
    carga_id                  text,
    PRIMARY KEY (execucao_id, fonte)
);
COMMENT ON TABLE diag.execucao_carga IS 'Carga de cada fonte usada numa execução (reprodutibilidade) [histórico: registro]';
CREATE INDEX ix_diag_execucao_carga_carga_id ON diag.execucao_carga (carga_id);

-- diag.resultado_imovel
CREATE TABLE diag.resultado_imovel (
    resultado_id              text NOT NULL,
    execucao_id               text NOT NULL,
    organizacao_id            text,
    imovel_id                 text,
    cod_imovel                text,
    uf                        text,
    cod_municipio             text,
    area_ha                   double precision,
    situacao                  text NOT NULL,
    resumo                    text,
    prioridade                bigint,
    n_pendencias              bigint,
    n_indicios                bigint,
    n_inconclusivos           bigint,
    n_nao_verificados         bigint,
    n_sem_ocorrencia          bigint,
    gerado_em                 timestamp NOT NULL,
    ficha                     text,
    ano_mes                   text NOT NULL,
    PRIMARY KEY (resultado_id)
);
COMMENT ON TABLE diag.resultado_imovel IS 'Resultado geral de um imóvel numa execução [histórico: registro]';
CREATE INDEX ix_diag_resultado_imovel_cod_imovel ON diag.resultado_imovel (cod_imovel);
CREATE INDEX ix_diag_resultado_imovel_organizacao_id ON diag.resultado_imovel (organizacao_id);

-- geo.bioma
CREATE TABLE geo.bioma (
    bioma                     text NOT NULL,
    nome                      text,
    geometria                 geometry(Geometry, 4674),
    carga_id                  text,
    PRIMARY KEY (bioma)
);
COMMENT ON TABLE geo.bioma IS 'Contorno dos biomas (INPE) [histórico: fotografia]';
COMMENT ON COLUMN geo.bioma.geometria IS 'Declarado no contrato: MultiPolygon, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_geo_bioma_geometria ON geo.bioma USING gist (geometria);
CREATE INDEX ix_geo_bioma_carga_id ON geo.bioma (carga_id);

-- geo.imovel_car
CREATE TABLE geo.imovel_car (
    cod_imovel                text NOT NULL,
    uf                        text NOT NULL,
    cod_municipio             text,
    municipio                 text,
    tipo_imovel               text,
    status_imovel             text,
    condicao                  text,
    area_declarada_ha         double precision,
    area_geom_ha              double precision,
    m_fiscal                  double precision,
    data_criacao              timestamp,
    data_atualizacao          timestamp,
    fracao_coberta_por_outros double precision,
    geometria                 geometry(Geometry, 4674) NOT NULL,
    alertas                   text,
    carga_id                  text,
    consultado_em             timestamp NOT NULL,
    PRIMARY KEY (cod_imovel, consultado_em)
);
COMMENT ON TABLE geo.imovel_car IS 'Imóvel do CAR consultado no WFS do SICAR (só os consultados; uma versão por consulta) [histórico: por_consulta]';
COMMENT ON COLUMN geo.imovel_car.geometria IS 'Declarado no contrato: MultiPolygon, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_geo_imovel_car_geometria ON geo.imovel_car USING gist (geometria);
CREATE INDEX ix_geo_imovel_car_cod_imovel ON geo.imovel_car (cod_imovel);
CREATE INDEX ix_geo_imovel_car_carga_id ON geo.imovel_car (carga_id);

-- geo.municipio
CREATE TABLE geo.municipio (
    cod_municipio             text NOT NULL,
    municipio                 text,
    uf                        text,
    chave                     text,
    carga_id                  text,
    PRIMARY KEY (cod_municipio)
);
COMMENT ON TABLE geo.municipio IS 'Municípios do IBGE com a chave de nome normalizado [histórico: fotografia]';
CREATE INDEX ix_geo_municipio_carga_id ON geo.municipio (carga_id);

-- geo.uf
CREATE TABLE geo.uf (
    uf                        text NOT NULL,
    cod_uf                    text,
    geometria                 geometry(Geometry, 4674),
    carga_id                  text,
    PRIMARY KEY (uf)
);
COMMENT ON TABLE geo.uf IS 'Contorno das UFs (IBGE), usado para recortar o PRODES e localizar o ponto [histórico: fotografia]';
COMMENT ON COLUMN geo.uf.geometria IS 'Declarado no contrato: MultiPolygon, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_geo_uf_geometria ON geo.uf USING gist (geometria);
CREATE INDEX ix_geo_uf_carga_id ON geo.uf (carga_id);

-- meta.carga
CREATE TABLE meta.carga (
    carga_id                  text,
    fonte                     text NOT NULL,
    tipo_dado                 text,
    iniciada_em               timestamp NOT NULL,
    status                    text NOT NULL,
    mensagem                  text,
    url                       text,
    sha256_entrada            text,
    registros_recebidos       bigint,
    registros_produzidos      bigint,
    registros_descartados     bigint,
    registros_com_alerta      bigint,
    tabelas_json              jsonb,
    entrada_json              jsonb,
    saida_json                jsonb,
    transformacoes_json       jsonb,
    PRIMARY KEY (carga_id)
);
COMMENT ON TABLE meta.carga IS 'Uma linha por execução de fonte (ResultadoFonte): entrada, saída e situação [histórico: registro]';
CREATE INDEX ix_meta_carga_carga_id ON meta.carga (carga_id);

-- meta.descarte
CREATE TABLE meta.descarte (
    carga_id                  text,
    fonte                     text NOT NULL,
    registro_id               text NOT NULL,
    motivo                    text,
    dados_json                jsonb,
    PRIMARY KEY (carga_id, registro_id)
);
COMMENT ON TABLE meta.descarte IS 'Registros descartados por carga, com o motivo e o registro original em JSON [histórico: registro]';
CREATE INDEX ix_meta_descarte_carga_id ON meta.descarte (carga_id);

-- meta.fonte
CREATE TABLE meta.fonte (
    fonte                     text NOT NULL,
    orgao                     text NOT NULL,
    nome                      text NOT NULL,
    tipo_dado                 text,
    acesso                    text,
    ritmo                     text,
    tabelas                   text,
    carga_id                  text,
    PRIMARY KEY (fonte)
);
COMMENT ON TABLE meta.fonte IS 'Catálogo de fontes, lido de contratos/fontes.yaml [histórico: fotografia]';
CREATE INDEX ix_meta_fonte_carga_id ON meta.fonte (carga_id);

-- meta.validacao
CREATE TABLE meta.validacao (
    carga_id                  text,
    fonte                     text NOT NULL,
    codigo                    text NOT NULL,
    descricao                 text,
    severidade                text NOT NULL,
    tratamento                text,
    verificados               bigint,
    ocorrencias               bigint,
    PRIMARY KEY (carga_id, codigo)
);
COMMENT ON TABLE meta.validacao IS 'Validações de cada carga (código, severidade, ocorrências) [histórico: registro]';
CREATE INDEX ix_meta_validacao_carga_id ON meta.validacao (carga_id);

-- ref.embargo_ibama
CREATE TABLE ref.embargo_ibama (
    id_embargo                text NOT NULL,
    num_tad                   text,
    ser_tad                   text,
    seq_tad                   text,
    data_embargo              timestamp,
    data_ultima_alteracao     timestamp,
    pos_corte_eudr            boolean,
    documento_hash            text,
    tipo_documento            text,
    cod_municipio             text,
    municipio                 text,
    uf                        text,
    latitude                  double precision,
    longitude                 double precision,
    area_ha                   double precision,
    biomas                    text,
    descricao_infracao        text,
    situacao                  text,
    data_desembargo           timestamp,
    alertas                   text,
    carga_id                  text,
    valido_de                 timestamp NOT NULL,
    valido_ate                timestamp,
    hash_linha                text,
    PRIMARY KEY (id_embargo, valido_de)
);
COMMENT ON TABLE ref.embargo_ibama IS 'Áreas embargadas do IBAMA, com documento pseudonimizado (ADR 0002 e 0003) [histórico: validade]';
CREATE INDEX ix_ref_embargo_ibama_documento_hash ON ref.embargo_ibama (documento_hash);
CREATE INDEX ix_ref_embargo_ibama_carga_id ON ref.embargo_ibama (carga_id);

-- ref.lista_suja
CREATE TABLE ref.lista_suja (
    chave_registro            text NOT NULL,
    id_registro               bigint,
    documento_hash            text,
    tipo_documento            text,
    uf                        text,
    estabelecimento           text NOT NULL,
    cnae                      text,
    cnae_agropecuaria         boolean,
    trabalhadores_envolvidos  bigint,
    ano_acao_fiscal           bigint,
    data_decisao              timestamp,
    data_inclusao             timestamp,
    data_inclusao_ultima      timestamp,
    data_atualizacao_cadastro timestamp,
    alertas                   text,
    carga_id                  text,
    valido_de                 timestamp NOT NULL,
    valido_ate                timestamp,
    hash_linha                text,
    PRIMARY KEY (chave_registro, valido_de)
);
COMMENT ON TABLE ref.lista_suja IS 'Cadastro de Empregadores do MTE (Lista Suja), com documento pseudonimizado; chave_registro é o hash de documento, estabelecimento, ano da ação e sequencial (id_registro é a linha do PDF e muda) [histórico: validade]';
CREATE INDEX ix_ref_lista_suja_documento_hash ON ref.lista_suja (documento_hash);
CREATE INDEX ix_ref_lista_suja_carga_id ON ref.lista_suja (carga_id);

-- ref.terra_indigena
CREATE TABLE ref.terra_indigena (
    terrai_codigo             text NOT NULL,
    nome                      text,
    etnia                     text,
    fase                      text,
    modalidade                text,
    uf                        text,
    municipio                 text,
    superficie_ha             double precision,
    data_atualizacao          timestamp,
    geometria                 geometry(Geometry, 4674),
    alertas                   text,
    carga_id                  text,
    PRIMARY KEY (terrai_codigo)
);
COMMENT ON TABLE ref.terra_indigena IS 'Terras indígenas da FUNAI (critério 5 do AB+S) [histórico: fotografia]';
COMMENT ON COLUMN ref.terra_indigena.geometria IS 'Declarado no contrato: MultiPolygon, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_ref_terra_indigena_geometria ON ref.terra_indigena USING gist (geometria);
CREATE INDEX ix_ref_terra_indigena_carga_id ON ref.terra_indigena (carga_id);

-- ref.territorio_quilombola
CREATE TABLE ref.territorio_quilombola (
    codigo                    text NOT NULL,
    nome                      text,
    situacao                  text,
    uf                        text,
    base                      text,
    data_referencia           timestamp,
    geometria                 geometry(Geometry, 4674),
    alertas                   text,
    carga_id                  text,
    PRIMARY KEY (codigo)
);
COMMENT ON TABLE ref.territorio_quilombola IS 'Camada combinada do critério 6: INCRA inteiro mais o território do IBGE que o INCRA não cobre (ADR 0016) [histórico: fotografia]';
COMMENT ON COLUMN ref.territorio_quilombola.geometria IS 'Declarado no contrato: MultiPolygon, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_ref_territorio_quilombola_geometria ON ref.territorio_quilombola USING gist (geometria);
CREATE INDEX ix_ref_territorio_quilombola_carga_id ON ref.territorio_quilombola (carga_id);

-- ref.unidade_conservacao
CREATE TABLE ref.unidade_conservacao (
    cd_cnuc                   text NOT NULL,
    nome                      text,
    categoria                 text,
    grupo                     text,
    esfera                    text,
    uf                        text,
    orgao_gestor              text,
    ano_criacao               bigint,
    qualidade_poligono        text,
    so_ponto                  boolean,
    geometria                 geometry(Geometry, 4674),
    alertas                   text,
    carga_id                  text,
    PRIMARY KEY (cd_cnuc)
);
COMMENT ON TABLE ref.unidade_conservacao IS 'Unidades de conservação do CNUC/MMA (critério 9 do AB+S) [histórico: fotografia]';
COMMENT ON COLUMN ref.unidade_conservacao.geometria IS 'Declarado no contrato: Geometry, SRID 4674. Os dados reais misturam Polygon e MultiPolygon; por isso a coluna aceita qualquer geometria. Vem de geometria_wkt do lago.';
CREATE INDEX ix_ref_unidade_conservacao_geometria ON ref.unidade_conservacao USING gist (geometria);
CREATE INDEX ix_ref_unidade_conservacao_carga_id ON ref.unidade_conservacao (carga_id);
