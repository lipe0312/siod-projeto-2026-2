# Tratar a LGPD por desenho, com dado pessoal no Brasil

Situação: **proposto em 05/11/2026, para lapidar; revisão jurídica pendente**. Módulo completo em [`docs/lgpd/`](../../lgpd/README.md).

## Context and Problem Statement

A AgroValid trata CPF e CNPJ de produtores (pseudonimizados, ADR 0002), cadastro de cooperativas, resultado de pré-diagnóstico que pode afetar crédito e venda, e dados públicos com nomes de pessoas (Lista Suja, embargos). Com API e front, entram contas de usuários e terceiros (provedor de identidade, borda, nuvem). A conformidade precisa estar no desenho, não num texto no fim.

## Considered Options

* LGPD por desenho: papéis definidos, dado pessoal hospedado no Brasil, minimização, inventário mantido junto com o código
* Conformidade só documental (política e termos), sem mudar a arquitetura
* Anonimizar tudo e não tratar dado pessoal

## Decision Outcome

Chosen option: "LGPD por desenho", because o produto precisa ligar o resultado ao produtor, então anonimizar tudo inviabiliza o serviço; e só documento não protege nada.

Regras:
* Papéis: a cooperativa é **controladora** dos dados dos produtores dela; a AgroValid é **operadora** desses dados e **controladora** das contas de usuário e do tratamento de dados públicos.
* Dado pessoal de cliente (`cad`, `diag`, contas) fica em São Paulo. A borda (Cloudflare) é transferência internacional, com cláusulas-padrão (Resolução CD/ANPD nº 19/2024) e registro no inventário.
* CPF e CNPJ nunca em claro (ADR 0002). Pseudonimizado continua sendo dado pessoal para quem tem a chave: a chave do HMAC é segredo de produção.
* O sistema nunca decide sozinho: a ficha mostra fonte, data e o que não foi verificado, e o técnico decide (art. 20).
* Inventário de tratamentos, bases legais e prazos de retenção mantidos em `docs/lgpd/`, atualizados por toda issue que trate dado pessoal novo (checklist de issue).
* Antes do piloto: contrato de operador com a cooperativa, política de privacidade, termos de uso, canal do titular, encarregado indicado, RIPD e plano de incidente (comunicação em 3 dias úteis, Resolução CD/ANPD nº 15/2024).

### Consequences

* Good, because a resposta a "onde está e por que tratamos esse dado" sai do repositório, não da memória.
* Good, because o desenho (RLS, papéis, residência no Brasil) é a prova de confiabilidade para a cooperativa.
* Bad, because cada fornecedor novo exige análise de transferência e contrato.
* Bad, because os textos precisam de revisão jurídica antes de valer.
