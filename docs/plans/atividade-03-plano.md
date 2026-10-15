# Plano — Atividade 3

## 1. Objetivo

Fechar as três lacunas que impedem o cruzamento real do projeto:

1. **Não ter o CAR.** Sem o polígono e a situação do CAR, nenhum embargo, alerta ou lista consegue ser atribuído a um imóvel. É o maior problema, mais do que a falta de download em massa.
2. **Não ter a resposta oficial do AB+S.** O código de autenticidade (UUID) do relatório é a ponte para usar o AB+S como referência, mas ainda não se conhece o conteúdo de uma resposta válida.
3. **Não cobrir os biomas do recorte.** O recorte do projeto é **café em Minas Gerais** (Mata Atlântica e Cerrado), e o DETER não cobre a Mata Atlântica.

Também atende ao que foi pedido na avaliação da Atividade 2: mostrar dado real, comprovar com evidência que o AB+S não entrega diagnóstico e aprofundar o cruzamento com o AB+S. A parte de montagem (visualização do que já existe e slides) fica para o fim (seção 9).

## 2. Princípios

- **Fonte aberta e gratuita primeiro.** Tudo que entra no projeto agora pode ser acessado sem contrato e sem pagamento. Fontes pagas ou contratadas ficam registradas como **fontes de produção**: seriam as principais se o projeto fosse ao ar, mas não são usadas agora (seção 7).
- **O projeto não declara conformidade.** Ele aponta indícios com fonte e data. Quando existe resultado oficial do AB+S, ele é a referência e é citado, nunca reescrito.
- **Toda conclusão tem evidência conferível.** Cada afirmação deste plano e dos documentos que ele gera aponta para o módulo que o gera em `pipeline/` e para a seção do caderno `notebooks/02_fontes_antes_e_depois.ipynb` que o reproduz, ou é marcada como resultado do estudo exploratório de 13/10/2026.
- **Toda saída é visual.** Cada frente termina com tabela, mapa ou gráfico, não só com texto.
- **Sem pular etapas da disciplina.** Pesquisa e testes exploratórios podem andar livres; a integração no pipeline segue o cronograma (persistência na Aula 04, ML na Aula 09, LLM na Aula 10).

## 3. Organização das saídas

Documentação, código e dados ficam separados. `docs/` tem só texto e figuras: é a base de estudo e dos slides. Os estudos exploratórios de 13/10/2026 viraram módulos do pipeline no padrão da Atividade 02 e um caderno de visualização. SICAR, PRODES e AB+S são **fontes sob demanda**: consulta-se só a área ou o relatório do caso, e não há carga em massa. Cada consulta devolve o DataFrame tratado e o `ResultadoFonte`, e grava a resposta bruta em `data/raw/<fonte>/` com um `.meta.json`.

```
docs/
├── atividade-01-dados.md
├── atividade-02-pipeline.md
├── atividade-03-investigacao.md         conclusões da atividade e índice
├── atividade-03/                        DOCUMENTAÇÃO (base de estudo e slides)
│   ├── car.md                           frente A
│   ├── ab-s-validacao-cruzada.md        frente B
│   ├── prodes-e-escada-de-fontes.md     frente C
│   └── figuras/                         PNG dos estudos (mapas, gráficos, prints)
├── evidencias/atividade-02/             execução de referência da Atividade 02 (já entregue)
├── arquitetura/
│   ├── arquitetura.md                   atualizada com as fontes sob demanda
│   └── adr/                             0007, 0008 e 0009 novos
├── inconsistencias-dos-dados.md         atualizado com SICAR, PRODES e AB+S
└── plans/
    └── atividade-03-plano.md            este plano

notebooks/02_fontes_antes_e_depois.ipynb VISUALIZAÇÃO: cada fonte antes e depois do tratamento, executado e salvo

pipeline/                                CÓDIGO
├── wfs.py                               requisição, contagem e filtros WFS (DETER, PRODES, SICAR)
├── cruzamento.py                        atribuição embargo/alerta → CAR (frente A)
└── fontes/
    ├── sicar.py                         frente A, sob demanda
    ├── ab_s.py                          frente B, sob demanda
    └── inpe_prodes.py                   frente C, sob demanda

tests/test_{sicar,ab_s,inpe_prodes,cruzamento}.py

data/                                    DADOS (fora do Git)
└── raw/{sicar,ab_s,inpe_prodes}/        respostas como vieram da fonte, com .meta.json (cache das consultas)
```

Regras:

- Cada fonte sob demanda segue o contrato das fontes em lote: transformação explícita, validações registradas com `resultado.validar(...)` e testes com dados pequenos escritos no próprio teste.
- As fontes sob demanda não entram em `python -m pipeline` nem no relatório de execução da Atividade 02.
- Resposta de API é guardada como veio, com data da consulta e SHA-256 em um `.meta.json`, no mesmo padrão de `pipeline/download.py`.
- Nenhum CPF, CNPJ ou nome de pessoa vai para as saídas. Dados pessoais são pseudonimizados com `pipeline/documentos.py::pseudonimizar`.

## 4. Panorama das fontes abertas (testado em 13/10/2026)

| Fonte | O que entrega | Acesso | Teste | Situação |
|---|---|---|---|---|
| **SICAR, WFS público** (`geoserver.car.gov.br/geoserver/sicar/wfs`) | Polígono, código, status e condição do CAR, município IBGE, área, módulos fiscais. **Sem CPF.** Uma camada por UF | Livre, sem login | Busca por código, por ponto, por município e por polígono funcionaram | **Fonte nova principal** |
| **AB+S, API pública de validação** (`agrobrasil.agricultura.gov.br/abs/backend/api/public/...`) | Resultado oficial de um relatório já emitido, pelo UUID | Livre, sem login, sem documentação | Os 3 endpoints respondem JSON; só testados com UUID inexistente | Falta um UUID real |
| **PRODES por bioma, WFS** (TerraBrasilis, `prodes-{bioma}-nb`) | Polígonos de supressão anual, com data da imagem e ano de publicação | Livre | Mata Atlântica de 2021 a 2025 respondeu | **Fonte nova** |
| **FUNAI, WFS** (`geoserver.funai.gov.br`) | Terras indígenas (polígonos) | Livre | Camadas listadas | Fora deste plano; registrada para o critério de sobreposição |
| DETER, IBAMA, Lista Suja, IBGE | Já no pipeline | Livre | — | Mantidas |

## 5. Frente A — Obter o CAR (prioridade 1)

### O que já se sabe

O SICAR publica um **WFS aberto** com uma camada por UF (`sicar:sicar_imoveis_{uf}`, 27 camadas). Campos: `cod_imovel`, `status_imovel`, `dat_criacao`, `data_atualizacao`, `area`, `condicao`, `uf`, `municipio`, `cod_municipio_ibge`, `m_fiscal`, `tipo_imovel` e a geometria `geo_area_imovel` (MultiPolygon, SIRGAS 2000, EPSG:4674, o mesmo sistema do DETER). Não publica CPF nem nome, então não há dado pessoal na coleta.

Resultados dos testes:

| Teste | Resultado |
|---|---|
| Busca pelo código do CAR que aparece no relatório AB+S de Capixaba/AC | Encontrado em 0,26 s: status `AT`, condição "Aguardando análise" |
| Busca pelo código do relatório AB+S de Niquelândia/GO | Encontrado em 0,26 s |
| Busca por município (Capixaba/AC) | 1.973 imóveis |
| Busca por ponto | Funciona com a ordem **latitude, longitude**. Na ordem longitude, latitude devolve zero sem erro |
| Município cafeeiro inteiro de MG | Patrocínio: 5.962 imóveis, 13,8 MB, 3,8 s · Três Pontas: 2.449, 4,4 MB, 1,0 s · Manhuaçu: 4.370, 6,5 MB, 2,1 s. Em todos, anunciado = recebido |
| Volume por UF | AC 62.868 · MT 220.256 · MG 1.180.594 |
| Status no AC | `AT` 49.787 · `PE` 7.409 · `CA` 5.640 · `SU` 32 |
| Condição (amostra de 3.000 no AC) | "Aguardando análise", "Em análise", "Analisado, aguardando atendimento a notificação", "Analisado, aguardando regularização ambiental", "Analisado, em regularização ambiental", "Analisado, em conformidade com a Lei nº 12.651/2012", "Cancelado por decisão administrativa" |
| **30 embargos IBAMA reais do AC, posteriores a 2020, cruzados pelo polígono** | **29 caem sobre pelo menos um CAR**, 1 não cai sobre nenhum. A maioria toca de 3 a 4 CARs (mediana 3, máximo 19). 0,09 s por consulta |

Três achados mudam o desenho:

1. **O CAR não é um por embargo.** Um embargo toca vários CARs: vizinhos que encostam na borda e cadastros autodeclarados sobrepostos. Atribuir o embargo a todos eles gera **falso positivo**. É preciso uma regra de atribuição pela área de interseção.
2. **A área diverge entre fontes.** No relatório AB+S de Capixaba a área do estabelecimento é 58,6 ha; no SICAR, o mesmo CAR tem 2.736,7 ha. Em Niquelândia, 329,2 ha contra 199,6 ha. A hipótese é que o AB+S use a área do cadastro fundiário (SNCR/INCRA), não a do CAR. Precisa ser confirmada antes de qualquer conclusão.
3. **O servidor exige TLS antigo.** O `requests` do Python falha no *handshake* (`SSLV3_ALERT_HANDSHAKE_FAILURE`); o `curl` funciona. O certificado é válido (Sectigo). A correção é um contexto TLS com `set_ciphers("DEFAULT:@SECLEVEL=1")` e `OP_LEGACY_SERVER_CONNECT`, **mantendo a verificação do certificado ligada**. Nunca usar `verify=False`.

### Como chegar ao CAR do produtor (escada, da mais rápida à mais lenta)

| Degrau | O técnico tem | Como obter o CAR | Confiança |
|---|---|---|---|
| 1 | O código do CAR ou o recibo de inscrição | WFS por `cod_imovel` | Alta: correspondência exata |
| 2 | Um ponto (sede, coordenada do GPS) ou o desenho da área | WFS com `INTERSECTS`; candidatos ordenados pela área de interseção | Média: o técnico confirma o candidato |
| 3 | Um relatório AB+S | UUID → API pública → CAR, se a resposta trouxer o código (ver frente B) | Alta, quando funcionar |
| 4 | Só o CPF/CNPJ | Não há caminho aberto: o SICAR não publica documento (LGPD). Pede-se o recibo do CAR ao produtor, que sempre o tem. Mais lento, mas viável e gratuito | Alta, depois de obtido |
| 5 | Nenhum CAR encontrado no local | **Isso já é um resultado**: CAR inexistente veda o crédito rural (MCR, Seção 2-9) | Sinalizar como "sem CAR localizado", nunca como "sem CAR" sem confirmação |

O mesmo cruzamento vale no sentido inverso, sem o técnico: cada embargo IBAMA e cada alerta de desmatamento é atribuído aos CARs que ele atinge.

### Tarefas

| # | Tarefa | Saída | Pronto quando |
|---|---|---|---|
| A1 | Script que baixa o CAR de um conjunto de municípios cafeeiros de MG, um município por requisição, conferindo `numberMatched` contra o recebido (mesmo padrão da partição mensal do DETER, ADR 0004) | `sicar.consultar_municipios`; caderno, seção 5 | Todos os municípios com anunciado = recebido |
| A2 | Estudo de inconsistências do CAR: códigos repetidos, geometria inválida, área zero, status e condição, sobreposição entre CARs do mesmo município | Validações `CAR_*` em `sicar.transformar`; atualização de `inconsistencias-dos-dados.md` | Cada problema com contagem e tratamento proposto |
| A3 | Regra de atribuição embargo/alerta → CAR: fração do embargo dentro de cada CAR e fração do CAR atingida. Classificar em **principal**, **parcial** e **tangente** (limiares definidos pelos dados, não arbitrados) | `cruzamento.atribuir_car` + histograma das frações + mapa de casos reais (caderno, seção 8) | Limiares justificados por um gráfico; casos tangentes separados |
| A4 | Confirmar o significado de `AT`, `PE`, `SU` e `CA` e das condições na documentação do Serviço Florestal Brasileiro | Tabela de códigos com fonte | Cada código com fonte oficial, ou marcado como "inferido" |
| A5 | Investigar a divergência de área AB+S × SICAR | Nota em `car.md` | Origem da área do AB+S identificada ou declarada como pendência |
| A6 | Decisão em ADR: SICAR WFS como fonte do CAR, escada de obtenção, regra de atribuição e o ajuste de TLS | `adr/0007-obter-o-car-pelo-wfs-publico-do-sicar.md` | ADR no formato MADR, como os anteriores |

### Visualização desta frente

- Mapa de um município com os CARs, os embargos e os casos principal/parcial/tangente em cores diferentes.
- Gráfico de barras de status e condição do CAR nos municípios do recorte.
- Tabela da escada de obtenção (acima), com o tempo medido de cada degrau.

## 6. Frente B — AB+S pelo UUID como referência (prioridade 2)

### O que já se sabe

Existem **dois canais** e eles não podem ser confundidos:

| Canal | Para quê | Acesso | Uso no projeto |
|---|---|---|---|
| **API pública de validação por UUID** | Confirmar um relatório que o produtor já emitiu | Livre, sem login, sem documentação oficial | **Usado agora** |
| API Serpro "Consulta Práticas Agropecuárias Sustentáveis" | Consultar a qualificação por CAR + CPF/CNPJ, em lote | Contrato comercial; restrita a operadores financeiros autorizados pelo Banco Central | Fonte de produção (seção 7) |

Teste da API pública em 13/10/2026, com UUID inexistente e com o UUID que aparece no relatório de demonstração:

| Endpoint | Resposta | O que revela |
|---|---|---|
| `GET /abs/backend/api/public/qualificacao/{uuid}` | 404, JSON: "Não foi encontrado nenhum registro na entidade Validacao" | Qualificação socioambiental |
| `GET /abs/backend/api/public/habilitacao/{uuid}` | 404, JSON, cita a entidade `ValidacaoPlanoSafra` e o campo `COD_AUTENTICACAO` | Habilitação para o Plano Safra |
| `GET /abs/backend/api/public/area-producao/{uuid}` | 404, JSON: "Não foi encontrada área de produção" | Área de produção (EUDR) |

O UUID do relatório de demonstração (`57e267ec-...`) também deu 404. O próprio relatório indica ambiente de teste ("TESTE VARIOS PROPRIETARIOS 999"). **Ainda não existe uma resposta válida**, e esse é o bloqueio desta frente.

O relatório em PDF tem o código de autenticidade **em texto** ("Código de autenticidade: ..."), além do QR. Então o UUID pode ser extraído com `pdfplumber`, que já está no projeto; a leitura do QR é um caminho alternativo.

### Como conseguir um UUID real sem pagar

| Opção | Como | Observação |
|---|---|---|
| Produtor voluntário | Pedir um relatório AB+S já emitido, pela rede da cooperativa, da Emater ou do orientador | Exige consentimento por escrito. O UUID dá acesso ao resultado do produtor |
| Relatório publicado | Procurar relatórios que cooperativas ou produtores divulgaram publicamente | O UUID é público por desenho, mas confirmar que a divulgação foi do próprio titular |
| Conta gov.br própria | Só funciona se houver imóvel vinculado ao CPF no SNCR | Provavelmente não se aplica |

### Validação cruzada e falsos positivos/negativos

Quando existe resultado do AB+S para um imóvel, ele é a **referência** e o pré-diagnóstico do projeto é comparado critério a critério:

| Projeto | AB+S | Classificação | Consequência |
|---|---|---|---|
| Pendência | Não conforme | Concordância | Projeto acrescenta causa e caminho de regularização |
| Sem pendência | Conforme | Concordância | — |
| Pendência | Conforme | **Falso positivo** do projeto | Mostrar o oficial em destaque; revisar a regra (ex.: embargo tangente da frente A) |
| Sem pendência | Não conforme | **Falso negativo** do projeto | Mais grave. Indica critério sem fonte aberta ou fonte desatualizada |
| Não verificado | Qualquer | Fora de cobertura | Declarado no relatório; nunca exibido como "sem pendência" |

Cada critério do AB+S é mapeado para o critério equivalente do projeto, usando a taxonomia interna já levantada (`VERIFICACAO_EMBARGOS_IBAMA`, `VERIFICACAO_SOBREPOSICAO_PRODES`, `VERIFICACAO_TRABALHO_ESCRAVO`, `VERIFICACAO_CAR` etc.). Com uma amostra de imóveis com resposta oficial, isso vira uma **matriz de confusão por critério**: é a métrica de qualidade do pré-diagnóstico.

### Blindagem jurídica

- O projeto **nunca** afirma conformidade. Usa "pendência encontrada nas bases consultadas em [data]" e "nenhuma pendência encontrada nas bases consultadas em [data]".
- O resultado do AB+S aparece **citado**: fonte, data da consulta, UUID e SHA-256 da resposta. Não é reescrito como conclusão do projeto.
- Consulta à API pública **só sob demanda**, uma por relatório, com User-Agent identificado. Sem varredura de UUIDs. A API não é documentada e pode mudar.
- Guardar só o necessário da resposta. Documento de pessoa é pseudonimizado.
- Texto fixo no relatório do projeto: o que ele é (pré-diagnóstico com fonte), o que não é (atestado, certificação, parecer jurídico) e quem é a referência oficial (AB+S/MAPA).

### Tarefas

| # | Tarefa | Saída | Pronto quando |
|---|---|---|---|
| B1 | Repetir os testes da API pública e guardar as respostas brutas | `ab_s.consultar` + resposta bruta em `data/raw/ab_s/` | Respostas de 404 guardadas com data e hash |
| B2 | Extrair o UUID do PDF (texto via `pdfplumber`; QR como alternativa) e validar o formato de 36 caracteres | `ab_s.extrair_uuid` e `ab_s.validar_uuid` | Extração funcionando no PDF disponível |
| B3 | **Conseguir um UUID real** (ação do autor, não automatizável) e guardar a resposta válida | Resposta pseudonimizada em `data/raw/ab_s/` | Uma resposta 200 com estrutura documentada campo a campo |
| B4 | Mapear critério AB+S → critério do projeto | Tabela em `ab-s-validacao-cruzada.md` | Todos os critérios do relatório mapeados, inclusive os "não verificados" |
| B5 | Viabilidade para o técnico: o que ele precisa (carteira inteira, periódica) × o que o canal público oferece (um relatório por vez, depende do produtor emitir) × lacuna | Tabela | Conclusão explícita sobre o uso em carteira |
| B6 | ADR da regra de referência e da blindagem | `adr/0008-usar-o-ab-s-como-referencia-sem-declarar-conformidade.md` | ADR no formato MADR |

Se B3 não for possível até a entrega, as tarefas B1, B2, B4, B5 e B6 continuam válidas, e a falta da resposta válida é declarada como pendência com o motivo.

### Visualização desta frente

- Prints do relatório AB+S mostrando o resultado sem causa nem caminho de regularização (já capturados).
- Diagrama do fluxo PDF → UUID → API pública → comparação lado a lado.
- Tabela de concordância por critério (com dados reais, se B3 der certo; com o modelo da tabela, se não).

## 7. Fontes de produção (segundo plano)

Registradas para mostrar o caminho caso o projeto vá ao ar. **Não são usadas agora.**

| Fonte | Ganho | Por que fica para depois |
|---|---|---|
| API Serpro "Consulta Práticas Agropecuárias Sustentáveis" | Resultado oficial em lote, por CAR + documento | Contrato comercial, restrita a operadores financeiros autorizados pelo Banco Central |
| Download do CAR por UF no portal do SICAR | Base completa de uma vez | Captcha e e-mail; o WFS já atende o recorte |
| SIGEF/INCRA (imóveis certificados) | Geometria fundiária oficial; explica a divergência de área | Download exige login gov.br |
| APIs privadas de CAR (Infosimples e similares) | Automatizam consultas individuais | Pagas e não acrescentam dado ao WFS |
| MapBiomas Alerta | Laudo por alerta, já cruzado com CAR | Exige cadastro e token |

## 8. Frente C — PRODES e a escada entre fontes de cadência diferente (prioridade 3)

### Por que é necessária

O recorte é café em MG, na Mata Atlântica e no Cerrado. O DETER não cobre a Mata Atlântica, então **sem o PRODES o recorte não tem fonte de desmatamento** em boa parte do território.

### O que já se sabe

O TerraBrasilis publica um WFS por bioma (`prodes-mata-atlantica-nb`, `prodes-caatinga-nb`, `prodes-pampa-nb`, `prodes-pantanal-nb`), com a camada `yearly_deforestation`. Campos: `fid`, `state`, `path_row`, `main_class`, `class_name`, `def_cloud`, `julian_day`, `image_date`, `year`, `area_km`, `scene_id`, `source`, `satellite`, `sensor`, `uuid`, `publish_year` e a geometria.

Polígonos na Mata Atlântica por ano: 2021: 26.588 · 2022: 25.389 · 2023: 20.211 · 2024: 13.724 · **2025: 11.221**. A notícia de março de 2026 dava a Mata Atlântica com dados até 2024, mas o serviço já tem 2025. **A cadência tem que ser lida do dado (`publish_year`, `image_date`), não da notícia.**

Ponto de atenção para a data de corte da EUDR (31/12/2020): o ano do PRODES não é o ano civil. Se o "ano 2021" incluir imagens do fim de 2020, filtrar por `year` deixaria entrar desmatamento anterior ao corte. O filtro deve usar `image_date`. O calendário exato precisa ser confirmado (C1).

### Escada entre fontes

Cada evidência de desmatamento carrega fonte, data da imagem, data de publicação e bioma. A regra é de nível 1 (regra explícita), sem ML:

| Situação | Fonte que vale | Estado exibido |
|---|---|---|
| Amazônia ou Cerrado, alerta DETER sem PRODES ainda | DETER | "Alerta não consolidado", com data |
| Amazônia ou Cerrado, PRODES publicado para o período | PRODES | "Supressão confirmada", com data da imagem |
| DETER alerta, PRODES do mesmo período publicado e sem o polígono | PRODES, e o alerta fica registrado | "Alerta não confirmado pela consolidação" |
| Mata Atlântica, Caatinga, Pampa, Pantanal | PRODES (única fonte) | "Supressão confirmada até [data do último lote]" |
| Período depois do último lote publicado, sem DETER | Nenhuma | **"Sem cobertura de [data] até hoje"**: inconclusivo, nunca "sem pendência" |

A última linha é a principal proteção contra falso negativo: um bioma sem fonte recente não pode aparecer como limpo.

### Tarefas

| # | Tarefa | Saída | Pronto quando |
|---|---|---|---|
| C1 | Confirmar o calendário do ano PRODES e o significado de `year`, `image_date` e `publish_year` na documentação do INPE | Nota com fonte | Regra de filtro pela data de corte justificada |
| C2 | Coletar Mata Atlântica e Cerrado nos municípios do recorte (filtro espacial ou por `state`), conferindo `numberMatched` | `inpe_prodes.consultar` + contagens | Anunciado = recebido |
| C3 | Estudo de inconsistências: unicidade do `uuid`, geometria inválida, classes, nuvem (`def_cloud`) | Validações `PRODES_*` em `inpe_prodes.transformar` + tabela | Mesmo nível do estudo do DETER |
| C4 | Tabela de cobertura: bioma × fonte × último dado disponível × data de publicação | Tabela + gráfico de linha do tempo | Datas lidas do serviço, não de notícia |
| C5 | Sobreposição DETER × PRODES no Cerrado do recorte: quantos alertas o PRODES confirmou | `inpe_prodes.confirmar_alertas` + matriz (caderno, seção 6) | Taxa de confirmação medida |
| C6 | ADR da escada | `adr/0009-combinar-deter-e-prodes-por-data-de-imagem-e-cobertura.md` | ADR no formato MADR |

### Visualização desta frente

- Linha do tempo por bioma: até quando cada fonte cobre.
- Mapa do recorte com polígonos PRODES e alertas DETER sobre os CARs.
- Tabela da escada (acima).

## 9. Frente D — Código incremental

Depois que as frentes A e C tiverem evidência, entram no pipeline seguindo o padrão de `pipeline/fontes/inpe_deter.py` (`transformar`, validações com `Validacao`/`Marcas`, `executar`) e com testes sintéticos no estilo de `tests/`:

| Ordem | Módulo | Reaproveita | Observação |
|---|---|---|---|
| 1 | Ajuste de TLS para o SICAR em `pipeline/download.py` ou em um utilitário HTTP | `download.py` (tentativas, conferência de tamanho) | Teste com `monkeypatch`, como em `tests/test_download.py` |
| 2 | `pipeline/fontes/sicar_car.py` | `particoes_mensais` como modelo de partição (aqui por município); `municipios.py` para validar o código IBGE; `shapely` para geometria | Coleta só dos municípios do recorte |
| 3 | `pipeline/fontes/inpe_prodes.py` | Estrutura de `inpe_deter.py` (WFS, CRS, contagem) | Filtro de data pela `image_date` |
| 4 | `pipeline/cruzamento.py`: embargo/alerta → CAR | Regra da tarefa A3 | Nível 1, regra explícita |
| 5 | `pipeline/fontes/ab_s.py`: consulta por UUID | `requests` com tentativas | Sob demanda, fora da execução em lote |

A saída continua em Parquet até a decisão de persistência da Aula 04. ML (resolução de entidade para registros sem documento) e LLM (roteiro de regularização com citação) não entram nesta atividade.

## 10. Execução por agentes

As frentes A e C são independentes e podem rodar em paralelo. A frente B depende de uma ação do autor (B3).

| Pacote | Depende de | Entrega |
|---|---|---|
| 0. Separar documentação, código e dados | — | Estrutura da seção 3 |
| A1–A6 | 0 | `docs/atividade-03/car.md`, evidências, ADR 0007 |
| C1–C6 | 0 | `docs/atividade-03/prodes-e-escada-de-fontes.md`, evidências, ADR 0009 |
| B1, B2, B4, B5, B6 | 0 | `docs/atividade-03/ab-s-validacao-cruzada.md`, ADR 0008 |
| B3 | Autor conseguir um relatório real | Resposta válida documentada |
| D1–D5 | A e C concluídas | Módulos e testes |
| Fechamento | Tudo acima | `docs/atividade-03-investigacao.md`, `inconsistencias-dos-dados.md` e `arquitetura.md` atualizados |

Instruções comuns a todo agente:

- Nenhum número sem o código que o gere (módulo em `pipeline/` ou caderno).
- Nada de `verify=False`, varredura de UUID ou coleta fora do recorte.
- Escrita direta, em português, no mesmo tom dos documentos existentes.
- Commits sem assinatura de ferramenta.

## 11. Montagem final (por último)

- **Dado real lado a lado:** `df.head()` do bruto e do tratado para IBAMA, DETER, CAR e PRODES, a partir do notebook e das evidências.
- **Prints do AB+S:** copiar os prints para `docs/atividade-03/figuras/ab-s/`, recortando a barra de compartilhamento de tela.
- **Slides:** mesmo padrão visual da apresentação anterior (tema, tabelas, imagens agro), com os mapas e tabelas gerados nas frentes A, B e C.

## Fontes

- SICAR, WFS público: `https://geoserver.car.gov.br/geoserver/sicar/wfs` (consultado em 13/10/2026)
- AB+S, API pública de validação: `https://agrobrasil.agricultura.gov.br/abs/backend/api/public/` (consultado em 13/10/2026)
- TerraBrasilis, WFS do PRODES por bioma: `https://terrabrasilis.dpi.inpe.br/geoserver/` (consultado em 13/10/2026)
- FUNAI, WFS: `https://geoserver.funai.gov.br/geoserver/Funai/ows` (consultado em 13/10/2026)
- [API Consulta Práticas Agropecuárias Sustentáveis — Serpro](https://apicenter.estaleiro.serpro.gov.br/documentacao/api-consulta-praticas-agropecuarias-sustentaveis/)
- [Prodes — BiomasBR (INPE)](https://data.inpe.br/biomasbr/en/prodes-annual-monitoring-of-native-vegetation-suppression/)
- [BiomasBR atualiza dados do Prodes — MCTI, 03/2026](https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/2026/03/biomasbr-atualiza-dados-do-prodes-e-divulga-taxa-consolidada-da-amazonia-ja-em-marco)
- [Download de shapefile do CAR — Infosimples](https://infosimples.com/consultas/car-download-shapefile/)
