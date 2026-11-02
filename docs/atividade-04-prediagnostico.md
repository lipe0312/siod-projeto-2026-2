# Atividade 04 — Pré-diagnóstico por imóvel e PRODES em lote

Situação em 01/11/2026. Commits `1b1e599` (pré-diagnóstico) e `7191cae` (PRODES em lote e avaliação na página da demonstração); decisões e medições de 30/10 a 01/11/2026 nas seções 3 a 9.

## 1. O que foi entregue

| Entrega | Código | Evidência |
|---|---|---|
| Pré-diagnóstico de um imóvel: para um CAR, junta SICAR, embargos do IBAMA, DETER confirmado ou não pelo PRODES, PRODES após 2020 e Lista Suja; cada critério sai como pendência, indício, sem ocorrência, não verificado ou inconclusivo, com evidência, encaminhamento e procedência | [`pipeline/prediagnostico.py`](../pipeline/prediagnostico.py), [`pipeline/ficha_html.py`](../pipeline/ficha_html.py) | [`evidencias/atividade-04/prediagnostico/`](evidencias/atividade-04/prediagnostico/) |
| PRODES em lote com verificação da publicação a cada 30 dias; o último ano publicado vem do serviço. Desde 30/10/2026, por UF: seis biomas, partição Parquet por UF, UF pelo contorno, e a UF de cada imóvel novo entra no lote | [`pipeline/fontes/inpe_prodes.py`](../pipeline/fontes/inpe_prodes.py), [`pipeline/territorio.py`](../pipeline/territorio.py) | [`evidencias/atividade-04/prodes-lote/`](evidencias/atividade-04/prodes-lote/), [ADR 0010](arquitetura/adr/0010-persistir-o-prodes-em-lote-e-verificar-a-publicacao-todo-mes.md), [ADR 0013](arquitetura/adr/0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md) |
| Terras indígenas (FUNAI), unidades de conservação (CNUC) e territórios quilombolas (IBGE) em lote, e os critérios 5, 9 e 6 do AB+S por sobreposição | [`pipeline/fontes/`](../pipeline/fontes/), [`pipeline/vetor.py`](../pipeline/vetor.py) | [`evidencias/atividade-04/fontes-ab-s/`](evidencias/atividade-04/fontes-ab-s/), [ADR 0014](arquitetura/adr/0014-verificar-terras-indigenas-quilombolas-e-unidades-de-conservacao-por-sobreposicao.md) |
| Testes | [`tests/test_prediagnostico.py`](../tests/test_prediagnostico.py), [`tests/test_prodes_lote.py`](../tests/test_prodes_lote.py), [`tests/test_territorio.py`](../tests/test_territorio.py), [`tests/test_fontes_sobreposicao.py`](../tests/test_fontes_sobreposicao.py) | `python -m pytest`: 157 passed, 2 skipped |

## 2. HTML gerado na demonstração

`python -m pipeline.prediagnostico --demo` gera as páginas em `data/processed/prediagnostico/`. A cópia versionada, com prints, está em [`evidencias/atividade-04/prediagnostico/`](evidencias/atividade-04/prediagnostico/). São 17 CARs reais: 6 do café de MG, 1 por bioma no resto do país e 4 com sobreposição a área protegida, em 8 UFs (MG, PA, MT, BA, RS, MS, SP e PR). A execução de 02/11/2026 usou as 8 UFs já no lote do PRODES (637.429 polígonos, 167 MB) e deu 17 de 17.

| Página | Caso | Resultado |
|---|---|---|
| [`index.html`](evidencias/atividade-04/prediagnostico/index.html) ([print](evidencias/atividade-04/prediagnostico/index.png)) | Avaliação esperado x obtido, situação do PRODES em lote por UF e um cartão por imóvel | 17 de 17 conferem |
| [`MG-3148103-6245AC9B….html`](evidencias/atividade-04/prediagnostico/MG-3148103-6245AC9B371A4422B2FA8011CFCC5566.html) | Desmatamento após 2020 confirmado pelo PRODES | com pendência |
| [`MG-3166808-A726F93D….html`](evidencias/atividade-04/prediagnostico/MG-3166808-A726F93D7AFF4A0883BFDEA10D64B1F4.html) | Embargo e 8 alertas DETER de 2025 confirmados pelo PRODES Cerrado 2026 | com pendência (embargo e desmatamento) |
| [`MG-3148103-A0B17B31….html`](evidencias/atividade-04/prediagnostico/MG-3148103-A0B17B31272E42CEA4B4C06338C310AF.html) | 3 alertas DETER de 21/08/2026, depois do último PRODES | com indício |
| [`MG-3148103-627F1606….html`](evidencias/atividade-04/prediagnostico/MG-3148103-627F1606409049ABAB34A913E6F37010.html) | Embargo e alerta sobre área já suprimida antes | com pendência (embargo) e indício |
| [`MG-3148103-A63D0A01….html`](evidencias/atividade-04/prediagnostico/MG-3148103-A63D0A01090844CF89342D2544C5847F.html) | CAR com notificação pendente, embargos e alerta confirmado | 2 pendências e 1 indício |
| [`MG-3148103-5527FB32….html`](evidencias/atividade-04/prediagnostico/MG-3148103-5527FB32FFB24B7F850B487724583043.html) | CAR analisado, nada nas fontes verificadas | sem pendência nas fontes verificadas |
| [`PA-1505502-D0CAA14A….html`](evidencias/atividade-04/prediagnostico/PA-1505502-D0CAA14AD3D349D7BCA887F8A15D861E.html) | Paragominas, Amazônia: polígono PRODES 2021 com imagem de 02/08/2021 (a supressão pode ser de antes do corte) | com indício |
| [`MT-5107925-7B986980….html`](evidencias/atividade-04/prediagnostico/MT-5107925-7B98698040DE4C439D7B67CDA0EDDC60.html) | Sorriso, Cerrado | sem pendência nas fontes verificadas |
| [`BA-2918407-16899931….html`](evidencias/atividade-04/prediagnostico/BA-2918407-1689993146174173AC37FC0818E09A85.html) | Juazeiro, Caatinga | sem pendência, com aviso de Caatinga sem DETER desde 19/12/2025 |
| [`RS-4317103-9D7ED9AE….html`](evidencias/atividade-04/prediagnostico/RS-4317103-9D7ED9AE1A034779AF519FCDEE36FFB6.html) | Rosário do Sul, Pampa | sem pendência, com aviso de Pampa sem DETER desde 19/12/2025 |
| [`MS-5003207-620BD0D0….html`](evidencias/atividade-04/prediagnostico/MS-5003207-620BD0D082F34232BBBFCF2F71811690.html) | Corumbá, Pantanal: 4 polígonos PRODES de 2021 a 2025, 342 ha no imóvel | com pendência, com aviso de Pantanal sem DETER desde 12/08/2025 |
| [`SP-3543402-0381059F….html`](evidencias/atividade-04/prediagnostico/SP-3543402-0381059FD0A5487594C09A887A5D2BC8.html) | Ribeirão Preto, Cerrado e Mata Atlântica | sem pendência, com aviso de Mata Atlântica sem DETER desde 14/09/2025 |
| [`PR-4104808-358E3C8A….html`](evidencias/atividade-04/prediagnostico/PR-4104808-358E3C8A7E234C429B2AA0F3F683B005.html) | Cascavel, Mata Atlântica, CAR com notificação | com indício (CAR) |
| [`MS-5006358-72D1C0B4….html`](evidencias/atividade-04/prediagnostico/MS-5006358-72D1C0B44C904850BD9F4A222CA93285.html) | Paranhos: CAR inteiro dentro da TI Ypoi/Triunfo (declarada) e de APA | com pendência (terra indígena); APA e CAR como indício |
| [`PA-1506807-C4579B9B….html`](evidencias/atividade-04/prediagnostico/PA-1506807-C4579B9B17F64708B80882FC553E51FE.html) | Santarém: CAR inteiro dentro do território quilombola Saracura | com pendência (quilombola); CAR como indício |
| [`MG-3164100-799AE47F….html`](evidencias/atividade-04/prediagnostico/MG-3164100-799AE47FE0684CDEB8107378921FB1B7.html) | São Pedro do Suaçuí: CAR dentro de APA e com 1,3 ha de PRODES após 2020 | com pendência (desmatamento); APA como indício |
| [`MG-3160207-F518ED7F….html`](evidencias/atividade-04/prediagnostico/MG-3160207-F518ED7FF13744F8B6CC0E04B04CC63E.html) | Santo Antônio do Itambé: CAR dentro do Parque Estadual Pico do Itambé | com pendência (unidade de conservação) |

Com `--sem-baixar-prodes`, a demonstração não baixa UF nova: o imóvel de UF fora do lote sai com desmatamento inconclusivo ("UF ainda não carregada no lote do PRODES"), nunca "sem ocorrência". Foi assim em 31/10/2026, com o TerraBrasilis fora do ar.

Cada ficha também sai em `.md`, `.json` e `.png` com o mesmo nome. O CPF da demonstração é fictício e não aparece em nenhum arquivo.

## 3. O que a avaliação mede e como passa a ser medida

O "17 de 17" compara o resultado obtido com o esperado gravado em `config.CARS_DEMONSTRACAO`. Esse esperado foi escrito pelo autor depois de olhar as mesmas fontes que o pipeline usa. Por isso a página funciona como **teste de regressão**: avisa quando uma mudança de regra ou de dado altera um caso conhecido. Ela não mede acerto. O caso de Serra do Salitre mostra isso: o esperado foi reescrito em 30/10/2026, quando o PRODES Cerrado 2026 confirmou os 8 alertas.

**Decisão ([ADR 0012](arquitetura/adr/0012-conferir-o-prediagnostico-com-o-relatorio-ab-s-do-imovel.md)):** o gabarito passa a ser o relatório AB+S do mesmo imóvel, conferido depois do cruzamento.

1. O pré-diagnóstico cruza as fontes abertas e grava a ficha.
2. O relatório AB+S entra por um destes caminhos:
   * UUID ou PDF entregue pelo produtor;
   * relatório emitido no atendimento pelo próprio produtor, com o login gov.br dele e o técnico ao lado. O técnico não guarda a senha, e o projeto não emite relatório em nome de ninguém.
3. `ab_s.consultar` confirma o relatório na API pública, e cada critério entra na matriz de concordância.

O gabarito do autor continua como teste de regressão, separado da medida de acerto.

## 4. Precisa de mais dados do AB+S?

Sim. Desde 13/10/2026, nenhuma consulta à API pública devolveu 200. Por isso:

- a estrutura da resposta válida não é conhecida campo a campo;
- a correspondência entre número do critério e código interno (`ab_s.CRITERIOS`) foi feita pelo nome e não está confirmada;
- a matriz de concordância não tem nenhuma linha.

O código para consultar (`ab_s.consultar`) está pronto; falta o dado.

| O que obter | Para quê | Mínimo útil |
|---|---|---|
| PDF original (não print) de um relatório AB+S real, com consentimento escrito do titular | Primeira resposta 200; documentar a estrutura; confirmar os códigos dos critérios | 1 relatório |
| Relatórios de imóveis com o CAR conhecido, de preferência um com "Não conforme" em embargo (7) ou Lista Suja (4) | Preencher a matriz e medir falso positivo e falso negativo | Alguns por situação; um só confere o mapeamento |
| Código de uma habilitação de área de produção | Comparar o desmatamento com o endpoint `area-producao` | 1 código |

## 5. Critérios do AB+S: fontes abertas pesquisadas e integradas

Cada fonte candidata foi testada em 30/10/2026 ([`evidencias/atividade-04/cobertura-e-persistencia/`](evidencias/atividade-04/cobertura-e-persistencia/), script 01). As que respondem sem login entraram no pipeline em lote ([ADR 0014](arquitetura/adr/0014-verificar-terras-indigenas-quilombolas-e-unidades-de-conservacao-por-sobreposicao.md)). Execução de referência em [`evidencias/atividade-04/fontes-ab-s/`](evidencias/atividade-04/fontes-ab-s/).

| # | Critério | Fonte | Situação | Feições (30/10/2026) |
|---|---|---|---|---:|
| 3 | CAR | SICAR, WFS | Já verificado (Atividade 03): existência e status | — |
| 4 | Lista Suja | MTE, PDF | Já verificado (Atividade 02) | — |
| 7 | Embargos do IBAMA | IBAMA, CSV | Já verificado (Atividade 02) | — |
| 5 | Sobreposição: terras indígenas | FUNAI, WFS `Funai:tis_poligonais` ([FUNAI](https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas)) | **Integrado** (`pipeline/fontes/funai_terras_indigenas.py`) | 665 |
| 9 | Sobreposição: unidade de conservação | CNUC/MMA, shapefile 2025_08 ([dados.mma.gov.br](https://dados.mma.gov.br/dataset/unidadesdeconservacao)) | **Integrado** (`pipeline/fontes/mma_unidades_conservacao.py`) | 3.301 |
| 6 | Sobreposição: área quilombola | IBGE, territórios quilombolas oficialmente delimitados, Censo 2022 ([metadados](https://metadadosgeo.ibge.gov.br/geonetwork_ibge/geonetwork_ibge/api/records/2dfb5757-255c-4b13-8d65-cbca4d23e5a1)) | **Integrado, parcial**: base de 31/07/2022, não a do INCRA (`pipeline/fontes/ibge_territorios_quilombolas.py`) | 495 |
| 2 | Fundiária: dados geoespaciais | SIGEF, acervo fundiário do INCRA | Não verificado: `certificacao.incra.gov.br` e `acervofundiario.incra.gov.br` sem resolução de DNS, inclusive no 8.8.8.8 e no 1.1.1.1; o acervo passou a exigir login gov.br | — |
| 8 | Sobreposição: CAR x SIGEF | SIGEF | Não verificado: depende do 2 | — |
| 1 | Fundiária: dados cadastrais | Consulta pública do SNCR ([Serpro](https://sncr.serpro.gov.br/sncr-web/consultaPublica.jsf)) | Não verificado: hCaptcha, e o CSV não traz a situação cadastral | — |

**Resultado:** 6 dos 9 critérios verificados (o 6 em parte), contra 3 antes. Os 3 restantes ficam para a conferência com o relatório AB+S (seção 3).

O que as validações encontraram nas três fontes (detalhe em [`inconsistencias-dos-dados.md`](inconsistencias-dos-dados.md)):

| Fonte | Achado | Quantidade |
|---|---|---:|
| FUNAI | TI sem data de atualização | 143 de 665 |
| FUNAI | Geometria inválida (corrigida) | 2 |
| CNUC | UC sem polígono, só ponto de localização | 180 de 3.301 |
| CNUC | Polígono esquemático | 99 |
| CNUC | Texto cortado no meio de um caractere UTF-8 | 1 |
| CNUC | Geometria ausente (descartada) | 1 |
| IBGE | Nenhuma inconsistência | 0 de 495 |

**Regra de sobreposição.** A área protegida é muito maior que o imóvel, então vale a fração do CAR atingida.
* **Conta como sobreposição:** ao menos 5% do CAR, ou faixa comum com mais de 30 m.
* **Tangente:** abaixo disso; é contato de borda e não conta.

**Situação de cada sobreposição:**
* **Terra indígena:** pendência; "Em Estudo" é indício.
* **Quilombola:** pendência; "Estudo técnico" é indício.
* **Unidade de conservação:**
  * pendência na proteção integral e nas de domínio público;
  * indício em APA, ARIE e RPPN (admitem propriedade privada), em polígono esquemático e em UC só com ponto de localização.

## 6. Pré-diagnóstico no Brasil inteiro

Decisão no [ADR 0013](arquitetura/adr/0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md); implementado em 30/10/2026.

| Problema do teste de 30/10/2026 | Correção |
|---|---|
| Por coordenada, o SICAR era consultado em MG | A UF vem do contorno do IBGE (`pipeline/territorio.py`); ponto fora do Brasil é inconclusivo sem consulta |
| PRODES só de Cerrado e Mata Atlântica | Os seis biomas; cada UF recebe os biomas que tocam o seu contorno (MG tem Caatinga, Cerrado e Mata Atlântica) |
| PRODES sob demanda falhou nos 7 CARs (HTTP 502) | Lote por UF: a UF entra quando o primeiro imóvel dela é consultado (`inpe_prodes.garantir_uf`) e depois não depende do serviço; a carga retoma do que já gravou |
| Filtro pelo campo `state` perdia polígono de divisa | Requisição pelo retângulo da UF e UF de cada polígono pelo contorno; o de divisa entra nas duas UFs |
| Mais de 50 mil polígonos por ano e bioma; 502 em respostas grandes | Retângulo dividido em quatro acima de 8 mil polígonos ou quando o serviço responde 5xx |
| Bioma sem DETER aparecia limpo depois da última imagem PRODES | "Sem ocorrência" com o aviso "sem cobertura de [data] até hoje" (decisão do usuário: não inconclusivo) |
| Fonte que falha virava "sem ocorrência" | Critério inconclusivo com o motivo; o resultado segue pendência > inconclusivo > indício > sem pendência |

Tamanho do PRODES por bioma no Brasil, de 2019 a 2026 (script 02, camada do bioma na Amazônia). Por esse tamanho, o lote cresce por UF em vez de baixar tudo:

| Bioma | Polígonos | Último ano publicado |
|---|---:|---|
| Cerrado | 462.916 (sem 2019, que não respondeu) | 2026 |
| Caatinga | 419.991 | 2025 |
| Amazônia (bioma) | 358.162 | 2025 |
| Mata Atlântica | 153.063 | 2025 |
| Pampa | 33.962 (sem 2021, que não respondeu) | 2025 |
| Pantanal | 9.413 | 2025 |
| **Total contado** | **1.437.507** | — |

## 7. Persistência e agendamento

**Agora: Parquet particionado por UF, sem custo** ([ADR 0011](arquitetura/adr/0011-persistir-em-parquet-por-uf-e-adiar-o-postgis.md)). O PRODES fica em `data/processed/inpe_prodes/uf=XX/part.parquet`, e o pré-diagnóstico lê só a partição da UF do imóvel. As demais fontes nacionais ficam num Parquet cada uma. O agendamento mensal é o `crontab` da máquina do autor.

**Depois, sem prioridade: PostgreSQL com PostGIS**, quando houver API (Aula 05) e acesso por técnico (Aula 08).

Medição (script 04): a mesma consulta, sobre 397.017 geometrias e 300 CARs de Patrocínio.

| Forma | Consulta por CAR | Espaço | Memória por processo | Achados |
|---|---:|---:|---:|---:|
| Parquet + STRtree em memória | 0,01 ms | 139,9 MB | +1.176 MB | 47 |
| DuckDB spatial | 0,32 ms | 370,2 MB | — | 47 |
| PostGIS | 0,63 ms | 276,8 MB | — | 47 |

O desempenho empata. O banco passa a valer quando houver:
* escrita do agendador concorrente com a leitura da API;
* permissão por técnico;
* histórico consultável das fichas.

Opções sem custo para esse passo:
* PostGIS local em Docker;
* Neon gratuito: 1 GB por projeto, com PostGIS ([changelog de 02/10/2026](https://neon.com/docs/changelog/2026-10-02)); comporta o lote por UF;
* Supabase gratuito: 500 MB ([preços](https://supabase.com/pricing)).

## 8. Decisões

| Decisão | Situação | Onde |
|---|---|---|
| Gabarito | **Decidido**: cruzamento primeiro, conferência com o relatório AB+S (UUID do produtor ou relatório emitido no atendimento) | ADR 0012 |
| Persistência | **Decidido**: Parquet particionado por UF, sem custo; PostgreSQL + PostGIS como passo futuro, sem prioridade | ADR 0011 |
| Atualização | **Decidido**: verificação mensal; agendada no `crontab` enquanto não houver servidor | ADR 0011 |
| Polígono na divisa | **Decidido e implementado**: UF pelo contorno do IBGE; o polígono entra nas duas UFs | ADR 0013 |
| Dado incompleto | **Decidido e implementado**: inconclusivo com o motivo; nunca "sem ocorrência" | ADR 0013 |
| Bioma sem DETER | **Decidido e implementado**: "sem ocorrência" com aviso de período sem cobertura | ADR 0013 |
| Recorte | **Decidido e implementado**: Brasil inteiro, por UF, à medida que os imóveis entram | ADR 0013 |
| Critérios 5, 6 e 9 | **Decidido e implementado**: FUNAI, IBGE 2022 e CNUC, por sobreposição; UC por categoria | ADR 0014 |
| Critérios 1, 2 e 8 | **Aberto**: sem fonte aberta acessível (SNCR com captcha; acervo do INCRA fora do ar e com login) | Seção 5 |
| Primeiro relatório AB+S real | **Aberto**: produtor voluntário com consentimento ou relatório emitido num atendimento | Seção 4 |

## 9. Próximos passos

1. **Conseguir o primeiro relatório AB+S real**, registrar a resposta 200 e começar a matriz de concordância (seção 4).
2. **Aceitar o PDF do AB+S no pré-diagnóstico** e mostrar o resultado oficial ao lado de cada critério (ADR 0012).
3. **Acompanhar o acervo do INCRA** (SIGEF e áreas quilombolas): quando voltar a ter endereço público, integrar os critérios 2 e 8 e trocar a base quilombola do IBGE 2022 pela do INCRA.
4. **Agendar a verificação mensal** no `crontab` e validar a dor com técnicos usando as fichas.
5. **Futuro, sem prioridade:** PostgreSQL com PostGIS quando houver API e mais de um usuário (ADR 0011).
