# Usar o AB+S como referência sem declarar conformidade

## Context and Problem Statement

O projeto faz um pré-diagnóstico com fontes abertas e, com elas, verifica 2 dos 9 critérios do relatório de qualificação do AgroBrasil+Sustentável (AB+S) por inteiro e 1 em parte. O AB+S é a qualificação oficial do MAPA e tem uma API pública que confirma um relatório pelo código de autenticidade (UUID), sem login e sem documentação. Nos testes de 13/10/2026, a API não validou o formato do código e respondeu 500 a um código malformado em um dos endpoints. É preciso decidir que papel o resultado oficial tem no projeto e como o projeto fala de conformidade sem assumir uma responsabilidade que não é dele.

## Considered Options

* O projeto emite o próprio resultado de conformidade, sem consultar o AB+S
* O projeto consulta a API pública em massa para montar a situação da carteira
* O AB+S é a referência, consultado sob demanda pelo UUID que o produtor apresenta, e o projeto só aponta indícios

## Decision Outcome

Chosen option: "O AB+S é a referência, consultado sob demanda pelo UUID que o produtor apresenta, e o projeto só aponta indícios", because o projeto não tem fonte aberta para 6 dos 9 critérios e não pode afirmar o que não verificou. A consulta em massa foi rejeitada porque exigiria varredura de UUIDs numa API não documentada, e o resultado em lote só existe na API Serpro, que é paga e restrita a operadores financeiros.

Regras:

* O projeto usa só "pendência encontrada nas bases consultadas em [data]" e "nenhuma pendência encontrada nas bases consultadas em [data]". Critério sem fonte aberta aparece como "não verificado".
* O resultado do AB+S é citado, não reescrito: fonte, data da consulta, UUID e SHA-256 da resposta.
* O UUID vem do texto do PDF do relatório e tem o formato validado (36 caracteres, 8-4-4-4-12 hexadecimal) antes da consulta. Print e OCR não são aceitos.
* Uma consulta por relatório, com User-Agent identificado. 404 é "não localizado na consulta pública em [data]"; 500 é falha do serviço.
* Quando os dois resultados divergem, prevalece o oficial, e a divergência é classificada como falso positivo ou falso negativo do projeto.
* Documento de pessoa na resposta é pseudonimizado com HMAC (ADR 0002) antes de qualquer gravação fora de `data/`.

### Consequences

* Good, because a responsabilidade pela qualificação fica com quem a emite, e o projeto responde só por ter apontado onde olhar.
* Good, because cada relatório real comparado alimenta a matriz de concordância por critério, que mede a qualidade do pré-diagnóstico.
* Bad, because o canal depende de o produtor emitir e entregar o relatório; não serve para acompanhar a carteira.
* Bad, because a API não é documentada e pode mudar sem aviso; a estrutura de uma resposta válida ainda não é conhecida.
