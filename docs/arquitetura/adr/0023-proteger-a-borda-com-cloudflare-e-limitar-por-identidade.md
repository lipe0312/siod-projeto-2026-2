# Proteger a borda com Cloudflare e limitar por identidade

Situação: **proposto em 05/11/2026, para lapidar**. Fontes de 11/2026: [WAF da Cloudflare](https://developers.cloudflare.com/waf/), [comparação de planos](https://icwt.cloud/en/blog/cloudflare-waf-plany-porownanie/), [Turnstile](https://tech-insider.org/cloudflare-turnstile-setup-2026/).

## Context and Problem Statement

Quando a API e o front forem públicos, vão receber varredura, força bruta, enxurrada de requisições e ataque distribuído por muitos IPs. Bloquear por IP derruba cooperativas inteiras atrás do mesmo IP (CGNAT, rede compartilhada). O orçamento é próximo de zero.

## Considered Options

* Cloudflare gratuita na frente + limite por identidade na API
* Cloudflare Pro desde o início
* WAF da nuvem (AWS WAF ou Cloud Armor)
* Só limite na aplicação, sem borda

## Decision Outcome

Chosen option: "Cloudflare gratuita + limite por identidade", because o plano gratuito já dá DDoS sem limite, o conjunto de regras gerenciadas gratuito, 5 regras próprias, 1 regra de limite por IP e o Turnstile. O limite por identidade na API cobre o que o plano gratuito não cobre: o ataque distribuído e o abuso por uma conta válida.

Regras:
* A origem só aceita tráfego da Cloudflare: túnel sem IP público, ou cabeçalho secreto conferido pela API (no Cloud Run, além disso, fechar o domínio `run.app`).
* Regra de limite da borda: grossa, por IP, só contra enxurrada. Ação: desafio gerenciado, não bloqueio.
* Limite da API por sessão, chave e organização (janela deslizante), com 429 e `Retry-After`.
* Turnstile em login, cadastro, redefinição de senha e contato.
* Login com atraso progressivo por conta, sem bloqueio fixo.
* Nenhuma rota anônima cara; o que é caro e repetido vai para cache por organização e execução.
* Degrau seguinte: Cloudflare Pro (US$ 20/mês: regras OWASP e mais regras de limite) quando houver usuários reais ou ataque recorrente.

### Consequences

* Good, because protege bem por US$ 0 e tem degrau pago claro.
* Good, because quem divide IP não é bloqueado por engano.
* Bad, because a Cloudflare processa o tráfego fora do Brasil: é transferência internacional, registrada no inventário LGPD e na política de privacidade.
* Bad, because a regra gratuita de limite é só por IP e com janela curta; o resto depende do código da API.
