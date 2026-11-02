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
