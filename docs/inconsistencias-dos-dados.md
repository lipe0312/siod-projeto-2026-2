# Inconsistências dos dados

Resumo das inconsistências encontradas nas fontes do projeto e de como cada uma é tratada. Os números vêm da execução de referência do pipeline ([`docs/evidencias/atividade-02/`](evidencias/atividade-02/)), do notebook da Atividade 01 e, para as fontes da Atividade 03, do caderno [`notebooks/02_fontes_antes_e_depois.ipynb`](../notebooks/02_fontes_antes_e_depois.ipynb). Como as fontes são atualizadas continuamente, os valores podem variar entre execuções.

Tratamentos usados:
- **erro:** interrompe a fonte;
- **descarte:** o registro vai para um arquivo de descartados, com o motivo;
- **correção:** ajuste automático e registrado;
- **alerta:** o registro é mantido, o campo inválido é anulado e o código vai para a coluna `alertas`.

## IBAMA — Áreas Embargadas (91.199 registros)

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| Servidor não informa a codificação (o arquivo é UTF-8; lido como Latin-1, os acentos se corrompem) | — | Leitura explícita em UTF-8 |
| CPF/CNPJ interpretado como número perde o zero à esquerda | 25.490 identificadores | Leitura de todas as colunas como texto |
| CPF/CNPJ ausente | 9.233 | Alerta |
| CPF/CNPJ com tamanho inválido | 2 | Alerta; documento anulado |
| CPF/CNPJ com dígito verificador inválido | 164 | Alerta; documento anulado |
| Número + série do termo repetido em registros diferentes | 250 linhas (105 termos) | Identificador composto por número + série + sequencial ([ADR 0003](arquitetura/adr/0003-identificar-embargos-por-numero-serie-e-sequencial.md)) |
| Sequencial do termo ausente | 1.446 | Coberto pelo identificador composto |
| Data do embargo no futuro (25/09/2925) | 1 | Alerta; data anulada |
| Código de município inexistente no IBGE | 17 | Alerta; mantidos o nome e a UF da própria base |
| Só latitude ou só longitude preenchida | 1.087 | Alerta; coordenada anulada |
| Coordenada (0, 0) | 3.180 | Alerta; coordenada anulada |
| Coordenada fora do Brasil | 255 | Alerta; coordenada anulada |
| Área igual a zero ou negativa | 406 | Alerta; área anulada |
| Área com vírgula decimal, gravada como texto | Todos | Conversão para número |
| Bioma em texto livre: itens repetidos ("Amazonia, Amazonia"), sem acento e em ordem variável (39 grafias para 7 categorias) | 44.619 | Correção: itens únicos, ordenados e acentuados |
| Polígono ausente | 44,6% | Mantido; localização pela coordenada, quando existir |
| WKT ilegível | 1 | Alerta; geometria anulada |
| Polígono topologicamente inválido | 117 | Alerta; mantido sem correção |
| Sem documento válido, sem polígono e sem coordenada válida | 252 | Descarte |
| Nome do imóvel preenchido em só 12,2% | — | Campo fora da saída |
| Não existem campos de código do CAR, cultura do produtor nem autorização de supressão | — | Limitação declarada; a localização terá de ser informada pelo produtor |

## INPE — Alertas DETER (233.777 alertas desde 2021)

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| `gid` repetido para trechos do mesmo alerta em municípios vizinhos (Cerrado) | 1.848 alertas | Identificador calculado pelo conteúdo ([ADR 0004](arquitetura/adr/0004-coletar-alertas-deter-em-particoes-mensais-e-identificar-pelo-conteudo.md)) |
| `gid` reutilizado por alertas de datas e lugares diferentes (Amazônia) | 39.890 `gid` | Identificador calculado pelo conteúdo |
| Paginação ordenada por `gid` repetia registros entre páginas | — | Coleta com uma requisição por mês; completude conferida em cada mês |
| Camada Cerrado sem código IBGE de município | 87.234 alertas | Código obtido por nome + UF na lista do IBGE ([ADR 0005](arquitetura/adr/0005-resolver-municipio-dos-alertas-deter-pela-referencia-do-ibge.md)) |
| Nome de município sem acento (Amazônia) ou em maiúsculas com acento (Cerrado) | — | Normalização do nome antes da comparação |
| Nome antigo de município (ex.: "Fortaleza do Tabocão" → Tabocão) | 90 alertas | Correção por tabela de 4 apelidos |
| Polígono topologicamente inválido | 17.841 (7,6%) | Alerta; mantido sem correção |
| Mesma geometria, classe e data em `gid` diferentes | 6 | Alerta |
| Coordenadas em SIRGAS 2000 (EPSG:4674), não em WGS84 | Todos | Sistema verificado a cada coleta; diferente disso, interrompe |
| Várias classes misturadas (degradação, queimada, mineração etc.) | — | Filtro nas classes de desmatamento |
| DETER não cobre Mata Atlântica, Caatinga, Pampa e Pantanal | — | Limitação declarada; o PRODES anual é a referência para esses biomas (seção PRODES abaixo) |

## MTE — Lista Suja (PDF, 714 linhas de tabela)

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| Cabeçalho da tabela repetido em cada página | 45 | Removido na segmentação |
| Títulos repetidos em cada página | 90 | Removidos na segmentação |
| Células com quebra de linha (empregador, estabelecimento, inclusão) | 294 células | Limpeza do texto |
| Registro sem UF, ano, CNAE e data de decisão | 3 | Alerta; campos anulados |
| Número de trabalhadores ausente | 2 | Alerta; campo anulado |
| Vários períodos de inclusão na mesma célula | 10 | Correção: primeira e última data em colunas separadas |
| Inclusão no cadastro anterior à decisão administrativa | 1 | Alerta |
| Mesmo empregador em mais de um registro | 22 | Alerta; mantidos (estabelecimentos diferentes) |
| Extração pela biblioteca `agrobr` gerava linhas de cabeçalho como dado e linhas sem documento | — | Extração própria do PDF ([ADR 0006](arquitetura/adr/0006-extrair-a-lista-suja-diretamente-do-pdf-oficial.md)) |

## SICAR — CAR (33.452 imóveis em 10 municípios cafeeiros de MG)

Consultado sob demanda ([`pipeline/fontes/sicar.py`](../pipeline/fontes/sicar.py)). Números do caderno [`notebooks/02_fontes_antes_e_depois.ipynb`](../notebooks/02_fontes_antes_e_depois.ipynb), seção 5; detalhe em [`atividade-03/car.md`](atividade-03/car.md).

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| Recebido diferente do anunciado, código fora do formato, código repetido, status desconhecido, sem geometria | 0 | Erro (contagem) ou descarte |
| Geometria inválida (autointerseção) | 13 | Correção com `make_valid` |
| Município no código do CAR diferente de `cod_municipio_ibge` | 54 | Alerta; vale `cod_municipio_ibge` e o cruzamento é pela geometria |
| Ponto interno do imóvel fora do município declarado (malha do IBGE) | 298 | Alerta |
| Área declarada difere mais de 1% da área da geometria | 24 | Alerta; frações calculadas com a área da geometria |
| Status `CA` (cancelado) | 476 | Alerta; não serve como CAR do imóvel |
| Imóvel com 95% ou mais da área coberta por outros CARs | 6.727 (20,11%) | Alerta; a atribuição lista todos os CARs atingidos |
| Dos 6.727 sobrepostos, com status `AT`, apesar de a IN MMA nº 2/2014 prever `PE` para sobreposição | 5.537 | `AT` sozinho não é tratado como sinal de regularidade |
| Embargo ou alerta com mais de um CAR principal (CARs sobrepostos) | 44 de 179 | Alerta; todos os principais são listados (caderno, seção 8) |
| Embargo ou alerta sem nenhum CAR | 3 de 179 | Registrado como "sem CAR localizado", nunca "sem CAR" |

## INPE — PRODES Cerrado de MG (56.708 polígonos de 2019 a 2025)

Consultado sob demanda ([`pipeline/fontes/inpe_prodes.py`](../pipeline/fontes/inpe_prodes.py)). Números do caderno, seção 6; detalhe em [`atividade-03/prodes-e-escada-de-fontes.md`](atividade-03/prodes-e-escada-de-fontes.md).

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| UF por extenso no Cerrado (`MINAS GERAIS`) e como sigla na Mata Atlântica (`MG`) | 56.708 | Correção para a sigla; filtro de UF montado conforme o bioma |
| Geometria inválida | 4.966 (8,8%) | Correção com `make_valid` antes de qualquer interseção |
| `image_date` fora de 01/08 do ano anterior a 31/07 do `year` | 32.446 | Alerta; a data de corte usa `image_date`, não `year` |
| `area_km` difere mais de 10% da área calculada da geometria | 763 | Alerta; usar a área calculada |
| `publish_year` repete 01/01 do `year` e não informa a publicação | Todos | Campo ignorado |
| `main_class` diferente de `DESMATAMENTO`, `uuid` nulo ou repetido | 0 | Descarte |
| Polígono do PRODES 2021 sobre alerta DETER com imagem entre 01/08 e 31/12/2020 (supressão possivelmente anterior ao corte, datada de 2021) | 166 alertas | A escada de fontes combina DETER e PRODES ([ADR 0009](arquitetura/adr/0009-combinar-deter-e-prodes-por-data-de-imagem-e-cobertura.md)) |

### PRODES em lote, primeira versão (Atividade 04): MG, Cerrado e Mata Atlântica, 112.817 polígonos de 2019 a 2026

Execução de 30/10/2026 em [`evidencias/atividade-04/prodes-lote/`](evidencias/atividade-04/prodes-lote/).

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| `main_class` diferente de `DESMATAMENTO` (ex.: `RESERVATORIO`) | 100 | Descarte |
| Geometria inválida | 12.211 | Correção com `make_valid` |
| UF por extenso | 62.897 | Correção para a sigla |
| `image_date` fora do ano PRODES | 59.838 | Alerta; vale `image_date` |
| `area_km` difere mais de 10% da área calculada | 1.654 | Alerta; usar a área calculada |
| Último ano publicado diferente do que o código supunha: Cerrado 2026 já publicado, constante em 2025 | 1 bioma | O último ano passou a vir da contagem do serviço ([ADR 0010](arquitetura/adr/0010-persistir-o-prodes-em-lote-e-verificar-a-publicacao-todo-mes.md)) |

Na versão por UF ([ADR 0013](arquitetura/adr/0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md)), o recorte passou a ser o contorno da UF: o campo `state` diferente do contorno vira o alerta `PRODES_UF_DIFERE_DO_CONTORNO`, e o polígono do retângulo que não toca a UF é descartado da partição (`PRODES_FORA_DO_CONTORNO_DA_UF`). MG também tem Caatinga, que a primeira versão deixava de fora.

### PRODES em lote por UF (Atividade 04): 8 UFs, seis biomas, 637.429 polígonos de 2019 a 2026

Partições de MG, BA, PA, RS, MT, MS, PR e SP, carregadas de 30/10 a 02/11/2026 ([`evidencias/atividade-04/prodes-lote/`](evidencias/atividade-04/prodes-lote/)). Contagens lidas das partições e de `inpe_prodes_descartados.parquet`.

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| `main_class` em minúsculas (`desmatamento`) na camada da Amazônia: quase todo 2019 e 2020 e 254 polígonos de 2021 a 2025, em PA e MT | 68.132 | Correção para maiúsculas (`PRODES_CLASSE_CAIXA_DIFERENTE`). Até 02/11/2026 esses polígonos eram descartados como classe fora do domínio |
| `main_class` fora do domínio (`RESERVATORIO`, `QUEIMADA`) | 1.838 | Descarte |
| `uuid` repetido entre partes do retângulo dividido | 1.024 | Descarte da cópia |
| `image_date` fora do ano PRODES | 434.897 | Alerta; vale `image_date` |
| `area_km` difere mais de 10% da área calculada | 24.175 | Alerta; usar a área calculada |
| Campo `state` diferente da UF do contorno | 771 | Alerta `UF_DIFERE_DO_CONTORNO`; vale o contorno, e o `state` fica em `uf_fonte` |
| Polígono de divisa, presente na partição de duas UFs | 176 | Mantido nas duas, com a mesma `uf` (a do ponto representativo) |
| `state` vazio | 1 (PR) | UF anulada; vale o contorno |
| Anel degenerado que interrompe o `make_valid` do GEOS ("mixed-dimension"): Mata Atlântica 2024 em MG, e depois um alerta DETER em PA | 2 geometrias | `vetor.tornar_valida` tenta o método `structure`; vale para todas as fontes |
| Combinação de ano, bioma e UF com mais de 8 mil polígonos ou resposta 5xx | 292 de 386 | Retângulo dividido em quatro até caber (`PRODES_RETANGULO_DIVIDIDO`) |

## AB+S — API pública de validação

Consultada sob demanda, um relatório por vez ([`pipeline/fontes/ab_s.py`](../pipeline/fontes/ab_s.py)); detalhe em [`atividade-03/ab-s-validacao-cruzada.md`](atividade-03/ab-s-validacao-cruzada.md).

| Inconsistência | Tratamento |
|---|---|
| A API não valida o formato do código: texto qualquer recebe 404 em `qualificacao` e `area-producao` e 500 em `habilitacao` | Formato validado antes da consulta; código malformado não é enviado |
| 404 não distingue código errado, relatório de ambiente de teste e relatório inexistente | Registrado como "não localizado na consulta pública em [data]" |
| O mesmo rótulo "Não conforme" serve para falta de dado no INCRA e para irregularidade | Classificado à parte na comparação |

## FUNAI — Terras indígenas (665)

Em lote, pelo WFS `Funai:tis_poligonais` ([`pipeline/fontes/funai_terras_indigenas.py`](../pipeline/fontes/funai_terras_indigenas.py)). Execução de 30/10/2026 em [`evidencias/atividade-04/fontes-ab-s/`](evidencias/atividade-04/fontes-ab-s/).

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| `data_atualizacao` vazia | 143 | Alerta; a ficha cita a data da coleta |
| Geometria inválida | 2 | Correção com `make_valid` |
| Código repetido, geometria ausente, fase ou UF fora do domínio | 0 | Descarte ou alerta |

## MMA — Unidades de conservação do CNUC (3.302 recebidas)

Em lote, pelo shapefile mais recente com endereço em `dados.mma.gov.br` (2025_08) ([`pipeline/fontes/mma_unidades_conservacao.py`](../pipeline/fontes/mma_unidades_conservacao.py)).

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| UC sem limite no CNUC, só um ponto de localização (camada `_pontos`) | 180 | Alerta; ponto dentro do imóvel é indício |
| Polígono é "representação esquemática da localização da UC" | 99 | Alerta; sobreposição vira indício |
| Texto do DBF cortado no meio de um caractere UTF-8 | 1 | Lido com o caractere de substituição |
| Feição sem geometria | 1 | Descarte |
| Grupo nos pontos abreviado (`PI`, `US`) e esfera em minúsculas | 180 | Correção para o texto por extenso |
| Shapefile mais novo (2026_07) só num link do SharePoint | — | Usado o último com endereço estável (2025_08) |

## IBGE — Territórios quilombolas delimitados, Censo 2022 (495)

Em lote, pelo shapefile do IBGE ([`pipeline/fontes/ibge_territorios_quilombolas.py`](../pipeline/fontes/ibge_territorios_quilombolas.py)), no lugar das áreas quilombolas do INCRA, que não têm endereço público ([ADR 0014](arquitetura/adr/0014-verificar-terras-indigenas-quilombolas-e-unidades-de-conservacao-por-sobreposicao.md)).

| Inconsistência | Quantidade | Tratamento |
|---|---:|---|
| Polígonos com coordenada Z | 495 | Z descartado |
| Base parada em 31/07/2022 | todos | Data citada na ficha; critério marcado como parcial |
| Código repetido, geometria inválida, situação ou UF fora do domínio | 0 | — |

## IBGE — Municípios (5.571)

Nenhuma inconsistência encontrada. As verificações de estrutura, quantidade, UF, código repetido e nome + UF repetido ficaram todas em zero.

## Serviços de origem

| Inconsistência | Tratamento |
|---|---|
| Download do IBAMA interrompido pelo servidor sem erro (parou em 136 de 148 MB) | Limite de espera, até 3 tentativas e conferência do tamanho recebido |
| SICAR alterna entre recusar a conexão, não responder e redirecionar, sem download em massa | Consulta sob demanda pelo WFS, por município, retângulo ou ponto |
| Servidor do SICAR só aceita TLS antigo; o `requests` com a configuração padrão falha no *handshake* | Adaptador com cifras de nível 1 e renegociação legada, com o certificado verificado |
| No WFS 2.0 em EPSG:4674 (SICAR e TerraBrasilis), o filtro espacial sem SRS lê (latitude, longitude); na ordem trocada devolve zero, sem erro | Ordem fixada em `config.ORDEM_EIXOS_FILTRO`, com teste; a contagem anunciada é conferida |
| CEPEA devolve só cerca de 15 dias de preços por consulta | Usado só no notebook; série histórica pendente |
| Bases atualizadas continuamente (o IBAMA mudou de 91.197 para 91.199 registros no mesmo dia) | Procedência registrada a cada execução (data e SHA-256) |
| TerraBrasilis respondeu HTTP 502 de forma intermitente em 30/10/2026: as 7 consultas do PRODES sob demanda fora de MG falharam, e a contagem de Cerrado 2019 e Pampa 2021 não saiu depois de 4 tentativas | PRODES nacional em lote, guardado no banco, com retomada; falha de fonte vira critério inconclusivo ([ADR 0013](arquitetura/adr/0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md)) |
| FUNAI (WFS de terras indígenas) não envia o certificado intermediário; o `requests` falha na verificação | Intermediário buscado no endereço AIA do próprio certificado e somado à cadeia do certifi, com a verificação ligada |
| FUNAI responde 403 a GetFeature sem `count` e a `resultType=hits` | Pedido sempre com `count`; contagem feita pelas feições recebidas |
| `certificacao.incra.gov.br` e `acervofundiario.incra.gov.br` (SIGEF e áreas quilombolas) não resolveram no DNS em 30/10/2026; o agrobr registrou que não respondem de fora do Brasil | Coleta a partir de uma máquina no Brasil ([ADR 0011](arquitetura/adr/0011-persistir-em-parquet-por-uf-e-adiar-o-postgis.md)) |
| A consulta pública do SNCR tem hCaptcha | Não automatizada: o projeto não contorna captcha |
| O shapefile mais recente do CNUC (2026_07) só está num link do SharePoint, e a resposta do portal traz links pessoais de servidores | Coleta automática do último shapefile com endereço estável (2025_08); resposta bruta do portal guardada só em `data/raw/` |
