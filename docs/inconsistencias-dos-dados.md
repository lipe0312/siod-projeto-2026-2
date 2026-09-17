# Inconsistências dos dados

Resumo das inconsistências encontradas nas fontes do projeto e de como cada uma é tratada. Os números vêm da execução de referência do pipeline ([`docs/evidencias/`](evidencias/)) e do notebook da Atividade 01. Como as fontes são atualizadas continuamente, os valores podem variar entre execuções.

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
| DETER não cobre Mata Atlântica, Caatinga, Pampa e Pantanal | — | Limitação declarada; o PRODES anual será a referência para esses biomas |

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

## IBGE — Municípios (5.571)

Nenhuma inconsistência encontrada. As verificações de estrutura, quantidade, UF, código repetido e nome + UF repetido ficaram todas em zero.

## Serviços de origem

| Inconsistência | Tratamento |
|---|---|
| Download do IBAMA interrompido pelo servidor sem erro (parou em 136 de 148 MB) | Limite de espera, até 3 tentativas e conferência do tamanho recebido |
| SICAR alterna entre recusar a conexão, não responder e redirecionar, sem download em massa | Fora do pipeline; limitação declarada |
| CEPEA devolve só cerca de 15 dias de preços por consulta | Usado só no notebook; série histórica pendente |
| Bases atualizadas continuamente (o IBAMA mudou de 91.197 para 91.199 registros no mesmo dia) | Procedência registrada a cada execução (data e SHA-256) |
