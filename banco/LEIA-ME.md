# Banco (PostgreSQL com PostGIS)

O banco é uma cópia do lago Parquet, refeita a qualquer momento (ADR [0011](../docs/arquitetura/adr/0011-persistir-em-parquet-por-uf-e-adiar-o-postgis.md) e [0017](../docs/arquitetura/adr/0017-separar-o-dado-em-cinco-esquemas-guardar-historico-no-lago-e-carregar-um-perfil-lite.md)). As tabelas saem dos contratos em `contratos/`; ninguém escreve DDL de tabela à mão.

| Arquivo | O que é |
|---|---|
| `docker-compose.yml` | PostGIS 17-3.5 (`imresamu/postgis`, a imagem da medição do ADR 0011, com build arm64), porta 5433 no host, volume nomeado `agrovalid_pgdata` |
| `migracoes/0001_extensoes_e_esquemas.sql` | PostGIS, os cinco esquemas (`meta`, `geo`, `ref`, `cad`, `diag`) e a tabela `meta.migracao`. Escrita à mão |
| `migracoes/0002_tabelas_lite.sql` | Tabelas do perfil lite. **Gerada** |
| `migracoes/0003_tabelas_completo.sql` | Tabelas do perfil completo e as geometrias que o lite não leva. **Gerada**; só se aplica no perfil completo |
| `migracoes/0004_seguranca_por_linha.sql` | Papel `agrovalid_app` e segurança por linha em `cad` e `diag`. **Gerada** |
| `migracoes/0005_visoes.sql` | `<tabela>_vigente` e `diag.mudanca`. **Gerada** |

As migrações 0002 a 0005 são geradas por `python -m pipeline.armazenamento.ddl`. O teste `tests/test_banco_ddl.py` falha se um contrato mudou e elas não foram regeradas.

## Subir local

```bash
docker compose -f banco/docker-compose.yml up -d --wait
export AGROVALID_DATABASE_URL=postgresql://agrovalid:agrovalid@localhost:5433/agrovalid
```

Se a 5433 estiver ocupada por outro contêiner, troque a porta do host: `AGROVALID_PG_PORTA=5434 docker compose -f banco/docker-compose.yml up -d --wait` (e use a 5434 na URL). `docker compose -f banco/docker-compose.yml down` para; o volume fica, e `down -v` o apaga.

## Aplicar as migrações e carregar

```bash
.venv/bin/python -m pipeline.armazenamento.banco --perfil lite --migrar
.venv/bin/python -m pipeline.armazenamento.banco --perfil completo --migrar
.venv/bin/python -m pipeline.armazenamento.banco --perfil lite --tabelas ref.embargo_ibama geo   # só algumas
```

- A URL vem de `--url` ou de `AGROVALID_DATABASE_URL`. Sem ela, o comando para com erro.
- `--migrar` aplica, em ordem, as migrações que faltam e as registra em `meta.migracao`. A 0003 só entra no perfil completo. Sem `--migrar`, o banco precisa estar migrado.
- Cada tabela é recarregada por inteiro, numa transação: `TRUNCATE` e `COPY`. Rodar de novo dá o mesmo resultado.
- O que entra: `fotografia`, só a versão vigente; `validade`, `acrescimo`, `por_consulta` e `registro`, todo o histórico. As visões `<tabela>_vigente` dão o estado atual.
- A tabela que ainda não está no lago (`cad` e `diag` vazios) é pulada com aviso.
- Ao final, imprime as linhas e o tamanho por tabela (`pg_total_relation_size`) e o total.

Perfis: o **lite** leva `meta`, `geo`, `cad`, `diag`, as camadas pequenas e o embargo do IBAMA **sem geometria**; o **completo** acrescenta DETER, PRODES, quilombolas (INCRA e IBGE) e a geometria do embargo. Tabela `fora` nunca vai ao banco. O perfil de cada tabela e da geometria está no contrato (`perfil_banco`).

Convenções do banco:
- A coluna de geometria vira `geometria geometry(Geometry, 4674)`. O tipo declarado no contrato (MultiPolygon etc.) está no `COMMENT` da coluna, porque os dados reais misturam Polygon e MultiPolygon. Vai como EWKT (`SRID=4674;...`).
- `data_hora` vira `timestamp` sem fuso, em UTC. Valor com fuso é convertido antes de carregar.
- Enquanto uma fonte não grava no lago, o carregador lê o legado de `data/processed/` (via `lago.ler`), que não tem as colunas de controle: `carga_id` vira `legado` e `valido_de`/`consultado_em` recebem o momento da carga. Linhas do legado com chave nula ou repetida são deixadas de fora, com aviso.

## Ligar no Neon ou no Supabase

Só a URL muda; as migrações são Postgres puro.

```bash
export AGROVALID_DATABASE_URL='postgresql://USUARIO:SENHA@HOST:5432/BANCO?sslmode=require'
.venv/bin/python -m pipeline.armazenamento.banco --perfil lite --migrar
```

- Use a conexão **direta** (no Neon, o host sem `-pooler`; no Supabase, a porta 5432 ou o pooler em modo sessão), não o pooler em modo transação: o `COPY` e as migrações em bloco pedem uma sessão inteira.
- Carregue o **lite**. O completo (cerca de 2 GB, o PRODES é quase tudo) não cabe nos planos gratuitos.
- A extensão `postgis` precisa estar disponível no projeto (no Supabase, ative em Database > Extensions; no Neon, o `CREATE EXTENSION` da migração 0001 basta).
- Ligar a um serviço externo envia dado para fora da máquina: faça só com a confirmação do responsável pelo projeto. Os testes e o orçamento deste repositório nunca se conectam fora do `localhost`.

Limites gratuitos (conferidos em 30/10/2026; ADR 0011):

| Serviço | Limite | Observação |
|---|---|---|
| Supabase | 500 MB por projeto | O projeto pausa depois de 1 semana sem uso |
| Neon | 1 GB por projeto (20 GB no total) | PostGIS disponível |

O tamanho medido de cada perfil está em [`docs/evidencias/persistencia/01_orcamento_banco.md`](../docs/evidencias/persistencia/01_orcamento_banco.md).

## Segurança por linha

Em `cad` e `diag`, cada tabela com `organizacao_id` só mostra e só aceita linhas da organização da conexão. A API entra como o papel `agrovalid_app` (sem login; só `SELECT` e `INSERT`) e informa a organização antes de consultar:

```sql
SET ROLE agrovalid_app;
SELECT set_config('app.organizacao_id', '<uuid da organização>', false);
SELECT * FROM cad.imovel;   -- só os imóveis dessa organização
```

- Sem `app.organizacao_id`, nenhuma linha passa.
- Em `diag`, a linha com `organizacao_id` nulo (demonstração) é visível a todos; só a organização dona insere.
- `diag.execucao_carga`, que não tem `organizacao_id`, segue a execução.
- `diag.mudanca` usa `security_invoker`: quem consulta só vê as mudanças da própria organização.
- O dono (quem migra e carrega) não é afetado: não há `FORCE ROW LEVEL SECURITY`.
- No Supabase, o JWT da API preenche a variável depois.

## Testes

```bash
.venv/bin/python -m pytest                # offline; confere que as migrações geradas estão em dia
.venv/bin/python -m pytest --banco        # também migração, carga, segurança por linha e diag.mudanca
```

Os testes de banco criam e apagam bancos próprios no servidor de `AGROVALID_TEST_URL` (padrão `postgresql://agrovalid:agrovalid@localhost:5433/postgres`; o usuário precisa poder criar bancos).
