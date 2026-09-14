# Pseudonimizar CPF/CNPJ com HMAC-SHA256 dentro do pipeline

## Context and Problem Statement

A base do IBAMA e a Lista Suja trazem CPF, CNPJ e nomes. O sistema precisa cruzar essas bases pelo documento do produtor, mas os dados pessoais não devem circular pelas camadas seguintes (persistência, API, logs). O espaço de CPFs é pequeno, cerca de 10⁹ combinações válidas, então um hash simples pode ser revertido por força bruta.

## Considered Options

* Manter o documento original e proteger só o acesso às camadas seguintes
* Substituir o documento por SHA-256 simples
* Substituir o documento por HMAC-SHA256 com uma chave secreta fora do repositório

## Decision Outcome

Chosen option: "Substituir o documento por HMAC-SHA256 com uma chave secreta fora do repositório", because mantém o cruzamento entre bases (o mesmo documento gera o mesmo código) e, sem a chave, não é possível recalcular os códigos a partir de uma lista de CPFs. O SHA-256 simples foi rejeitado por ser reversível por força bruta.

A chave é lida da variável `SIOD_CHAVE_PSEUDONIMIZACAO`. Se ela não existir, é criada uma vez em `data/chave_pseudonimizacao`, pasta que não é versionada. O nome do empregador e o documento original são removidos da saída.

### Consequences

* Good, because nenhuma saída do pipeline contém CPF, CNPJ ou nome de pessoa.
* Good, because o documento que o produtor informar no futuro poderá ser cruzado aplicando a mesma função com a mesma chave.
* Bad, because a chave passa a ser um segredo operacional: se for perdida, os códigos gerados deixam de corresponder aos novos.
