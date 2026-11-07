# Visão do produto: o que o cliente recebe e o que ele entrega

Situação em 02/11/2026. Liga o que já funciona ao que falta para o técnico usar o sistema no dia a dia.

## Nome do produto

**AgroValid** (escolhido em 03/11/2026). "Valid" porque o produto valida cada critério com fonte e data, e porque nunca declara "conforme": o que não tem fonte fica "não verificado". "Agro" no início facilita a busca pelo setor. O nome serve ao pré-diagnóstico e a uma futura consultoria de fazenda (por exemplo, "AgroValid Consultoria").

Checagens feitas em 03/11/2026: `agrovalid.com` e `agrovalid.com.br` sem registro no Verisign e no Registro.br, e nenhuma marca com esse nome em busca aberta na web. Os domínios ainda não foram registrados e a **consulta de marca no INPI não foi feita**. Marca e identidade visual (logo e cores) estão em aberto.

## 1. Quem usa e para quê

O **cliente** é a cooperativa ou a empresa de assistência técnica rural. O **usuário** é o técnico que acompanha os produtores. O **beneficiário** é o produtor, que precisa de crédito rural (MCR, Seção 2-9) e de vender para comprador sujeito à EUDR (30/12/2026 para empresas grandes e médias).

A pergunta que o sistema responde é: **quais produtores da minha carteira atendo primeiro, qual pendência trato em cada um e com qual evidência?**

## 2. O que o cliente vê no final

| Tela | O que mostra | Situação |
|---|---|---|
| **Carteira priorizada** | Uma linha por imóvel, ordenada: pendência > inconclusivo > indício > sem pendência; dentro do grupo, mais pendências e maior área primeiro. Para cada um: o que apareceu, o primeiro passo e o link da ficha | **Pronta** (`python -m pipeline.carteira`, 02/11/2026) |
| **Ficha do imóvel** | Para cada critério: situação, evidência (mapa, polígonos, datas, área no imóvel), encaminhamento, fonte e data do dado e SHA-256 de cada arquivo | **Pronta** (Atividade 04) |
| **Mudanças desde o último mês** | Imóveis cujo resultado mudou depois da rotina mensal (PRODES novo, DETER novo, embargo novo, Lista Suja nova), com o critério que mudou | Sim (04/11/2026): a carteira compara cada imóvel com a execução anterior da mesma organização (`resultados.mudancas`, visão `diag.mudanca` no banco); colunas `mudou` e `o_que_mudou` no CSV e "N imóveis mudaram desde <data>" no topo do HTML |
| **Resultado oficial do AB+S ao lado** | Quando o produtor traz o relatório AB+S, cada critério mostra o resultado do pipeline e o oficial. A matriz de concordância mede o acerto | A fazer: depende do primeiro relatório real (ADR 0012) |
| **Dossiê para o comprador (EUDR)** | Polígono da área de produção, ausência de desmatamento após 31/12/2020 com a fonte e a data de cada imagem, e o que não foi verificado | Sim (05/11/2026, #6): `python -m pipeline.prediagnostico --car <cod> --dossie-eudr [--area-producao arquivo.kml] [--commodity café]` grava `dossie.geojson`, `dossie.md` e `dossie.json`. Com área de produção, mostra o desmatamento na área declarada (decide a EUDR) e no resto do imóvel (risco, indício) em linhas separadas ([ADR 0018](arquitetura/adr/0018-cruzar-o-desmatamento-na-area-declarada-e-a-legalidade-no-imovel-inteiro.md)). Para a carteira toda: `python -m pipeline.carteira planilha.xlsx --dossie-eudr` gera uma pasta por imóvel e o `indice.csv` (#20). Fica de fora: envio ao comprador ou à UE e assinatura digital |

O sistema nunca diz "conforme". Diz o que encontrou, onde e quando; o que não tem fonte aparece como "não verificado".

## 3. O que os stakeholders entregam

### Cooperativa ou técnico: uma planilha

Uma planilha (XLSX ou CSV) com uma linha por imóvel. Modelo: [`docs/modelos/carteira_modelo.csv`](modelos/carteira_modelo.csv).

| Coluna | Obrigatória | Para quê | Se faltar |
|---|---|---|---|
| `id_produtor` | sim | Código da própria cooperativa, para o técnico achar o produtor na lista. Nunca o CPF | A linha é recusada |
| `cod_car` | um dos dois | Localiza o imóvel no SICAR (está no recibo de inscrição do CAR) | Usa `lat`/`lon` |
| `lat`, `lon` | um dos dois | Coordenada da sede ou da área de produção, quando o produtor não tem o recibo | Sem nenhum dos dois, a linha fica inconclusiva |
| `documento` | não | CPF ou CNPJ do titular: Lista Suja e embargo por documento. É pseudonimizado e nunca gravado | Lista Suja "não verificado"; embargo só pelo polígono |
| `ccir` | não | Critério 1 do AB+S (SNCR), que não tem consulta aberta | Critério 1 "não verificado" |
| `codigo_sigef` | não | Critérios 2 e 8 (SIGEF), que exigem login gov.br | Critérios 2 e 8 "não verificado" |
| `relatorio_ab_s` | não | UUID ou PDF do relatório AB+S, para conferir com o pipeline | Sem conferência |
| `area_producao` | não | Caminho, relativo à pasta da planilha, de um KML ou GeoJSON com o polígono da área de produção (EUDR). O desmatamento (DETER e PRODES) é cruzado com ele, e a ficha diz qual polígono foi usado e avisa se a área está fora do CAR ou com mais de 5% fora | Desmatamento cruzado com o imóvel inteiro. Arquivo ilegível ou fora da pasta: aviso "área de produção não lida: <motivo>" na ficha |
| outras (`nome_area`, `commodity`...) | não | Passam direto para a saída | — |

A carteira confere cada linha antes de consultar qualquer serviço:
* linha sem localização;
* coordenada fora do Brasil, quase sempre `lat` e `lon` trocados;
* documento com dígito verificador inválido.

A linha com problema sai na lista como inconclusiva, com o motivo.

### Produtor: no atendimento

* Consentimento por escrito (LGPD) para o uso do CPF e do CAR.
* Recibo do CAR, CCIR e número da certificação SIGEF, se tiver.
* O relatório AB+S. Pode ser emitido ali, com o login gov.br dele e o técnico ao lado. O técnico não guarda a senha (ADR 0012).
* Para a EUDR, o polígono da área de produção (KML ou GeoJSON; shapefile ainda não), quando não for o imóvel inteiro. Declare só onde a commodity foi produzida, nunca a fazenda inteira por precaução, e um polígono por parcela; até 4 ha pode ser um ponto. Como demarcar e o que comprova: [`eudr-area-de-producao.md`](eudr-area-de-producao.md).

### Fontes públicas: nada a pedir

São atualizadas pela rotina mensal ([`agendamento/`](../agendamento/LEIA-ME.md)): IBAMA, DETER (Amazônia, Cerrado e Pantanal), PRODES (seis biomas, 27 UFs), Lista Suja, FUNAI, CNUC e áreas quilombolas do INCRA e do IBGE. O SICAR é consultado na hora, por imóvel.

## 4. Como funciona de ponta a ponta

1. **Todo mês, sem ninguém:** a rotina mensal atualiza as fontes em lote.
   * O PRODES só é baixado de novo quando a versão do arquivo muda (ADR 0015).
   * A demonstração dos 17 imóveis roda como teste de regressão.
2. **A cooperativa envia a planilha.** Cada imóvel leva cerca de 2 s:
   * consulta ao SICAR;
   * leitura da partição do PRODES da UF;
   * cruzamento local com as outras fontes.

   Uma carteira de 500 imóveis sai em cerca de 20 minutos.
3. **O técnico abre a carteira** e atende de cima para baixo. A ficha diz o que fazer:
   * regularizar o CAR na secretaria estadual;
   * pedir ao IBAMA a revisão do embargo;
   * conferir no INCRA o limite do território quilombola;
   * e assim por diante.
4. **No atendimento**, o produtor traz o que falta (CCIR, SIGEF, relatório AB+S). Com o relatório AB+S, o resultado oficial entra ao lado de cada critério e alimenta a medida de acerto.
5. **No mês seguinte**, a carteira roda de novo, e o técnico vê só o que mudou.

## 5. O que agrega mais valor, em ordem

| # | Passo | Por que vem antes | Esforço |
|---|---|---|---|
| 1 | **Primeiro relatório AB+S real** e matriz de concordância | Sem ele, não há medida de acerto, só regressão; é o maior risco do projeto (README) | Depende de um produtor voluntário |
| 2 | ~~**Carteira com "o que mudou"**~~ (feito em 04/11/2026): comparar com a execução anterior de cada imóvel | É o que faz o técnico voltar todo mês, e a rotina mensal já existe | Pequeno |
| 3 | **Piloto com uma cooperativa** (café de MG, já na demonstração): uma carteira real, medindo o tempo de triagem contra a consulta separada a cada base | É a hipótese do projeto ("reduzir o tempo de triagem") | Médio, depende de parceiro |
| 4 | **Entrada do polígono da área de produção** (KML ou GeoJSON; feito em 05/11/2026, coluna `area_producao`) e dossiê EUDR (a fazer) | A EUDR exige a geolocalização da área, não do imóvel | Médio |
| 5 | **DETER da Amazônia e do Cerrado pelo arquivo diário**, como o Pantanal (feito em 04/11/2026, [ADR 0015](arquitetura/adr/0015-montar-o-prodes-e-o-deter-do-pantanal-pelo-arquivo-do-terrabrasilis.md), adendo) | Tirou a última fonte que dependia do WFS em partições mensais; o WFS ficou como queda quando o arquivo falha | Pequeno |
| 6 | **API sobre o banco lite** | O banco já existe e é gerado dos contratos (ADR 0017); falta a API e ligar um Neon ou Supabase gratuito quando houver mais de um técnico | Médio |
