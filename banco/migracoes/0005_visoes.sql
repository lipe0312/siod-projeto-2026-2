-- GERADO por `python -m pipeline.armazenamento.ddl` a partir de contratos/. Não edite à mão:
-- mude o contrato e gere de novo (o teste tests/test_banco_ddl.py acusa o arquivo desatualizado).

-- Visões. O estado vigente vem do lago; no banco as tabelas guardam todas as versões.

-- geo.imovel_car_vigente
CREATE OR REPLACE VIEW geo.imovel_car_vigente AS
SELECT DISTINCT ON (cod_imovel) * FROM geo.imovel_car
ORDER BY cod_imovel, consultado_em DESC;

-- ref.embargo_ibama_vigente
CREATE OR REPLACE VIEW ref.embargo_ibama_vigente AS
SELECT * FROM ref.embargo_ibama
WHERE valido_ate IS NULL;

-- ref.lista_suja_vigente
CREATE OR REPLACE VIEW ref.lista_suja_vigente AS
SELECT * FROM ref.lista_suja
WHERE valido_ate IS NULL;

-- diag.mudanca
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
       c_atual.chave,
       c_atual.criterio,
       c_antes.situacao AS situacao_anterior,
       c_atual.situacao AS situacao_atual,
       antes.gerado_em  AS data_anterior,
       atual.gerado_em  AS data_atual,
       antes.resultado_id AS resultado_anterior_id,
       atual.resultado_id AS resultado_atual_id
FROM ordenado atual
JOIN ordenado antes
  ON antes.ordem = 2
 AND antes.cod_imovel = atual.cod_imovel
 AND antes.organizacao_id IS NOT DISTINCT FROM atual.organizacao_id
JOIN diag.criterio c_atual ON c_atual.resultado_id = atual.resultado_id
JOIN diag.criterio c_antes ON c_antes.resultado_id = antes.resultado_id AND c_antes.chave = c_atual.chave
WHERE atual.ordem = 1
  AND c_antes.situacao IS DISTINCT FROM c_atual.situacao;

COMMENT ON VIEW diag.mudanca IS 'Critério cuja situação mudou entre as duas últimas execuções de um imóvel, por organização.';
