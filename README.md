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

O primeiro teste foi a Atividade 01, que mediu quanto das bases permite identificar o responsável e localizar a área. O próximo é avaliar o cruzamento em uma amostra de produtores com gabarito conhecido.

## O que mudou após a caracterização dos dados

- **Pré-diagnóstico, não atestado.** O sistema entrega um pré-diagnóstico com a evidência de cada pendência, e não um atestado de conformidade.
- **Embargo não basta.** A EUDR também veda desmatamento autorizado, que não gera embargo, então os alertas do INPE após 31/12/2020 são parte central do cruzamento.
- **Geolocalização vira entrada obrigatória.** Como não há download em massa do CAR, a localização da área de produção precisa ser informada. Sem ela, o resultado é marcado como inconclusivo.

## Entregas

| Atividade | O que entrega | Documento com a explicação completa | Onde está o que foi produzido |
|---|---|---|---|
| **01 — Caracterização e avaliação dos dados** | Fonte, qualidade dos dados, dicionário mínimo, análise exploratória e síntese técnica | [`docs/atividade-01-dados.md`](docs/atividade-01-dados.md) | [`notebooks/01_exploracao_dados.ipynb`](notebooks/01_exploracao_dados.ipynb) |
| **02 — Pipeline inicial de dados** | Pipeline para CSV, API e PDF, com validações comprovadas por testes, evidência de execução, arquitetura e decisões | [`docs/atividade-02-pipeline.md`](docs/atividade-02-pipeline.md) | [`pipeline/`](pipeline/), [`tests/`](tests/), [`docs/evidencias/`](docs/evidencias/), [`docs/arquitetura/`](docs/arquitetura/) |

Os dois documentos trazem os números medidos, o que cada verificação encontrou e o motivo de cada decisão. Este README explica como reproduzir tudo.

## Arquitetura

Versão 1 em [`docs/arquitetura/arquitetura.md`](docs/arquitetura/arquitetura.md): fontes de dados e pipeline definidos, demais camadas previstas. As decisões com alternativas estão em [`docs/arquitetura/adr/`](docs/arquitetura/adr/).

## Próximos passos

1. Validar a dor com técnicos de assistência técnica e de cooperativas.
2. Definir a camada de persistência e carregar nela as saídas do pipeline.
3. Montar uma amostra simulada de produtores, com gabarito, e implementar a regra de cruzamento da fatia vertical.
4. Incluir no pipeline o PRODES dos demais biomas e as bases de terras indígenas, unidades de conservação e florestas públicas.

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

O resultado esperado é `51 passed`. A tabela da seção 4 de [`docs/atividade-02-pipeline.md`](docs/atividade-02-pipeline.md) liga cada validação ao teste que a comprova.

**b) Execução completa.** Baixa as quatro fontes e gera as saídas:

```bash
python -m pipeline
```

A primeira execução baixa cerca de 180 MB e leva de 6 a 7 minutos, a maior parte na coleta dos alertas do INPE. As execuções seguintes reaproveitam o que já foi baixado. Outras opções:

```bash
python -m pipeline --fontes ibama              # só uma ou algumas fontes: ibama, deter, lista_suja
python -m pipeline --desde 2021-01-01          # início do recorte dos alertas DETER
python -m pipeline --atualizar                 # baixar tudo de novo
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
| Execução de referência, para comparar | [`docs/evidencias/`](docs/evidencias/) |

O processo termina com código 0 quando todas as fontes processam sem erro. Para comparar com a execução de referência, abra `data/processed/relatorio_execucao.md` ao lado do relatório em `docs/evidencias/`. O status deve ser `ok` e as contagens devem ser iguais ou muito próximas, pelo mesmo motivo de atualização das fontes.

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
| [`pipeline/download.py`](pipeline/download.py) | Download com procedência, novas tentativas e conferência de tamanho | 02 |
| [`pipeline/validacao.py`](pipeline/validacao.py) | Registro de cada validação (código, severidade, tratamento, contagens) e coluna `alertas` | 02 |
| [`pipeline/documentos.py`](pipeline/documentos.py) | Dígito verificador de CPF/CNPJ e pseudonimização | 02 |
| [`pipeline/municipios.py`](pipeline/municipios.py) | Referência de municípios do IBGE e resolução de município por nome | 02 |
| [`pipeline/relatorio.py`](pipeline/relatorio.py) | Log em arquivo e relatório em JSON e Markdown | 02 |
| [`pipeline/fontes/ibama_embargos.py`](pipeline/fontes/ibama_embargos.py) | Fonte tabular: embargos do IBAMA (CSV) | 02 |
| [`pipeline/fontes/inpe_deter.py`](pipeline/fontes/inpe_deter.py) | Fonte API: alertas de desmatamento do INPE (WFS/GeoJSON) | 02 |
| [`pipeline/fontes/mte_lista_suja.py`](pipeline/fontes/mte_lista_suja.py) | Fonte documento: Lista Suja do Ministério do Trabalho (PDF) | 02 |
| [`tests/test_ibama_embargos.py`](tests/test_ibama_embargos.py) | Validações da fonte IBAMA | 02 |
| [`tests/test_inpe_deter.py`](tests/test_inpe_deter.py) | Validações da fonte DETER, incluindo identificador e completude das partições | 02 |
| [`tests/test_mte_lista_suja.py`](tests/test_mte_lista_suja.py) | Segmentação e validações da Lista Suja | 02 |
| [`tests/test_municipios.py`](tests/test_municipios.py) | Referência do IBGE e resolução por nome | 02 |
| [`tests/test_documentos.py`](tests/test_documentos.py) | CPF/CNPJ e pseudonimização | 02 |
| [`tests/test_download.py`](tests/test_download.py) | Download truncado e registro de procedência | 02 |
| [`tests/test_execucao.py`](tests/test_execucao.py) | Comportamento quando a referência do IBGE está indisponível | 02 |
| [`docs/evidencias/`](docs/evidencias/) | Relatório e log da execução de referência | 02 |
| [`docs/arquitetura/arquitetura.md`](docs/arquitetura/arquitetura.md) | Arquitetura (versão 1) | 02 |
| [`docs/arquitetura/adr/`](docs/arquitetura/adr/) | Registros de decisão técnica | 02 |
| [`requirements.txt`](requirements.txt) | Bibliotecas e versões | 01 e 02 |
| `data/` | Gerada localmente: `raw/` (baixados), `processed/` (saídas), `logs/`, chave de pseudonimização. Não é versionada porque contém dados pessoais | 01 e 02 |
