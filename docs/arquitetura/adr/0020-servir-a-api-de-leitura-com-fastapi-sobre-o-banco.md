# Servir a API de leitura com FastAPI sobre o banco

Situação: **decidido em 05/11/2026** quanto à dependência (o dono aprovou `fastapi` e `uvicorn`); o desenho das rotas segue para lapidar na #10.

## Context and Problem Statement

A #10 precisa expor a carteira, a ficha e as mudanças por organização, lendo do banco, com isolamento por RLS e sem devolver documento. O projeto é Python, os contratos YAML já geram o banco e não há servidor web hoje.

## Considered Options

* FastAPI + uvicorn
* Litestar
* Django + Django REST Framework
* Flask

## Decision Outcome

Chosen option: "FastAPI + uvicorn", because valida entrada e saída com modelos tipados, gera a especificação OpenAPI sozinha (que vira o contrato com o front) e é leve. Django traz admin, sessão e CSRF prontos, mas o ORM duplicaria os contratos YAML e o framework pesa mais do que uma API de leitura precisa. Litestar é equivalente tecnicamente, com comunidade menor.

Regras:
* Acesso ao banco com psycopg 3 e SQL parametrizado, sem ORM. O pool de conexões (`psycopg_pool`) é dependência nova e passa pelo dono quando for preciso.
* Cada requisição: uma transação, `SET LOCAL ROLE agrovalid_leitura`, `SET LOCAL app.organizacao_id` (nunca `SET` de sessão, que vaza no pool).
* A organização vem só da credencial validada no servidor, nunca de parâmetro do cliente.
* Modelos de resposta explícitos: `documento_hash` e qualquer documento não existem neles. Um teste varre todas as respostas.
* Rotas versionadas em `/v1`; `/saude` testa o banco; erro do banco vira 503 sem dado parcial; erro inesperado vira 500 genérico com `request_id`.
* Documentação interativa (`/docs`) desligada fora do ambiente local.
* Toda resposta leva `execucao_id`, `carga_id` e a data de cada fonte.

### Consequences

* Good, because o contrato da API (OpenAPI) fica versionado e testável, como os contratos das tabelas.
* Good, because o mesmo processo serve depois de BFF para o front (ADR 0021), sem mais um servidor.
* Bad, because sessão, CSRF e limite de requisições precisam ser implementados com cuidado, sem a rede de segurança de um framework completo.
