# Autenticar com chave por organização agora e provedor de identidade com BFF depois

Situação: **decidido em 05/11/2026 para a fase 1** (chave por organização, desbloqueia a #10). A fase 2 (pessoas) está **proposta, para lapidar**. Pesquisa de preços em 11/2026: [Supabase](https://supabase.com/pricing).

## Context and Problem Statement

A #10 precisa saber de qual organização é cada requisição. Depois, técnicos vão entrar por um front no navegador. O que mais expõe um sistema assim é token no navegador (roubado por XSS), autenticação feita em casa e dado pessoal de usuário guardado fora do país.

## Considered Options

* A. Chave de API por organização agora; Supabase Auth (São Paulo) para pessoas depois, sempre pelo BFF
* B. Igual à A, com outro provedor gerenciado: Clerk ou Auth0
* C. Provedor próprio de código aberto (Keycloak ou Zitadel) numa VM
* D. Login próprio (senha e sessão feitas no projeto)

## Decision Outcome

Chosen option: "A", because não depende de serviço externo para a #10, e, para pessoas, junta identidade e banco no mesmo projeto e na mesma região (São Paulo), grátis até 50 mil usuários ativos por mês, com MFA por TOTP sem custo. O GoTrue, motor do Supabase Auth, é código aberto: dá para hospedar por conta própria se for preciso sair.

| | A. Supabase Auth | B. Clerk ou Auth0 | C. Keycloak/Zitadel próprio | D. Próprio |
|---|---|---|---|---|
| Custo inicial | Grátis | Grátis até um limite, caro depois | VM + manutenção | Grátis |
| Dado do usuário | Brasil | Exterior (transferência internacional) | Onde hospedar | Brasil |
| Superfície que nós mantemos | Pequena | Pequena | Grande (patches, backup, alta disponibilidade) | Enorme |
| Saída | Código aberto | Difícil | Já é nosso | — |
| Risco | Banco e identidade no mesmo fornecedor | Dependência e custo | Operação | Erro de implementação |

Se a #9 escolher o Neon em vez do Supabase, a opção B ou o Supabase Auth isolado voltam à mesa.

Fase 1 (servidor a servidor, #10):
* Chave com prefixo identificável (`agv_<ambiente>_...`), mostrada uma vez, guardada só como hash SHA-256; organização, escopo (só leitura), validade (90 dias), revogação e último uso.
* Tabela nova num contrato (uma mudança de contrato por vez).
* Nunca usada no navegador.

Fase 2 (pessoas, front):
* Fluxo PKCE conduzido pelo BFF (a própria API): o navegador só recebe o cookie `__Host-sessao` (`httpOnly`, `Secure`, `SameSite=Lax`). JWT e refresh token ficam no servidor.
* JWT validado pela chave pública do provedor; organização e papel vêm de uma tabela de membros em `cad`, nunca do cliente.
* MFA TOTP obrigatório para administrador da organização; Turnstile no login.
* Sessão curta com renovação silenciosa no servidor; sair revoga no provedor.

### Consequences

* Good, because nenhum token vive no navegador: XSS não consegue roubar sessão para usar em outra máquina.
* Good, because a #10 sai sem conta externa e sem esperar a #9.
* Bad, because o BFF exige sessão no servidor (tabela ou memória) e CSRF bem feito.
* Bad, because banco e identidade no mesmo fornecedor concentram o risco; mitigação: backup próprio do banco e a saída pelo GoTrue.
