# Construir o front estático com SvelteKit, sem segredo no navegador

Situação: **proposto em 05/11/2026, para lapidar** (fase 2 do roteiro).

## Context and Problem Statement

O técnico precisa de carteira, ficha, mapa e filtros, em computador e celular, às vezes com internet ruim. O front não pode vazar dado nem token, precisa ser barato de hospedar e não deve abrir mais um servidor para manter.

## Considered Options

* SvelteKit compilado como site estático (SPA) + a API como BFF
* HTMX + templates Jinja servidos pela própria API
* React + Vite (SPA)
* Next.js com React Server Components

## Decision Outcome

Chosen option: "SvelteKit estático", because gera pacotes pequenos e rápidos (bom para celular e internet ruim), é hospedado de graça na Cloudflare Pages e não põe um servidor Node em produção: o único servidor continua sendo a API.

| | SvelteKit estático | HTMX + Jinja | React + Vite | Next.js (RSC) |
|---|---|---|---|---|
| Peso no navegador | Pequeno | Mínimo | Médio | Médio a grande |
| Servidor a mais | Não | Não | Não | Sim (Node) |
| Mapa e filtros ricos | Bom | Trabalhoso | Bom | Bom |
| Ecossistema | Médio | Pequeno | Enorme | Enorme |
| Superfície de ataque | Pequena | Pequena | Pequena | Maior ([CVE-2025-29927](https://nvd.nist.gov/vuln/detail/CVE-2025-29927), [CVE-2025-55182](https://nvd.nist.gov/vuln/detail/CVE-2025-55182)) |

O HTMX fica como opção boa para telas administrativas simples, servidas pela própria API.

Regras do front:
* Nenhum segredo, token ou chave no pacote. Variável de ambiente pública só para a URL da API.
* CSP estrita: sem script inline, `connect-src` só a API, `frame-ancestors 'none'`; integridade (SRI) nos arquivos.
* Nenhum script de terceiro: sem analytics, sem fonte ou mapa servidos por terceiro. Mapa com MapLibre GL e tiles em PMTiles hospedados pelo projeto (R2), para a localização do imóvel não ir a um provedor de mapa.
* Nenhum dado pessoal em URL, título de página ou armazenamento do navegador.
* Os tipos da API são gerados do OpenAPI (ADR 0020), para o front não inventar campo.

### Consequences

* Good, because há um só servidor para endurecer e monitorar.
* Good, because hospedagem gratuita e cache global da Cloudflare.
* Bad, because a lógica de tela fica no cliente: tudo que a API devolve é visível ao usuário, então a API devolve só o que ele pode ver.
* Bad, because ecossistema menor que o do React; mitigado por usar poucas bibliotecas.
