-- GERADO por `python -m pipeline.armazenamento.ddl` a partir de contratos/. Não edite à mão:
-- mude o contrato e gere de novo (o teste tests/test_banco_ddl.py acusa o arquivo desatualizado).

-- Segurança por linha (ADR 0017), em Postgres puro: vale no Neon, no Supabase e no local.
-- Quem usa a API define a organização da conexão: SET app.organizacao_id = '<uuid>'.
-- Sem a variável, current_setting(..., true) dá NULL e nenhuma linha passa.
-- O dono das tabelas (quem carrega) não é afetado: não há FORCE ROW LEVEL SECURITY.

-- papel da futura API: só SELECT e INSERT
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agrovalid_app') THEN
        CREATE ROLE agrovalid_app NOLOGIN;
    END IF;
END
$$;

-- Deixa quem migra usar SET ROLE agrovalid_app (testes e a API, que entra como esse papel).
GRANT agrovalid_app TO CURRENT_USER;

GRANT USAGE ON SCHEMA meta, geo, ref, cad, diag TO agrovalid_app;
GRANT SELECT ON ALL TABLES IN SCHEMA meta, geo, ref, cad, diag TO agrovalid_app;
GRANT INSERT ON ALL TABLES IN SCHEMA cad, diag TO agrovalid_app;

-- Tabelas e visões criadas depois (a 0003, a 0005) herdam as mesmas permissões.
ALTER DEFAULT PRIVILEGES IN SCHEMA meta, geo, ref, cad, diag GRANT SELECT ON TABLES TO agrovalid_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA cad, diag GRANT INSERT ON TABLES TO agrovalid_app;

-- cad.area_producao
ALTER TABLE cad.area_producao ENABLE ROW LEVEL SECURITY;
CREATE POLICY area_producao_leitura ON cad.area_producao FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY area_producao_insercao ON cad.area_producao FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.carteira
ALTER TABLE cad.carteira ENABLE ROW LEVEL SECURITY;
CREATE POLICY carteira_leitura ON cad.carteira FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY carteira_insercao ON cad.carteira FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.carteira_item
ALTER TABLE cad.carteira_item ENABLE ROW LEVEL SECURITY;
CREATE POLICY carteira_item_leitura ON cad.carteira_item FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY carteira_item_insercao ON cad.carteira_item FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.consentimento
ALTER TABLE cad.consentimento ENABLE ROW LEVEL SECURITY;
CREATE POLICY consentimento_leitura ON cad.consentimento FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY consentimento_insercao ON cad.consentimento FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.documento_trazido
ALTER TABLE cad.documento_trazido ENABLE ROW LEVEL SECURITY;
CREATE POLICY documento_trazido_leitura ON cad.documento_trazido FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY documento_trazido_insercao ON cad.documento_trazido FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.imovel
ALTER TABLE cad.imovel ENABLE ROW LEVEL SECURITY;
CREATE POLICY imovel_leitura ON cad.imovel FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY imovel_insercao ON cad.imovel FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.organizacao
ALTER TABLE cad.organizacao ENABLE ROW LEVEL SECURITY;
CREATE POLICY organizacao_leitura ON cad.organizacao FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY organizacao_insercao ON cad.organizacao FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.produtor
ALTER TABLE cad.produtor ENABLE ROW LEVEL SECURITY;
CREATE POLICY produtor_leitura ON cad.produtor FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY produtor_insercao ON cad.produtor FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.produtor_imovel
ALTER TABLE cad.produtor_imovel ENABLE ROW LEVEL SECURITY;
CREATE POLICY produtor_imovel_leitura ON cad.produtor_imovel FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY produtor_imovel_insercao ON cad.produtor_imovel FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- cad.usuario
ALTER TABLE cad.usuario ENABLE ROW LEVEL SECURITY;
CREATE POLICY usuario_leitura ON cad.usuario FOR SELECT
    USING (organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY usuario_insercao ON cad.usuario FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- diag.conferencia_ab_s
ALTER TABLE diag.conferencia_ab_s ENABLE ROW LEVEL SECURITY;
CREATE POLICY conferencia_ab_s_leitura ON diag.conferencia_ab_s FOR SELECT
    USING (organizacao_id IS NULL OR organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY conferencia_ab_s_insercao ON diag.conferencia_ab_s FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- diag.criterio
ALTER TABLE diag.criterio ENABLE ROW LEVEL SECURITY;
CREATE POLICY criterio_leitura ON diag.criterio FOR SELECT
    USING (organizacao_id IS NULL OR organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY criterio_insercao ON diag.criterio FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- diag.evidencia
ALTER TABLE diag.evidencia ENABLE ROW LEVEL SECURITY;
CREATE POLICY evidencia_leitura ON diag.evidencia FOR SELECT
    USING (organizacao_id IS NULL OR organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY evidencia_insercao ON diag.evidencia FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- diag.execucao
ALTER TABLE diag.execucao ENABLE ROW LEVEL SECURITY;
CREATE POLICY execucao_leitura ON diag.execucao FOR SELECT
    USING (organizacao_id IS NULL OR organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY execucao_insercao ON diag.execucao FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));

-- diag.execucao_carga
ALTER TABLE diag.execucao_carga ENABLE ROW LEVEL SECURITY;
CREATE POLICY execucao_carga_leitura ON diag.execucao_carga FOR SELECT
    USING (execucao_id IN (SELECT execucao_id FROM diag.execucao));
CREATE POLICY execucao_carga_insercao ON diag.execucao_carga FOR INSERT
    WITH CHECK (execucao_id IN (SELECT execucao_id FROM diag.execucao));

-- diag.resultado_imovel
ALTER TABLE diag.resultado_imovel ENABLE ROW LEVEL SECURITY;
CREATE POLICY resultado_imovel_leitura ON diag.resultado_imovel FOR SELECT
    USING (organizacao_id IS NULL OR organizacao_id = current_setting('app.organizacao_id', true));
CREATE POLICY resultado_imovel_insercao ON diag.resultado_imovel FOR INSERT
    WITH CHECK (organizacao_id = current_setting('app.organizacao_id', true));
