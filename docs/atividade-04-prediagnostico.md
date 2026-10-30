# Atividade 04 — Pré-diagnóstico por imóvel e PRODES em lote

Situação em 30/10/2026. Commits `1b1e599` (pré-diagnóstico) e `7191cae` (PRODES em lote e avaliação na página da demonstração).

## 1. O que foi entregue

| Entrega | Código | Evidência |
|---|---|---|
| Pré-diagnóstico de um imóvel: para um CAR, junta SICAR, embargos do IBAMA, DETER confirmado ou não pelo PRODES, PRODES após 2020 e Lista Suja; cada critério sai como pendência, indício, sem ocorrência, não verificado ou inconclusivo, com evidência, encaminhamento e procedência | [`pipeline/prediagnostico.py`](../pipeline/prediagnostico.py), [`pipeline/ficha_html.py`](../pipeline/ficha_html.py) | [`evidencias/atividade-04/prediagnostico/`](evidencias/atividade-04/prediagnostico/) |
| PRODES em lote (MG, Cerrado e Mata Atlântica, desde 2019) com verificação da publicação a cada 30 dias; o último ano publicado passou a vir do serviço, e não de uma constante | [`pipeline/fontes/inpe_prodes.py`](../pipeline/fontes/inpe_prodes.py), `config.PRODES_UFS_LOTE` | [`evidencias/atividade-04/prodes-lote/`](evidencias/atividade-04/prodes-lote/), [ADR 0010](arquitetura/adr/0010-persistir-o-prodes-em-lote-e-verificar-a-publicacao-todo-mes.md) |
| Testes | [`tests/test_prediagnostico.py`](../tests/test_prediagnostico.py), [`tests/test_prodes_lote.py`](../tests/test_prodes_lote.py) | `python -m pytest`: 121 passed, 2 skipped (30 testes da Atividade 04) |

## 2. HTML gerado na demonstração

`python -m pipeline.prediagnostico --demo` gera as páginas em `data/processed/prediagnostico/`. A cópia versionada, com prints, está em [`evidencias/atividade-04/prediagnostico/`](evidencias/atividade-04/prediagnostico/):

| Página | Caso | Resultado |
|---|---|---|
| [`index.html`](evidencias/atividade-04/prediagnostico/index.html) ([print](evidencias/atividade-04/prediagnostico/index.png)) | Avaliação esperado x obtido, situação do PRODES em lote e um cartão por imóvel | 6 de 6 conferem |
| [`MG-3148103-6245AC9B….html`](evidencias/atividade-04/prediagnostico/MG-3148103-6245AC9B371A4422B2FA8011CFCC5566.html) | Desmatamento após 2020 confirmado pelo PRODES | com pendência |
| [`MG-3166808-A726F93D….html`](evidencias/atividade-04/prediagnostico/MG-3166808-A726F93D7AFF4A0883BFDEA10D64B1F4.html) | Embargo e 8 alertas DETER de 2025 confirmados pelo PRODES Cerrado 2026 | com pendência (embargo e desmatamento) |
| [`MG-3148103-A0B17B31….html`](evidencias/atividade-04/prediagnostico/MG-3148103-A0B17B31272E42CEA4B4C06338C310AF.html) | 3 alertas DETER de 21/08/2026, depois do último PRODES | com indício |
| [`MG-3148103-627F1606….html`](evidencias/atividade-04/prediagnostico/MG-3148103-627F1606409049ABAB34A913E6F37010.html) | Embargo e alerta sobre área já suprimida antes | com pendência (embargo) e indício |
| [`MG-3148103-A63D0A01….html`](evidencias/atividade-04/prediagnostico/MG-3148103-A63D0A01090844CF89342D2544C5847F.html) | CAR com notificação pendente, embargos e alerta confirmado | 2 pendências e 1 indício |
| [`MG-3148103-5527FB32….html`](evidencias/atividade-04/prediagnostico/MG-3148103-5527FB32FFB24B7F850B487724583043.html) | CAR analisado, nada nas fontes verificadas | sem pendência nas fontes verificadas |

Cada ficha também sai em `.md`, `.json` e `.png` com o mesmo nome. O CPF da demonstração é fictício e não aparece em nenhum arquivo.

## 3. O que a avaliação mede e o que não mede

O "6 de 6" compara o obtido com o esperado gravado em `config.CARS_DEMONSTRACAO`. Esse esperado foi escrito pelo autor depois de inspecionar as mesmas fontes que o pipeline usa. Por isso a página funciona como **teste de regressão** (avisa quando uma mudança de regra ou de dado altera um caso conhecido), e não como medida de acerto. O caso de Serra do Salitre mostra isso: o esperado foi reescrito em 30/10/2026, quando o PRODES Cerrado 2026 confirmou os 8 alertas.

Medir acerto exige um gabarito independente do pipeline: relatórios AB+S reais (matriz de concordância, [`atividade-03/ab-s-validacao-cruzada.md`](atividade-03/ab-s-validacao-cruzada.md), seção 7) ou casos revisados por um técnico.

## 4. Precisa de mais dados do AB+S?

Sim. Nada mudou desde 13/10/2026: não há nenhuma resposta 200 da API pública, então:

- a estrutura da resposta válida não é conhecida campo a campo;
- a correspondência entre número do critério e código interno (`ab_s.CRITERIOS`) foi feita pelo nome e não está confirmada;
- a matriz de concordância não tem nenhuma linha, e o pré-diagnóstico não tem gabarito externo.

O pré-diagnóstico já usa a tabela de critérios do AB+S: os 6 critérios sem fonte aberta aparecem como "não verificado", com o encaminhamento "Conferir no relatório do AgroBrasil+Sustentável do produtor". O que falta é dado, não código: o caminho `ab_s.consultar(uuid, chave)` está pronto.

| O que obter | Para quê | Mínimo útil |
|---|---|---|
| PDF original (não print) de um relatório AB+S real, com consentimento escrito do titular | Primeira resposta 200; documentar a estrutura; confirmar os códigos dos critérios | 1 relatório |
| Relatórios de imóveis com o CAR conhecido, de preferência um com "Não conforme" em embargo (7) ou Lista Suja (4) | Preencher a matriz de concordância e medir falso positivo e falso negativo do pré-diagnóstico | Alguns relatórios por situação; um só confere o mapeamento, não mede qualidade |
| Código de autenticidade de uma habilitação de área de produção | Comparar o critério de desmatamento com o endpoint `area-producao` | 1 código |

## 5. Próximos passos

1. **Gabarito independente.** Obter relatórios AB+S reais (seção 4) ou revisão dos 6 casos por um técnico, e separar na página o teste de regressão da medida de acerto.
2. **Mostrar o AB+S ao lado da ficha.** Aceitar o PDF do relatório no pré-diagnóstico (`ab_s.extrair_uuid` → `ab_s.consultar`) e exibir o resultado oficial por critério, como prevê o ADR 0008. Hoje a ficha só manda conferir o relatório.
3. **Reduzir os "não verificado".** Integrar terras indígenas (FUNAI, WFS já registrado), unidades de conservação e áreas quilombolas, que cobririam os critérios 5, 9 e 6 do AB+S.
4. **Persistência.** Decidir a camada (ver seção 6) e carregar nela os parquets e as fichas, com histórico das avaliações.
5. **Agendar a verificação mensal do PRODES** (crontab do README, seção 6) e registrar a próxima verificação, prevista para 29/11/2026.
6. **Validar a dor com técnicos** de assistência técnica e de cooperativas, usando as fichas da demonstração como material.
7. **Ampliar o recorte do lote** para outras UFs e biomas, se o caso de uso pedir (`config.PRODES_UFS_LOTE`).

## 6. Decisões em aberto

| Decisão | Opções | O que pesa |
|---|---|---|
| Como conseguir o relatório AB+S real | Produtor voluntário com consentimento; relatório divulgado pelo próprio titular; conta gov.br própria (só com imóvel no SNCR); declarar a falta como limite da entrega | Sem ele, o projeto não mede a qualidade do pré-diagnóstico |
| Quem define o gabarito | AB+S oficial; técnico; autor (situação atual) | O gabarito do autor é circular (seção 3) |
| Camada de persistência | Manter Parquet; DuckDB com extensão espacial; PostgreSQL/PostGIS | Consulta espacial, histórico das fichas e o que a Aula 04 pedir; a arquitetura deixa a decisão para essa aula |
| Fontes para os critérios 5, 6 e 9 | Integrar agora; deixar como "não verificado" | Cada uma reduz falso negativo, mas traz validação nova e pode ter data desatualizada (o próprio AB+S mostra 01/01/2010) |
| Onde roda a verificação mensal | Máquina do autor (crontab); serviço agendado | Sem agendamento, o último ano publicado só se atualiza quando alguém roda o pipeline |
| Polígono PRODES na divisa de UF | Aceitar o limite do filtro por `state` (ADR 0010); filtrar pelo contorno da UF | O filtro atual pode perder polígono gravado com a UF vizinha |
| Recorte geográfico | Só MG (café); outras UFs produtoras | Tamanho do parquet (cerca de 25 MB só para MG) e tempo da verificação |
