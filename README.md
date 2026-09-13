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

## Arquitetura

Em definição. O desenho será registrado em [`docs/arquitetura/`](docs/arquitetura/), e as decisões em [`docs/arquitetura/adr/`](docs/arquitetura/adr/).

## Próximos passos

1. Definir a arquitetura inicial e a fatia vertical.
2. Validar a dor com técnicos de assistência técnica e de cooperativas.
3. Consultar as feições do PRODES nos demais biomas e as bases de terras indígenas, unidades de conservação e florestas públicas.
4. Implementar a leitura e a validação dos dados a partir dos problemas identificados na Atividade 01.
5. Montar uma amostra simulada de produtores, com gabarito, para avaliar o sistema.

## Estrutura

```
docs/
  atividade-01-dados.md        caracterização e avaliação dos dados
  arquitetura/
    arquitetura.md             desenho da arquitetura (em definição)
    adr/                       registros de decisão
notebooks/
  01_exploracao_dados.ipynb    análise exploratória reproduzível
requirements.txt
```

## Como executar

Requer Python 3.12 e acesso à internet.

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
jupyter notebook notebooks/01_exploracao_dados.ipynb
```

Execute as partes do notebook em ordem. Na primeira execução, a base do IBAMA (cerca de 150 MB) é baixada para `data/raw/`. A pasta `data/` não é versionada porque as bases contêm dados pessoais.
