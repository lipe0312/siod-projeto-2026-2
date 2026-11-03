# Persistir em Parquet particionado agora e em PostgreSQL com PostGIS depois

Situação: **PostgreSQL com PostGIS adiado**, sem prioridade, por decisão de 30/10/2026. Até lá vale o Parquet particionado por UF, sem custo. Complementada pelo [ADR 0017](0017-separar-o-dado-em-cinco-esquemas-guardar-historico-no-lago-e-carregar-um-perfil-lite.md) (03/11/2026): esquemas, histórico no lago e perfil lite do banco.

## Context and Problem Statement

Até a Atividade 04, o pipeline grava Parquet em `data/processed/`, e cada pré-diagnóstico carregava o PRODES inteiro na memória. Três decisões de 30/10/2026 mudam a carga:

* recorte nacional, com a UF entrando no lote quando o primeiro imóvel dela é consultado ([ADR 0013](0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md));
* histórico das fichas e das respostas do AB+S ([ADR 0012](0012-conferir-o-prediagnostico-com-o-relatorio-ab-s-do-imovel.md));
* atualização mensal por agendamento.

A API (Aula 05) e o acesso por técnico (Aula 08) vêm depois. A restrição do momento é **não pagar nada**.

Medições de 30/10/2026 ([`evidencias/atividade-04/cobertura-e-persistencia/`](../../evidencias/atividade-04/cobertura-e-persistencia/), scripts 02 e 04). A consulta foi a mesma nas três formas: o que do PRODES, do DETER e do IBAMA toca cada um de 300 CARs de Patrocínio, sobre 397.017 geometrias.

| Forma | Carga | Consulta por CAR | Espaço | Memória por processo | Achados |
|---|---:|---:|---:|---:|---:|
| Parquet + STRtree em memória | 1,6 s a cada processo | 0,01 ms | 139,9 MB | +1.176 MB | 47 |
| DuckDB spatial, índice R-tree | 1,4 s, uma vez | 0,32 ms | 370,2 MB | — | 47 |
| PostgreSQL 17 + PostGIS 3.5, índice GiST | 12,2 s, uma vez | 0,63 ms | 276,8 MB | — | 47 |

As três formas acharam os mesmos 47 objetos, CAR a CAR, e todas respondem em menos de 1 ms por consulta. O que pesa é a memória: no modelo antigo, o PRODES do Brasil inteiro (cerca de 1,5 milhão de polígonos) precisaria de cerca de 5 GB em cada processo, numa extrapolação linear.

## Considered Options

* PostgreSQL com PostGIS agora (local, gerenciado ou numa VM)
* DuckDB spatial num arquivo
* Parquet particionado por UF agora, e PostgreSQL com PostGIS quando houver API e mais de um usuário

## Decision Outcome

Chosen option: "Parquet particionado por UF agora, e PostgreSQL com PostGIS depois", because resolve o problema medido (a memória) sem custo nem serviço a operar. O pré-diagnóstico lê só a partição da UF do imóvel. As razões para um banco (escrita concorrente com leitura, permissão por técnico, histórico de fichas) só aparecem com a API e com mais de um usuário.

Agora:
1. **PRODES em partições por UF** (`data/processed/inpe_prodes/uf=XX/part.parquet`). A partição é criada quando o primeiro imóvel da UF é consultado, e a verificação mensal regrava só as partições que mudaram.
2. **As demais fontes nacionais** (IBAMA, DETER, Lista Suja, terras indígenas, unidades de conservação, quilombolas) continuam num Parquet cada uma. As três camadas de áreas protegidas somam 4.461 feições.
3. **O Parquet é o contrato entre etapas:** limpo, validado, com procedência e reproduzível sem banco. O banco, quando vier, é carregado a partir dele.
4. **Agendamento sem custo:** `crontab` na máquina do autor, todo mês (README, seção 6). O GitHub Actions não serve: o lote fica fora do repositório, e o agrobr registrou que o INCRA não respondeu a acessos de fora do Brasil, inclusive pelo GitHub Actions.

Depois (passo futuro, sem prioridade): PostgreSQL com PostGIS, pelos motivos que a medição mostrou.
* **Concorrência:** sem servidor, o DuckDB aceita um processo que lê e escreve ou vários que só leem ([DuckDB, Concurrency](https://duckdb.org/docs/2.0/connect/concurrency.html)); o agendador vai escrever enquanto a API lê.
* **Permissões:** o PostgreSQL tem papéis e segurança por linha para o acesso por técnico.
* **Índice:** o GiST respondeu em menos de 1 ms por CAR.

Opções sem custo para esse passo, conferidas em 30/10/2026:

| Opção | Limite gratuito | Cabe? |
|---|---|---|
| PostgreSQL + PostGIS local (Docker; `imresamu/postgis:17-3.5`, que tem build arm64) | Disco da máquina | Sim; foi o usado na medição |
| Neon, plano gratuito | 1 GB por projeto, 20 GB no total, PostGIS disponível ([changelog de 02/10/2026](https://neon.com/docs/changelog/2026-10-02)) | Sim, se o lote ficar nas UFs consultadas; o Brasil inteiro (cerca de 1,2 GB estimados) não cabe num projeto |
| Supabase, plano gratuito | 500 MB por projeto; pausa depois de 1 semana sem uso ([preços](https://supabase.com/pricing)) | Só para um recorte pequeno |

### Consequences

* Good, because o pré-diagnóstico deixa de carregar o Brasil inteiro na memória, sem custo e sem serviço novo para operar.
* Good, because o recorte cresce com o uso: só entram as UFs dos imóveis consultados.
* Good, because a medição fica registrada: quando a API vier, a troca para o PostGIS já tem números e uma opção gratuita (Neon) que comporta o recorte por UF.
* Bad, because o Parquet não tem escrita concorrente nem controle de acesso. Por enquanto, um único processo de cada vez pode atualizar o lote.
* Bad, because o histórico das fichas continua em arquivos (`data/processed/prediagnostico/`), sem consulta.
* Bad, because o `crontab` depende da máquina do autor estar ligada no dia.
