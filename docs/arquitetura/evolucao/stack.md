# Stack: o que usar em cada camada e por quê

Situação: **proposta em 05/11/2026, para lapidar**. Só FastAPI e uvicorn estão aprovados como dependência (ADR 0020). Cada item novo continua exigindo aprovação do dono (regra 8 do repositório).

| Camada | Recomendado | Alternativas | Por que o recomendado | Custo do trade-off | ADR |
|---|---|---|---|---|---|
| Organização do código | Monólito modular: `pipeline/`, `api/`, `web/` no mesmo repositório, implantados separados | Microsserviços; tudo num processo só | Fronteiras claras sem custo de rede e de operação | Disciplina para não importar entre pacotes (um teste confere) | 0019 |
| API | FastAPI + uvicorn, psycopg 3 com SQL parametrizado, sem ORM | Litestar; Django + DRF; Flask | Validação e OpenAPI de graça, assíncrona, leve; o contrato YAML continua sendo a fonte das tabelas | FastAPI não traz admin, CSRF nem sessão prontos: o BFF implementa o mínimo | 0020 |
| Identidade de servidor (fase 1) | Chave de API por organização (hash no banco) | OAuth client credentials | Simples, sem serviço externo, testável no Postgres local | Rotação manual pelo administrador | 0021 |
| Identidade de pessoas (fase 2) | Supabase Auth em São Paulo, pelo BFF, com cookie `httpOnly` | Clerk; Auth0; Keycloak ou Zitadel próprios; auth própria | Mesmo provedor e região do banco (#9); grátis até 50 mil usuários ativos; GoTrue é código aberto (dá para hospedar se sair) | Concentra banco e identidade num fornecedor; MFA por SMS é pago (usar TOTP) | 0021 |
| Front | SvelteKit compilado como site estático + MapLibre GL + mapas em PMTiles próprios | HTMX + Jinja servido pela API; React + Vite; Next.js | Pacote pequeno e rápido, sem servidor Node em produção (menos superfície); mapa sem enviar localização a terceiro | Ecossistema menor que React; lógica de tela no cliente pede cuidado com o que a API devolve | 0022 |
| Borda | Cloudflare gratuito: proxy, WAF gerenciado, 1 regra de limite, Turnstile | Cloudflare Pro; AWS WAF; Cloud Armor | DDoS sem limite e WAF sem custo; um degrau pago claro (Pro) | Tráfego processado fora do Brasil (transferência internacional, registrar) | 0023 |
| Banco | Postgres + PostGIS gerenciado em São Paulo (Supabase, #9) | Neon; RDS; VM própria | RLS e papéis já desenhados (migração 0004); dado pessoal fica no Brasil | Plano grátis pausa e não tem backup: produção exige Pro | 0017, 0025 |
| Hospedagem da API | Cloud Run (`southamerica-east1`) | Fly.io (`gru`); VM; Render | Escala a zero, cota grátis, contêiner, região no Brasil, deploy por OIDC sem chave | IAM do GCP tem curva; o domínio `run.app` precisa ser fechado para só aceitar a borda | 0024 |
| CI/CD | GitHub Actions com ambientes protegidos e OIDC | Cloud Build | Já é o CI do projeto | Minutos gratuitos limitados em repositório privado | 0024 |
| Segredos | Ambientes do GitHub + Secret Manager da nuvem | `.env` em servidor | Segredo por ambiente, auditado, sem arquivo na máquina | Mais um painel para cuidar | 0024 |
| Limite de requisições na API | Contador em memória; depois tabela no Postgres | Redis gerenciado | Zero peça nova até haver mais de uma instância | Contador em memória não é compartilhado entre instâncias | 0023 |

## Por que não Next.js (decisão de segurança)

O Next.js e os React Server Components põem um servidor JavaScript entre o navegador e os dados. É mais uma superfície a manter: em 2025 houve um desvio de autorização pelo middleware do Next.js ([CVE-2025-29927](https://nvd.nist.gov/vuln/detail/CVE-2025-29927)) e uma execução remota de código nos React Server Components ([CVE-2025-55182](https://nvd.nist.gov/vuln/detail/CVE-2025-55182)). Com o front estático e um único servidor (a API), há um só lugar para endurecer, monitorar e corrigir.

## Quando trocar

| Sinal medido | Próximo degrau |
|---|---|
| Conexões do banco perto do limite | Pooler do provedor (Supavisor) em modo transação; já é compatível com `SET LOCAL` |
| Latência da API alta com o banco folgado | Mais instâncias no Cloud Run; cache de resposta por organização e execução |
| Muitas regras de borda ou ataque recorrente | Cloudflare Pro |
| Tela muito interativa ficando lenta | Revisar o que a API devolve (paginação, campos) antes de trocar de framework |
| Mais de um produto com regras próprias | Novo router e novo esquema no mesmo monólito; serviço separado só se o ciclo de deploy divergir |
