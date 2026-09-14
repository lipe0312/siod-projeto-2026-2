# Coletar alertas DETER de desmatamento em partições mensais e identificar cada alerta pelo conteúdo

## Context and Problem Statement

O DETER tem centenas de milhares de alertas, de várias classes, servidos por uma API WFS que devolve GeoJSON. Para o projeto importa o desmatamento com imagem posterior a 31/12/2020, com geometria.

A primeira implementação pedia os alertas em páginas de 2.000, ordenadas por `gid`, e tratava o `gid` como identificador. A execução completa mostrou que o `gid` não é único:
- **Cerrado:** o mesmo `gid` aparece para trechos de um mesmo alerta em municípios vizinhos.
- **Amazônia:** 39.890 `gid` são reutilizados por alertas de datas diferentes, com distância mediana de cerca de 1.100 km entre eles.

Com uma ordenação não única, a paginação por deslocamento repetiu registros na fronteira das páginas, o que também implica registros não recebidos. E o descarte por `gid` + município apagou alertas reais.

## Considered Options

* Paginação por deslocamento ordenada por `gid`, descartando `gid` repetido no mesmo município
* Coletar só a contagem de alertas por município, sem geometria
* Uma requisição completa por mês de imagem, com identificador calculado a partir do conteúdo do alerta

## Decision Outcome

Chosen option: "Uma requisição completa por mês de imagem, com identificador calculado a partir do conteúdo do alerta", because é a única das três que recebe cada alerta exatamente uma vez sem depender de uma chave única que a fonte não tem. O maior mês observado tem menos de 9 mil alertas, e o serviço devolve o mês inteiro numa requisição. Na execução de referência, os 233.777 alertas anunciados foram recebidos em 138 requisições, sem nenhuma duplicata.

O pipeline confere, em cada resposta, se o número de features recebidas é igual ao anunciado pelo serviço (`DETER_PARTICAO_INCOMPLETA`). Também compara a soma dos meses com o total anunciado no início da coleta.

O identificador é camada + `gid` + hash de (gid, data, município, geometria). Só é descartada como duplicata a feature idêntica nesses quatro campos. A contagem sem geometria foi rejeitada porque o cruzamento com a área de produção precisa dela. As demais classes (degradação, corte seletivo, queimada, mineração) ficam fora por não indicarem conversão para uso agropecuário.

### Consequences

* Good, because nenhum alerta é repetido ou perdido por instabilidade de paginação, e a completude de cada mês é verificada.
* Good, because cada resposta fica gravada compactada, com hash, e a transformação pode ser refeita sem nova coleta.
* Bad, because um mês com mais alertas do que o limite do serviço interrompe a coleta e exigirá partições menores.
* Bad, because o identificador muda se a fonte alterar a geometria de um alerta já publicado.
