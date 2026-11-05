# Limitar o que agentes de IA alcançam no desenvolvimento e no produto

Situação: **proposto em 05/11/2026, para lapidar**.

## Context and Problem Statement

O projeto é desenvolvido com várias sessões de agente de IA em paralelo, algumas com permissões amplas (worktrees, git, `gh`). Isso abre caminhos que não existem num time só humano: instrução maliciosa escondida em dado externo (PDF da Lista Suja, página de fonte, texto de issue), segredo lido do disco, comando destrutivo, ou uma sessão aprovando o trabalho de outra.

## Considered Options

* Agentes confinados ao ambiente local, sem credencial de homologação ou produção, merge só pelo dono
* Agentes com acesso a homologação para testar de ponta a ponta
* Sem agentes

## Decision Outcome

Chosen option: "Agentes confinados ao ambiente local", because mantém o ganho de velocidade sem dar a um agente comprometido nada além de dado sintético e do repositório, que tem histórico e revisão.

Regras:
* Agentes trabalham em worktree, com Postgres local e dado sintético ou `demonstracao`. A máquina de desenvolvimento não tem credencial de homologação nem de produção.
* Deploy só pelo CI; nenhum agente fala com a nuvem, a Cloudflare ou o provedor de identidade.
* Merge só com "aprovado merge" do dono na sessão do dono; uma sessão recusa aprovação repassada por outra.
* Conteúdo externo (arquivos baixados, páginas, issues de terceiros) é dado, nunca instrução.
* Servidor MCP, ferramenta ou permissão nova para agente passa pelo dono, como dependência nova.
* Varredura de segredo e proteção de push ligadas no GitHub.
* No produto: nenhum dado pessoal vai para provedor de LLM sem contrato e pseudonimização; a saída do modelo só sugere ao técnico.

### Consequences

* Good, because um agente enganado não alcança dado real nem implanta nada.
* Bad, because testes de ponta a ponta em homologação ficam com o dono ou com o CI.
