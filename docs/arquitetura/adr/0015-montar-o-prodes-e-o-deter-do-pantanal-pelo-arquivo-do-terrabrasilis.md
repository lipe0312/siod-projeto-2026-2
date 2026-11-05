# Montar o PRODES e o DETER do Pantanal pelo arquivo do TerraBrasilis

## Context and Problem Statement

Até 01/11/2026, o lote do PRODES era montado pelo WFS, UF por UF ([ADR 0013](0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md)). A primeira carga de uma UF levava horas: 7,9 h no PA e 5,1 h no MT. O tempo não vinha de falha de conexão, e sim do próprio serviço. O log da carga das 8 UFs registra 287 avisos: HTTP 502 do gateway, `ReadTimeout`, `ConnectionError` e `ChunkedEncodingError`. Cada um custa uma nova tentativa ou a divisão do retângulo em quatro. Por isso as 19 UFs restantes ficavam sem lote, e o primeiro imóvel de cada uma esperava horas.

Em 02/11/2026, o catálogo da área de download do TerraBrasilis (`/business/api/v1/download/all`) foi consultado. Ele lista um shapefile completo por bioma, `yearly_deforestation_biome_<bioma>_vAAAAMMDD.zip`, com a versão no nome. Os seis arquivos somam 2,6 GB e baixaram a 15–20 MB/s, cerca de 2 minutos no total.

| Teste em 02/11/2026 | Resultado |
|---|---|
| Polígonos por ano, 2019 a 2026, arquivo x contagem do WFS no Brasil (manifesto de 30/10/2026) | Idênticos nos 44 pares bioma x ano |
| As 8 UFs já no lote, arquivo x WFS, por `uuid` ([`01_comparacao.md`](../../evidencias/atividade-04/prodes-arquivo/01_comparacao.md)) | 637.415 polígonos nos dois; 14 só no WFS e 5 só no arquivo, todos na borda da UF; ano, data da imagem e UF 100% iguais |
| Precisão das coordenadas | O WFS devolve 4 casas decimais (~11 m); o arquivo, a precisão completa. Com o arredondamento, 64.328 polígonos do WFS viraram `GEOMETRYCOLLECTION` depois do `make_valid`, e a área difere mais de 10% em 24.227 |
| Codificação | O DBF da Amazônia e o do Cerrado estão em latin1 ("MARANHÃO"); os outros, em UTF-8. Lido em UTF-8, "MARANHÃO" vira sigla inválida em 300 mil polígonos |
| Lote completo das 27 UFs a partir dos arquivos | 245 s, pico de 4,8 GB de memória, 616 MB de Parquet |

O mesmo catálogo tem o DETER em arquivo (`/file-delivery/download/deter-<bioma>/shape`), atualizado todo dia. Ali aparece o **DETER do Pantanal**, que o WFS não publica. O projeto tratava o Pantanal como bioma sem DETER e avisava "sem cobertura desde 12/08/2025". No arquivo de 02/11/2026, o Pantanal tem 24.321 avisos desde 03/08/2023. Desses, 7.828 são de supressão ("supressão com solo exposto" e "supressão com vegetação"), com o último em 23/10/2026.

## Considered Options

* Manter o WFS e deixar a carga das 19 UFs rodando de madrugada
* Carregar só as UFs dos clientes previstos
* Montar o lote pelo arquivo de cada bioma e verificar a publicação pela versão do arquivo no catálogo

## Decision Outcome

Chosen option: "Montar o lote pelo arquivo de cada bioma", because cobre as 27 UFs em 4 minutos, com o mesmo conteúdo do WFS e geometria mais precisa. A verificação mensal custa uma requisição ao catálogo.

Regras (`inpe_prodes.executar_arquivos`, chamado por `python -m pipeline --fontes prodes`):
1. **Verificação:** a cada 30 dias, ou com `--verificar-prodes`, consulta o catálogo. Vale a versão mais nova de cada bioma; as variantes da Amazônia (não floresta, menores que 6,25 ha) ficam de fora, como no WFS do bioma. Bioma que sumiu do catálogo interrompe a fonte, e o lote anterior continua valendo.
2. **Só o bioma com versão nova** é baixado e tratado. Na partição de cada UF que ele toca, só as linhas desse bioma são trocadas; as dos outros biomas ficam como estavam. As peças bioma x UF são temporárias e não ficam em disco.
3. **O mesmo tratamento do WFS** (`inpe_prodes.tratar`): as validações de classe, uuid, geometria, data e área, e a UF pelo contorno do IBGE (o polígono de divisa entra nas duas UFs). Há três validações novas:
   * `PRODES_DBF_LATIN1`: correção;
   * `PRODES_ARQUIVO_INCOMPLETO`: DBF x SHX, erro;
   * `PRODES_FORA_DE_TODAS_AS_UFS`: descarte.
4. **Coordenadas com 6 casas decimais** (~0,1 m), abaixo do pixel de 30 m do Landsat.
5. **O WFS fica como alternativa** (`--prodes-pelo-wfs`) e para a consulta sob demanda do caderno da Atividade 03.
6. **DETER do Pantanal** pelo arquivo (`config.DETER_ARQUIVOS`):
   * as classes de supressão viram `DESMATAMENTO_CR` e `DESMATAMENTO_VEG`; queimada e mineração ficam fora, como na Amazônia e no Cerrado;
   * a UF vem do contorno do IBGE;
   * o município fica sem código (`DETER_MUNICIPIO_NAO_IDENTIFICADO`), porque o arquivo não traz;
   * o Pantanal deixa de gerar o aviso de "sem cobertura".

### Consequences

* Good, because as 27 UFs estão no lote. Nenhum imóvel espera horas: GO, MA e TO, fora do lote até 01/11/2026, saíram em cerca de 2 s cada.
* Good, because a geometria do PRODES deixa de ter o erro de ~11 m do WFS.
* Good, because o Pantanal passa a ter DETER. Em Corumbá (MS), a ficha mostra 12 alertas no imóvel, 4 confirmados pelo PRODES e 1 depois da última imagem, em vez do aviso de "sem cobertura".
* Good, because a verificação mensal deixa de depender da contagem do Brasil inteiro, que era a requisição mais pesada do WFS e a que mais recebia 502.
* Bad, because o arquivo bruto ocupa 2,6 GB, e o pico de memória da carga completa é de 4,8 GB. Numa máquina com 2 GB, a carga teria de ser feita bioma a bioma.
* Bad, because o endereço do catálogo e o nome dos arquivos não são uma API documentada. Se mudarem, a validação interrompe a fonte, e a saída é `--prodes-pelo-wfs`.
* Bad, because o Pantanal não tem DETER antes de 08/2023. Entre a data de corte (31/12/2020) e 08/2023, vale só o PRODES.
* Neutral, because Amazônia e Cerrado continuam no DETER pelo WFS, em partições mensais. O arquivo diário desses dois biomas é o candidato para o próximo passo.

## Adendo de 04/11/2026: DETER da Amazônia e do Cerrado pelo arquivo, reconciliado com o lago

O "próximo passo" acima foi feito (issue #4). `config.DETER_ARQUIVOS` passou a ter os três biomas, e o lote da Amazônia e do Cerrado vem do shapefile de `/file-delivery/download/deter-amz/shape` e `deter-cerrado-nb/shape` (HTTP 200, `application/zip`). O WFS em partições mensais ficou como **queda** e para a consulta sob demanda (`consultar_recorte`).

| Medido em 04/11/2026 | Amazônia | Cerrado |
|---|---|---|
| Tamanho do zip | 236.294.275 B (225 MB) | 47.776.983 B (45,6 MB) |
| Tempo de download | 11,7 a 16,9 s | 3,4 s (o servidor oscilou depois: leitura esgotada e falha de DNS) |
| Linhas no arquivo | 466.704 | 135.790 |
| Desmatamento desde 2021-01-01 | 150.215 | 89.927 |
| Contagem do WFS no mesmo período (até 23/10/2026) | 150.215 (diferença 0) | 89.927 (diferença 0) |
| Leitura e filtro do arquivo (sem rede) | 13,8 s | 6,5 s |
| Casados com o lago / novos / sem par no lago | 150.215 / 0 / 0 | 89.927 / 0 / 0 |
| Chaves ambíguas, todas resolvidas | 78 | 20 |

**O arquivo não é o WFS.** O `FID` do arquivo não é o `gid` do WFS (por exemplo, `100000_hist` x `2043041_hist` no Cerrado), e a geometria vem em `Polygon` com precisão total, sem o arredondamento de 4 casas do WFS. Ler o arquivo mudaria os ~240 mil `id_alerta` (ADR 0004: gid + hash do conteúdo), duplicaria os alertas no cruzamento e quebraria `diag.evidencia`. A decisão do dono foi **reconciliar com o lago antes de gravar** (`inpe_deter.reconciliar`):

1. **Par:** o alerta do arquivo que tem a mesma data da imagem, a mesma UF e a mesma área (arredondada a 6 casas, 1 m²) de um alerta vigente em `ref.alerta_deter` mantém o `id_alerta`, o `gid` e o mês de publicação do lago. O resto da linha (classe, geometria, código IBGE do município) vem do arquivo.
2. **Sem par:** o alerta é novo. `gid` = `arq-` + FID do arquivo e `id_alerta` pela fórmula de sempre. O prefixo não colide com o gid do WFS. Na execução seguinte ele casa com o lago, então o id é estável.
3. **Chave repetida** (mais de uma linha com a mesma data, UF e área, em um dos lados): resolvida um para um, nesta ordem: mesmo município (código ou nome), menor distância entre os centroides, menor gid do arquivo, menor `id_alerta` do lago. Cada caso entra em `DETER_<BIOMA>_AMBIGUO` (e `_AMBIGUO_SEM_PAR` se sobrar linha sem par). Nada é silencioso.
4. **Queda:** se o download, a leitura ou a validação do arquivo falhar, o bioma vem do WFS nessa execução, com o motivo em `entrada.quedas_para_wfs` e na validação `DETER_<BIOMA>_ARQUIVO_FALHOU`. As linhas do WFS passam pela mesma reconciliação, mas só contra alerta do lago que nasceu do arquivo (gid com `arq-`), para não duplicar. Nunca se grava "sem ocorrência" por falta de dado. O Pantanal não tem WFS, então a falha dele continua interrompendo a fonte.
5. **Download só quando muda:** o servidor não manda `Last-Modified`, `Content-Length` nem `ETag`; só o nome em `Content-Disposition`, que leva a data (`deter-amz-public-2026nov04.zip`). Um HEAD compara esse nome com o gravado no `.meta.json`; igual, não baixa. Diferente, baixa e compara o SHA-256 com o anterior (`mudou`).
6. **Leitura filtrada:** classe fora do desmatamento (queimada, degradação, mineração, corte seletivo: 183.275 linhas na Amazônia) e data anterior a `DETER_DESDE_PADRAO` (133.214) são contadas e ignoradas antes de montar a geometria, sem ir para `meta.descarte`.
7. **Validação arquivo x WFS e arquivo x lago** no mesmo período: `DETER_<BIOMA>_ARQUIVO_X_WFS` (uma requisição `resultType=hits`; WFS fora do ar vira `_INCONCLUSIVA`, sem derrubar a fonte), `_ARQUIVO_X_LAGO`, `_RECONCILIADO`, `_NOVO`, `_SO_NO_LAGO` e `_MUNICIPIO_DIFERENTE_NO_PAR`.

Numa execução de teste com cópia do lago (pico de memória de 2,2 a 2,4 GB), o arquivo falhou em cada bioma uma vez (leitura esgotada, conexão interrompida e falha de DNS, logo depois que o servidor regerou o arquivo do dia). O bioma caiu para o WFS com o motivo registrado, sem duplicar alerta; o arquivo do outro bioma foi reconciliado normalmente. Ao voltar ao WFS, as linhas casadas voltam à geometria de 4 casas, e a próxima leitura do arquivo as atualiza de novo.

Consequências:
* Good, because o lote da Amazônia e do Cerrado deixa de depender do WFS (horas e erros 502) e a geometria nova tem precisão total.
* Good, because os ids existentes se mantêm: nada se duplica e `diag.evidencia` continua válido.
* Bad, because na primeira carga todas as linhas casadas aparecem como "alteradas" no histórico (geometria de precisão total, `Polygon` em vez de `MultiPolygon`).
* Bad, because o par por data, UF e área é uma heurística; os casos em que o município diferia ou a chave se repetia ficam contados nas validações acima.
* Neutral, because `mes_publicacao` fica nulo nos alertas novos do arquivo (ele não traz `publish_month`); nenhum código o usa.
* Neutral, because o Pantanal também passou a ser baixado de novo quando a versão do arquivo muda (antes, só com `--atualizar`).
