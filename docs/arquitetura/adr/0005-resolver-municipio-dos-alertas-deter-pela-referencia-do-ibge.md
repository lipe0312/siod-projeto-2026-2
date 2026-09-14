# Resolver o município dos alertas DETER pela referência do IBGE

## Context and Problem Statement

A junção entre embargos do IBAMA e alertas do DETER usa o código IBGE do município. A camada Amazônia do DETER traz esse código, mas a camada Cerrado traz só o nome, em maiúsculas e com acento, enquanto a camada Amazônia escreve os nomes sem acento. Alguns nomes usam grafias antigas que não batem com o nome oficial.

## Considered Options

* Juntar as bases pelo nome do município, como veio de cada fonte
* Obter o código por cruzamento espacial da geometria do alerta com a malha municipal
* Obter o código a partir de nome normalizado + UF, usando a lista oficial de municípios da API do IBGE e uma tabela explícita de apelidos

## Decision Outcome

Chosen option: "Obter o código a partir de nome normalizado + UF, usando a lista oficial de municípios da API do IBGE e uma tabela explícita de apelidos", because o nome normalizado + UF identificou o município de todos os 233.777 alertas da execução de referência, com uma dependência leve (um JSON) e quatro apelidos para nomes antigos, aplicados a 90 alertas. O cruzamento espacial exigiria baixar e processar a malha municipal inteira nesta etapa.

Juntar pelo nome bruto falharia por diferenças de acento e caixa. Na camada Amazônia, o código vindo da fonte é mantido e comparado com o código obtido pelo nome (`DETER_MUNICIPIO_CODIGO_DIVERGENTE`). A mesma referência também valida os códigos de município da base do IBAMA.

### Consequences

* Good, because as três bases passam a usar o mesmo código e o mesmo nome oficial de município.
* Good, because a tabela de apelidos fica no código (`pipeline/municipios.py`) e cada nome não resolvido aparece no relatório.
* Bad, because nomes novos com grafia diferente exigem incluir apelidos manualmente, e o nome do município não confirma a posição da geometria.
