# Marcar registros inválidos e descartar só o que não pode ser vinculado nem localizado

## Context and Problem Statement

A caracterização dos dados encontrou vários tipos de problema na base do IBAMA: coordenadas em (0, 0), datas no futuro, documentos com dígito verificador errado, áreas zeradas e polígonos inválidos. Na maior parte dos casos, só um campo do registro está errado; o embargo em si continua existindo. O pipeline precisava decidir o que fazer com esses registros.

## Considered Options

* Remover todo registro com qualquer campo inválido
* Corrigir automaticamente os valores inválidos (por exemplo, inferir a data ou reparar o polígono)
* Anular o campo inválido, marcar o registro com um código de alerta e descartar apenas o que não tem nenhum uso

## Decision Outcome

Chosen option: "Anular o campo inválido, marcar o registro com um código de alerta e descartar apenas o que não tem nenhum uso", because um campo errado não invalida o embargo e a decisão de usar ou não o registro pertence à regra de cruzamento, que ainda será construída. A correção automática foi rejeitada porque exigiria adivinhar o valor correto (a data 25/09/2925 pode ser 2025 ou outro erro qualquer).

Na base do IBAMA, é descartado só o registro sem documento válido, sem geometria e sem coordenada válida, porque não pode ser associado a nenhum produtor nem a nenhuma área. As únicas correções automáticas são as determinísticas, como a normalização da grafia do bioma.

### Consequences

* Good, because nenhum embargo real é perdido por causa de um campo com problema.
* Good, because cada registro carrega na coluna `alertas` o motivo das suas limitações, e o relatório de execução conta cada caso.
* Bad, because as etapas seguintes precisam considerar a coluna `alertas` e os campos anulados, em vez de receber só dados "limpos".
