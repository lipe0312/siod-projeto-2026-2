# Entregar por três ambientes, com histórico linear e deploy pelo CI

Situação: **proposto em 05/11/2026, para lapidar**. Detalhe em [`evolucao/ambientes-e-entrega.md`](../evolucao/ambientes-e-entrega.md).

## Context and Problem Statement

Hoje tudo roda na máquina do dono, e o merge é por squash depois do gate local. Com usuários, é preciso testar cada feature isolada, ver a `main` funcionando antes de produção, implantar sem credencial na máquina e manter um histórico que diga o que mudou e quando.

## Considered Options

* Três ambientes (local por feature, homologação, produção), deploy só pelo CI, histórico linear
* Dois ambientes (local e produção)
* Ambiente efêmero por PR (preview de cada branch na nuvem)

## Decision Outcome

Chosen option: "Três ambientes, deploy pelo CI, histórico linear", because separa o risco (homologação nunca tem dado real) por custo zero nos planos gratuitos. O ambiente por PR fica para depois: custa mais e multiplica a superfície exposta.

Regras:
* Local: cada worktree sobe a própria pilha (`docker compose`) com porta própria e dado sintético.
* Homologação: deploy automático a cada merge na `main`; dado sintético ou `demonstracao`; nunca cópia da produção.
* Produção: deploy por tag `vX.Y.Z` com aprovação manual no ambiente protegido do GitHub; o CI entra na nuvem por OIDC, sem chave guardada.
* A `main` exige histórico linear: a branch é rebaseada antes do merge; squash por padrão, rebase-merge quando os passos importam.
* `--force-with-lease` só na própria branch de feature, depois de rebase; nunca na `main`. (Muda a regra "nunca `--force`"; vale só com o aceite do dono.)
* Migrações em duas etapas: expandir e depois contrair.

Hospedagem da API, a escolher na fase 1:

| | Cloud Run (`southamerica-east1`) | Fly.io (`gru`) |
|---|---|---|
| Custo parado | Zero (escala a zero) | Pequeno (máquina ligada) |
| Fechar a origem atrás da Cloudflare | Cabeçalho secreto; balanceador do GCP é pago | Túnel da Cloudflare, simples |
| Deploy sem chave | OIDC nativo com o GitHub | Token de deploy |
| Curva | IAM do GCP | Baixa |

### Consequences

* Good, because nenhuma credencial de produção existe fora do CI e do cofre.
* Good, because cada versão em produção tem tag, notas e caminho de volta (imagem anterior).
* Bad, because homologação no plano grátis pausa sem uso: o primeiro acesso depois de uma semana é lento.
* Bad, because rebase exige `--force-with-lease` na branch, o que pede atenção quando duas pessoas mexem nela.
