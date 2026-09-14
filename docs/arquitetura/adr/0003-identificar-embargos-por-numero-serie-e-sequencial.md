# Identificar embargos pela combinação número, série e sequencial do termo

## Context and Problem Statement

A base do IBAMA não tem uma coluna que identifique cada registro de forma única. O número e a série do termo (`NUM_TAD` + `SER_TAD`) se repetem em registros com datas, áreas e coordenadas diferentes; o sequencial (`SEQ_TAD`) está ausente em parte dos registros; e os termos mais recentes, com número alfanumérico, não têm série. Sem um identificador estável, não há como detectar duplicidade nem acompanhar o mesmo embargo entre atualizações da base.

## Considered Options

* Usar só o sequencial `SEQ_TAD`
* Usar número + série do termo
* Criar um identificador a partir do hash da linha inteira
* Combinar número + série + sequencial

## Decision Outcome

Chosen option: "Combinar número + série + sequencial", because foi a única combinação sem nenhuma repetição na base completa, inclusive entre os registros sem sequencial. Usar só o sequencial deixaria registros sem identificador. Número + série sozinhos repetem. O hash da linha mudaria a cada alteração do registro na fonte, perdendo o acompanhamento ao longo do tempo.

O pipeline verifica a unicidade a cada execução e interrompe a fonte se ela deixar de valer.

### Consequences

* Good, because o identificador `id_embargo` é legível e fica estável quando a fonte altera outros campos do registro.
* Good, because uma mudança na forma como o IBAMA numera os termos é detectada na hora, pela validação `IBAMA_ID_DUPLICADO`.
* Bad, because depende de três colunas da fonte; se o IBAMA mudar o layout, o identificador precisa ser revisto.
