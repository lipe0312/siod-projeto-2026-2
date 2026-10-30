# Projeto de SIOD — 2026.2

Projeto individual da disciplina **Sistemas Inteligentes Orientados a Dados** (IC0046, PGCOMP/UFBA, 2026.2).

O objetivo é apoiar a identificação de pendências socioambientais que impedem produtores rurais de acessar crédito rural e de vender para compradores sujeitos à regulação europeia antidesmatamento. O projeto usa apenas dados públicos.

## Problema

**Contexto.** Duas regras deixaram essas pendências mais caras para o produtor:

- **Regulação europeia (EUDR).** O [Regulamento (UE) 2023/1115](https://eur-lex.europa.eu/eli/reg/2023/1115/oj) passa a valer em 30/12/2026 para empresas grandes e médias, e em 30/06/2027 para micro e pequenas. Ele exige que soja, café, cacau, carne bovina, madeira, borracha e óleo de palma vendidos na União Europeia venham de áreas sem desmatamento após 31/12/2020, seja esse desmatamento legal ou ilegal no país de origem, com geolocalização das áreas de produção.
- **Crédito rural.** No Brasil, o Manual de Crédito Rural (Seção 2-9, Resolução CMN 5.193/2024) já veda crédito a imóveis com embargo ambiental ativo, CAR inexistente, cancelado ou suspenso, sobreposição a unidade de conservação ou terra indígena, e a empregadores incluídos no Cadastro de Empregadores ("Lista Suja").

**Usuário.** Técnico de assistência técnica rural ou de cooperativa que acompanha pequenos e médios produtores. O produtor é o beneficiário direto.

**Dor.** Para saber se um produtor tem pendência, é preciso consultar bases separadas (IBAMA, INPE, Ministério do Trabalho) ou usar a plataforma pública AgroBrasil+Sustentável, que exige o login gov.br do próprio produtor. No [piloto oficial dessa plataforma](https://zerodeforestationhub.eu/wp-content/uploads/2026/08/Dry-run-ABS_PT.pdf), produtores bloqueados não conseguiram identificar qual era o problema nem o procedimento de regularização.

**Dados.**
- Áreas Embargadas do IBAMA;
- alertas de desmatamento do INPE (DETER e PRODES);
- Cadastro de Empregadores do Ministério do Trabalho;
- indicadores de preço do CEPEA.

A caracterização completa está em [`docs/atividade-01-dados.md`](docs/atividade-01-dados.md).

**Resultado esperado.** O técnico decide quais produtores atender primeiro e qual pendência tratar em cada caso, com a fonte de cada evidência.

## Hipótese aplicada

> Se construirmos um pré-diagnóstico de pendências socioambientais que aponte a causa, a fonte e o encaminhamento de cada pendência, usando o cruzamento de bases públicas do IBAMA, do INPE e do Ministério do Trabalho, esperamos aumentar a proporção de pendências com causa identificada e reduzir o tempo de triagem por produtor, para técnicos de assistência técnica e cooperativas que atendem pequenos produtores, em comparação com a consulta separada a cada base e à plataforma AgroBrasil+Sustentável.

## Maior risco

O maior risco é atribuir uma pendência ao produtor errado ou deixar de apontar uma pendência real. As bases públicas não trazem o código do CAR, e parte dos registros não tem localização.

O primeiro teste foi a Atividade 01, que mediu quanto das bases permite identificar o responsável e localizar a área. A Atividade 04 conferiu o pré-diagnóstico em 6 CARs reais, mas com o resultado esperado escrito pelo próprio autor: é teste de regressão, não medida de acerto. O próximo é um gabarito independente, com relatórios AB+S reais ou revisão de um técnico.

## O que mudou após a caracterização dos dados

- **Pré-diagnóstico, não atestado.** O sistema entrega um pré-diagnóstico com a evidência de cada pendência, e não um atestado de conformidade.
- **Embargo não basta.** A EUDR também veda desmatamento autorizado, que não gera embargo, então os alertas do INPE após 31/12/2020 são parte central do cruzamento.
- **Geolocalização vira entrada obrigatória.** Como não há download em massa do CAR, a localização da área de produção precisa ser informada. Sem ela, o resultado é marcado como inconclusivo.

## Entregas

| Atividade | O que entrega | Documento com a explicação completa | Onde está o que foi produzido |
|---|---|---|---|
| **01 — Caracterização e avaliação dos dados** | Fonte, qualidade dos dados, dicionário mínimo, análise exploratória e síntese técnica | [`docs/atividade-01-dados.md`](docs/atividade-01-dados.md) | [`notebooks/01_exploracao_dados.ipynb`](notebooks/01_exploracao_dados.ipynb) |
| **02 — Pipeline inicial de dados** | Pipeline para CSV, API e PDF, com validações comprovadas por testes, evidência de execução, arquitetura e decisões | [`docs/atividade-02-pipeline.md`](docs/atividade-02-pipeline.md) | [`pipeline/`](pipeline/), [`tests/`](tests/), [`docs/evidencias/atividade-02/`](docs/evidencias/atividade-02/), [`docs/arquitetura/`](docs/arquitetura/) |
| **03 — Investigação de fontes: CAR, PRODES e AB+S** | CAR pelo WFS do SICAR, PRODES e a escada entre fontes de desmatamento, AB+S como referência; as três como fontes sob demanda do pipeline e a atribuição de embargo ou alerta a um CAR | [`docs/atividade-03-investigacao.md`](docs/atividade-03-investigacao.md) e [`docs/atividade-03/`](docs/atividade-03/) | [`notebooks/02_fontes_antes_e_depois.ipynb`](notebooks/02_fontes_antes_e_depois.ipynb), [`pipeline/fontes/`](pipeline/fontes/), [`pipeline/cruzamento.py`](pipeline/cruzamento.py), [`tests/`](tests/) |
| **04 — Pré-diagnóstico por imóvel e PRODES em lote** | Ficha por CAR com situação, evidência, encaminhamento e procedência de cada critério; demonstração com 6 CARs reais; PRODES persistido com verificação mensal da publicação | [`docs/atividade-04-prediagnostico.md`](docs/atividade-04-prediagnostico.md) | [`pipeline/prediagnostico.py`](pipeline/prediagnostico.py), [`pipeline/ficha_html.py`](pipeline/ficha_html.py), [`docs/evidencias/atividade-04/`](docs/evidencias/atividade-04/) (página da demonstração: [`prediagnostico/index.html`](docs/evidencias/atividade-04/prediagnostico/index.html)) |

Os documentos trazem os números medidos, o que cada verificação encontrou e o motivo de cada decisão. Este README explica como reproduzir tudo.

## Arquitetura

Versão 1 em [`docs/arquitetura/arquitetura.md`](docs/arquitetura/arquitetura.md): fontes de dados e pipeline definidos, demais camadas previstas. As decisões com alternativas estão em [`docs/arquitetura/adr/`](docs/arquitetura/adr/).

## Próximos passos

Detalhe e decisões em aberto em [`docs/atividade-04-prediagnostico.md`](docs/atividade-04-prediagnostico.md), seções 5 e 6.

1. Obter um relatório AB+S real (PDF, com consentimento do titular) para registrar a primeira resposta válida da API e montar um gabarito independente do pipeline.
2. Aceitar o PDF do AB+S no pré-diagnóstico e mostrar o resultado oficial ao lado de cada critério.
3. Incluir as bases de terras indígenas, unidades de conservação e áreas quilombolas, que hoje aparecem como "não verificado".
4. Definir a camada de persistência e carregar nela os parquets e as fichas, com histórico.
5. Agendar a verificação mensal do PRODES e validar a dor com técnicos de assistência técnica e de cooperativas.

## Como reproduzir na sua máquina

### Requisitos

- **Python 3.12**. As versões das bibliotecas estão fixadas em [`requirements.txt`](requirements.txt).
- **Git** e **acesso à internet**. Todas as fontes são públicas e não exigem cadastro.
- Cerca de **300 MB livres** para os dados baixados e gerados em `data/`.

Todos os comandos abaixo são executados **na pasta raiz do repositório**, com o ambiente virtual ativado. Depois de ativado, os comandos `python -m ...` e `jupyter ...` são iguais em macOS, Linux e Windows.

### 1. Preparar o ambiente

**macOS / Linux**

```bash
git clone https://github.com/lipe0312/siod-projeto-2026-2.git
cd siod-projeto-2026-2
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/lipe0312/siod-projeto-2026-2.git
cd siod-projeto-2026-2
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

No **Prompt de Comando (cmd)**, a ativação é `.venv\Scripts\activate.bat`. Se o PowerShell bloquear a ativação, execute antes `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, que vale só para aquela janela.

Para conferir: `python --version` deve mostrar 3.12.

### 2. Atividade 01 — reproduzir a caracterização dos dados

A análise está em [`notebooks/01_exploracao_dados.ipynb`](notebooks/01_exploracao_dados.ipynb). Abra no Jupyter e execute todas as células em ordem (menu *Kernel → Restart & Run All*):

```bash
jupyter notebook notebooks/01_exploracao_dados.ipynb
```

Também dá para executar sem abrir a interface. A cópia executada vai para `data/notebook_executado/`, e o notebook versionado não é alterado:

```bash
jupyter nbconvert --to notebook --execute notebooks/01_exploracao_dados.ipynb --output-dir data/notebook_executado
```

Na primeira execução, a base do IBAMA (cerca de 150 MB) é baixada para `data/raw/areas_embargadas.csv`, e a procedência fica em `data/raw/areas_embargadas.meta.json`. Com a base já baixada, a execução leva menos de um minuto.

**O que conferir.** Cada parte do notebook sustenta uma seção de [`docs/atividade-01-dados.md`](docs/atividade-01-dados.md):

| Parte do notebook | Seção do documento |
|---|---|
| 1 — Obtenção da fonte principal (URL, data, SHA-256) | 2. Caracterização da fonte |
| 2 — Leitura correta (codificação e CPF/CNPJ como texto) | 3. Inconsistências de formato ou codificação |
| 3 e 4 — Dimensão, intervalo temporal e valores ausentes | 2. Dimensão e 3. Valores ausentes |
| 5 — Duplicidades, grafias, registros incorretos, cobertura geográfica | 3. Avaliação inicial da qualidade |
| 6 — Estatísticas do domínio | 5. Análise exploratória |
| 7 — Fontes complementares (INPE, Lista Suja, CEPEA, SICAR) | 2. Fontes complementares |
| 8 — O que os dados permitem e o que falta | 6. Síntese técnica |

As fontes são atualizadas continuamente, então as contagens podem variar um pouco em relação às registradas no documento. A base do IBAMA, por exemplo, passou de 91.197 para 91.199 registros entre duas coletas no mesmo dia. A parte 7.5 depende do SICAR, que é instável; se ele não responder, isso é o comportamento esperado e está explicado no próprio notebook.

### 3. Atividade 02 — reproduzir o pipeline

**a) Testes.** São rápidos e não usam internet. Comprovam cada validação com dados sintéticos:

```bash
python -m pytest
```

O resultado esperado é `121 passed, 2 skipped`: 51 testes da Atividade 02, 40 da Atividade 03 e 30 da Atividade 04. Os testes ignorados são marcados `rede` e consultam o SICAR e o PRODES de verdade; só rodam com `python -m pytest --rede`. A tabela da seção 4 de [`docs/atividade-02-pipeline.md`](docs/atividade-02-pipeline.md) liga cada validação da Atividade 02 ao teste que a comprova.

**b) Execução completa.** Baixa as quatro fontes e gera as saídas:

```bash
python -m pipeline
```

A primeira execução baixa cerca de 180 MB e leva de 6 a 7 minutos, a maior parte na coleta dos alertas do INPE. As execuções seguintes reaproveitam o que já foi baixado. Outras opções:

```bash
python -m pipeline --fontes ibama              # só uma ou algumas fontes: ibama, deter, prodes, lista_suja
python -m pipeline --desde 2021-01-01          # início do recorte dos alertas DETER
python -m pipeline --atualizar                 # baixar tudo de novo
python -m pipeline --fontes prodes --verificar-prodes  # verificar a publicação do PRODES antes de 30 dias
python -m pipeline --evidencia minha_execucao  # copiar relatório e log para uma pasta
python -m pipeline --help
```

**c) Onde ver o resultado.**

| O que | Onde |
|---|---|
| Relatório da execução (contagens, transformações e cada validação) | `data/processed/relatorio_execucao.md` e `.json` |
| Log com as mensagens da execução | `data/logs/pipeline_<data>_<hora>.log` |
| Tabelas tratadas | `data/processed/ibama_embargos.parquet`, `inpe_deter_alertas.parquet`, `mte_lista_suja.parquet`, `ibge_municipios.parquet` |
| Registros descartados, com o motivo | `data/processed/ibama_embargos_descartados.parquet`, `inpe_deter_alertas_descartados.parquet` |
| Arquivos brutos e procedência | `data/raw/` (cada arquivo com um `.meta.json`; as respostas do INPE com um `manifesto.json`) |
| Execução de referência, para comparar | [`docs/evidencias/atividade-02/`](docs/evidencias/atividade-02/) |

O processo termina com código 0 quando todas as fontes processam sem erro. Para comparar com a execução de referência, abra `data/processed/relatorio_execucao.md` ao lado do relatório em `docs/evidencias/atividade-02/`. O status deve ser `ok` e as contagens devem ser iguais ou muito próximas, pelo mesmo motivo de atualização das fontes.

Para conferir rapidamente quantos registros cada tabela tem (o comando é igual nos três sistemas):

```bash
python -c "import pandas as pd; [print(f, len(pd.read_parquet(f'data/processed/{f}.parquet'))) for f in ['ibge_municipios','ibama_embargos','inpe_deter_alertas','mte_lista_suja']]"
```

**d) Chave de pseudonimização.** O CPF/CNPJ é substituído por um código calculado com uma chave secreta. Se a variável `SIOD_CHAVE_PSEUDONIMIZACAO` não estiver definida, a chave é criada em `data/chave_pseudonimizacao` e reutilizada nas execuções seguintes. Para usar uma chave própria:

```bash
export SIOD_CHAVE_PSEUDONIMIZACAO="sua-chave"        # macOS / Linux
```

```powershell
$env:SIOD_CHAVE_PSEUDONIMIZACAO = "sua-chave"         # Windows (PowerShell)
```

### 4. Atividade 03 — fontes sob demanda e o caderno das fontes

SICAR (CAR), PRODES e AB+S não entram em `python -m pipeline`: são consultados sob demanda, só para a área ou o relatório do caso. Cada consulta devolve o DataFrame tratado e o `ResultadoFonte` com as validações, e grava a resposta bruta em `data/raw/<fonte>/` com um `.meta.json` (URL, parâmetros, data UTC, SHA-256). Repetir a mesma consulta reaproveita o que foi gravado; `atualizar=True` consulta de novo.

```python
from pipeline import cruzamento
from pipeline.fontes import ab_s, inpe_prodes, sicar

car, resultado = sicar.consultar_ponto(-18.94, -46.99)                    # CAR que contém o ponto (lat, lon)
car, resultado = sicar.consultar_municipio("3148103")                     # todos os CARs de Patrocínio (MG)
prodes, resultado = inpe_prodes.consultar("cerrado", uf="MG", desde=2019) # PRODES, um ano por requisição
```

O caderno [`notebooks/02_fontes_antes_e_depois.ipynb`](notebooks/02_fontes_antes_e_depois.ipynb) mostra, para cada fonte, o dado bruto, o dado tratado, as validações e os casos de erro que motivaram cada tratamento. Ele lê as saídas de `python -m pipeline`, então rode o pipeline antes:

```bash
jupyter nbconvert --to notebook --execute notebooks/02_fontes_antes_e_depois.ipynb --output-dir data/notebook_executado
```

A primeira execução consulta o SICAR (10 municípios e uma consulta por embargo ou alerta do recorte, com pausa entre elas), o PRODES e o DETER do Cerrado de MG e a API do AB+S, e leva alguns minutos; as seguintes reaproveitam as respostas gravadas (cerca de 30 MB em `data/raw/`). As contagens podem mudar um pouco quando as fontes são atualizadas. A explicação de cada número está em [`docs/atividade-03-investigacao.md`](docs/atividade-03-investigacao.md) e nos documentos de [`docs/atividade-03/`](docs/atividade-03/).

### 5. Pré-diagnóstico de um imóvel

Do ponto de vista do produtor: para um CAR, junta o status no SICAR, os embargos do IBAMA (pelo polígono, pela coordenada ou pelo documento), os alertas DETER confirmados ou não pelo PRODES, os polígonos PRODES após 2020 e a Lista Suja. A saída é uma ficha em HTML (com mapa), Markdown e JSON em `data/processed/prediagnostico/`. Cada critério sai como pendência, indício, sem ocorrência, não verificado ou inconclusivo, com a evidência, o encaminhamento e a procedência. Precisa dos parquets de `python -m pipeline` (com o PRODES, seção 6). A página da demonstração confere o resultado de cada caso com o esperado, e cada ficha mostra como o resultado se formou e a linha do tempo das evidências diante da data de corte.

```bash
python -m pipeline.prediagnostico --demo                                   # 6 CARs reais prontos; abra data/processed/prediagnostico/index.html
python -m pipeline.prediagnostico --car MG-3148103-6245AC9B371A4422B2FA8011CFCC5566 --documento 111.444.777-35
python -m pipeline.prediagnostico --ponto -18.94 -46.99                    # CAR que contém a coordenada da sede
```

O documento é pseudonimizado com a mesma chave do pipeline e nunca é gravado em claro. Prints e fichas da demonstração estão em [`docs/evidencias/atividade-04/prediagnostico/`](docs/evidencias/atividade-04/prediagnostico/).

### 6. PRODES em lote, conferido todo mês

O PRODES sai uma vez por ano, sem data fixa. `python -m pipeline --fontes prodes` grava os anos desde 2019 do Cerrado e da Mata Atlântica em MG (`config.PRODES_UFS_LOTE`) em `data/processed/inpe_prodes.parquet`, limpo e validado como as outras fontes. A cada execução:

- se a última verificação tem menos de 30 dias, não vai à rede;
- senão, conta os polígonos de cada ano no Brasil: o último ano com polígono é o último publicado (não há mais ano fixo no código);
- em cada ano e UF, compara a contagem com a gravada no manifesto e baixa de novo só o que mudou, mais o último ano publicado (o INPE pode revisá-lo);
- registra ano novo, ano consolidado alterado e último ano revisado no histórico, em `data/processed/inpe_prodes_publicacao.json`, com as datas de imagem (mínima e máxima) de cada ano.

Para rodar todo mês sozinho, agende no `crontab -e` (exemplo, todo dia 1 às 6h):

```
0 6 1 * * cd /caminho/siod-projeto-2026-2 && .venv/bin/python -m pipeline --fontes prodes
```

O pré-diagnóstico lê esse parquet quando o imóvel está numa UF do recorte; fora dele, consulta o PRODES sob demanda. Na primeira verificação (30/10/2026), o Cerrado já tinha o ano 2026 publicado, e isso confirmou 8 alertas de 2025 que antes apareciam como "aguardando consolidação". Evidência em [`docs/evidencias/atividade-04/prodes-lote/`](docs/evidencias/atividade-04/prodes-lote/).

### Problemas comuns

| Situação | O que fazer |
|---|---|
| Download interrompido pelo servidor | O pipeline confere o tamanho recebido e tenta até 3 vezes. Se ainda falhar, rode `python -m pipeline` de novo: o que já foi baixado é reaproveitado |
| Uma fonte falhou e as outras não | Cada fonte é independente. A fonte com problema aparece como `erro` no relatório, com a mensagem; rode de novo só ela com `--fontes` |
| `python` abre outra versão | Confirme que o ambiente virtual está ativado; o nome `.venv` aparece no início da linha do terminal |
| O PowerShell não ativa o ambiente | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` e ative de novo |

## Onde encontrar cada coisa

| Arquivo ou pasta | O que faz | Atividade |
|---|---|---|
| [`docs/atividade-01-dados.md`](docs/atividade-01-dados.md) | Caracterização da fonte, qualidade, dicionário e síntese técnica | 01 |
| [`notebooks/01_exploracao_dados.ipynb`](notebooks/01_exploracao_dados.ipynb) | Análise exploratória reproduzível que sustenta o documento da Atividade 01 | 01 |
| [`docs/atividade-02-pipeline.md`](docs/atividade-02-pipeline.md) | Entrada, transformações, validações com seus testes, evidência, arquitetura e registro de decisão | 02 |
| [`pipeline/__main__.py`](pipeline/__main__.py) | Linha de comando: ordem das fontes, isolamento de falhas, relatório final | 02 |
| [`pipeline/config.py`](pipeline/config.py) | Endereços das fontes, caminhos e constantes (UFs, biomas, limites do Brasil, classes DETER) | 02 |
| [`pipeline/download.py`](pipeline/download.py) | Download com procedência, novas tentativas e conferência de tamanho; consulta com cache para as fontes sob demanda | 02 e 03 |
| [`pipeline/validacao.py`](pipeline/validacao.py) | Registro de cada validação (código, severidade, tratamento, contagens) e coluna `alertas` | 02 |
| [`pipeline/documentos.py`](pipeline/documentos.py) | Dígito verificador de CPF/CNPJ e pseudonimização | 02 |
| [`pipeline/municipios.py`](pipeline/municipios.py) | Referência de municípios do IBGE e resolução de município por nome | 02 |
| [`pipeline/relatorio.py`](pipeline/relatorio.py) | Log em arquivo e relatório em JSON e Markdown | 02 |
| [`pipeline/fontes/ibama_embargos.py`](pipeline/fontes/ibama_embargos.py) | Fonte tabular: embargos do IBAMA (CSV) | 02 |
| [`pipeline/fontes/inpe_deter.py`](pipeline/fontes/inpe_deter.py) | Fonte API: alertas de desmatamento do INPE (WFS/GeoJSON) | 02 |
| [`pipeline/fontes/mte_lista_suja.py`](pipeline/fontes/mte_lista_suja.py) | Fonte documento: Lista Suja do Ministério do Trabalho (PDF) | 02 |
| [`pipeline/wfs.py`](pipeline/wfs.py) | Requisição, contagem e filtros espaciais (ordem dos eixos) comuns aos serviços WFS | 03 |
| [`pipeline/fontes/sicar.py`](pipeline/fontes/sicar.py) | Fonte sob demanda: CAR pelo WFS do SICAR, por município, retângulo ou ponto | 03 |
| [`pipeline/fontes/inpe_prodes.py`](pipeline/fontes/inpe_prodes.py) | PRODES em lote com verificação mensal da publicação (04) e sob demanda por bioma e ano; confirmação dos alertas DETER | 03, 04 |
| [`pipeline/fontes/ab_s.py`](pipeline/fontes/ab_s.py) | Fonte sob demanda: validação do relatório AB+S pelo código de autenticidade | 03 |
| [`pipeline/cruzamento.py`](pipeline/cruzamento.py) | Atribuição de embargo ou alerta a um CAR (principal, parcial, tangente) | 03 |
| [`pipeline/prediagnostico.py`](pipeline/prediagnostico.py) | Pré-diagnóstico de um imóvel: critérios, situação, evidência, encaminhamento e procedência | 04 |
| [`pipeline/ficha_html.py`](pipeline/ficha_html.py) | Ficha do pré-diagnóstico em HTML, com o mapa do imóvel em SVG | 04 |
| [`tests/test_ibama_embargos.py`](tests/test_ibama_embargos.py) | Validações da fonte IBAMA | 02 |
| [`tests/test_inpe_deter.py`](tests/test_inpe_deter.py) | Validações da fonte DETER, incluindo identificador e completude das partições | 02 |
| [`tests/test_mte_lista_suja.py`](tests/test_mte_lista_suja.py) | Segmentação e validações da Lista Suja | 02 |
| [`tests/test_municipios.py`](tests/test_municipios.py) | Referência do IBGE e resolução por nome | 02 |
| [`tests/test_documentos.py`](tests/test_documentos.py) | CPF/CNPJ e pseudonimização | 02 |
| [`tests/test_download.py`](tests/test_download.py) | Download truncado e registro de procedência | 02 |
| [`tests/test_execucao.py`](tests/test_execucao.py) | Comportamento quando a referência do IBGE está indisponível | 02 |
| [`tests/test_sicar.py`](tests/test_sicar.py), [`test_inpe_prodes.py`](tests/test_inpe_prodes.py), [`test_ab_s.py`](tests/test_ab_s.py), [`test_cruzamento.py`](tests/test_cruzamento.py) | Validações das fontes sob demanda, ordem dos eixos, regra de confirmação do PRODES e de atribuição ao CAR | 03 |
| [`tests/test_prediagnostico.py`](tests/test_prediagnostico.py) | Pré-diagnóstico: situação de cada critério, divisa não atribuída, PRODES por ano, inconclusivo, documento nunca em claro, avaliação esperado x obtido | 04 |
| [`tests/test_prodes_lote.py`](tests/test_prodes_lote.py) | PRODES em lote com serviço falso: reaproveita dentro do mês, ano novo, ano consolidado alterado, último ano que recua | 04 |
| [`docs/atividade-03-investigacao.md`](docs/atividade-03-investigacao.md), [`docs/atividade-03/`](docs/atividade-03/) | Investigação do CAR, do PRODES e do AB+S | 03 |
| [`docs/atividade-04-prediagnostico.md`](docs/atividade-04-prediagnostico.md) | Pré-diagnóstico, PRODES em lote, o que a avaliação mede, AB+S pendente, próximos passos e decisões em aberto | 04 |
| [`docs/evidencias/atividade-04/`](docs/evidencias/atividade-04/) | Fichas da demonstração (HTML, MD, JSON, print) e execuções do PRODES em lote | 04 |
| [`notebooks/02_fontes_antes_e_depois.ipynb`](notebooks/02_fontes_antes_e_depois.ipynb) | Cada fonte antes e depois do tratamento, com as validações e os casos de erro | 03 |
| [`docs/evidencias/atividade-02/`](docs/evidencias/atividade-02/) | Relatório e log da execução de referência | 02 |
| [`docs/arquitetura/arquitetura.md`](docs/arquitetura/arquitetura.md) | Arquitetura (versão 1) | 02 |
| [`docs/arquitetura/adr/`](docs/arquitetura/adr/) | Registros de decisão técnica | 02 |
| [`requirements.txt`](requirements.txt) | Bibliotecas e versões | 01 a 04 |
| `data/` | Gerada localmente: `raw/` (baixados), `processed/` (saídas), `logs/`, chave de pseudonimização. Não é versionada porque contém dados pessoais | 01 a 04 |
