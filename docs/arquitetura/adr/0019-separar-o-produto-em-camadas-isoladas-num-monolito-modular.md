# Separar o produto em camadas isoladas num monólito modular

Situação: **proposto em 05/11/2026, para lapidar**. Visão geral em [`evolucao/README.md`](../evolucao/README.md).

## Context and Problem Statement

Até a #8, a AgroValid é um pipeline em lote que grava no lago e no banco e gera HTML. Com a API (#10), o front e mais de uma cooperativa, o sistema passa a ter porta aberta para a internet e dados de clientes diferentes no mesmo banco. É preciso decidir como separar as partes para que uma falha numa delas não entregue as outras, sem criar uma operação cara para um projeto pequeno.

## Considered Options

* Tudo num processo só (pipeline, API e páginas juntos)
* Monólito modular: um repositório, pacotes separados (`pipeline/`, `api/`, `web/`), implantados separados, conversando só pelo banco e pela API
* Microsserviços por domínio desde já

## Decision Outcome

Chosen option: "Monólito modular", because dá fronteiras claras de segurança (cada camada com seu papel no banco e sua superfície) sem rede interna, fila ou orquestração para operar.

Regras:
* Cada camada fala só com a vizinha: front → API → banco ← pipeline ← fontes. A API não lê o lago nem importa `pipeline/`; o front não fala com o banco nem com o provedor de identidade.
* Um papel de banco por camada, com o mínimo: `agrovalid_carga` (pipeline, escreve), `agrovalid_leitura` (API, só `SELECT`, novo) e `agrovalid_app` (escrita futura do produto). Nenhum com `BYPASSRLS`.
* O resultado pesado é pré-calculado pelo pipeline em `diag.*`; a API só lê.
* Um teste confere que `api/` não importa `pipeline/` e vice-versa.

### Consequences

* Good, because uma falha de autorização na API ainda esbarra na RLS e num papel sem escrita.
* Good, because a API fica leve e barata de escalar: lê resultado pronto por índice.
* Bad, because a API depende do pipeline ter rodado; uma carteira nova só aparece depois da próxima execução (aceitável: a rotina é mensal).
* Bad, because pede disciplina para não atalhar entre pacotes; o teste de importação vigia.
