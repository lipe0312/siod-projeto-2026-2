# Roteiro da demonstração final (26/11/2026)

Demonstração de 8 a 10 minutos do console local do AgroValid. A cooperativa é a **Cooperativa Vale do Cerrado (demonstração)**, com 12 imóveis `CVC-01` a `CVC-12` ([tabela caso → situação](../evidencias/entrega-final/LEIA-ME.md)). Os nomes, os ids e as commodities são fictícios; os CARs são públicos e reais. Nenhum CPF ou CNPJ aparece na tela, na planilha ou neste roteiro: o documento de demonstração do pipeline entra só em memória e só é gravado pseudonimizado.

**Hipótese a deixar clara:** para cada imóvel, o técnico sabe a **causa** de cada pendência, a **fonte** (com data) e chega a isso em **poucos minutos**, sem abrir cada base pública. O tempo medido de cada consulta aparece na tela ("Tempo total medido").

## Tempo estimado por bloco

Estimativa de planejamento, não medida: o ensaio cronometrado é do dono (tabela no fim).

| # | Bloco | Estimado |
|---|---|---|
| 1 | Problema | 1:00 |
| 2 | Carteira da cooperativa | 1:45 |
| 3 | Ficha 1: pendência com plano de ação (CVC-05) | 1:30 |
| 4 | Ficha 2: indício e mapa (CVC-03) | 1:30 |
| 5 | Ficha 3: o que falta (CVC-06) | 1:00 |
| 6 | Consulta ao vivo de um CAR | 1:00 |
| 7 | Rastreabilidade | 0:30 |
| 8 | Limites | 0:45 |
| | **Total** | **9:00** |

## As 3 fichas e por quê

| Ficha | Caso | Por que esta |
|---|---|---|
| Pendência com plano de ação | CVC-05, Fazenda Três Barras (demonstração), Patrocínio/MG | É o caso mais pesado do café: embargo do IBAMA (2 TAD) e desmatamento após 31/12/2020 confirmado (DETER e PRODES), mais o CAR com notificação como indício. Mostra causa, fonte e o plano de ação com quem faz o quê. |
| Indício | CVC-03, Fazenda Alto do Cerrado (demonstração), Patrocínio/MG | Tem talhão desenhado sobre os alertas DETER (ainda sem PRODES): o indício cai na área de produção e o técnico confere no mapa de satélite antes e depois. Também mostra a separação "área de produção × resto do imóvel". |
| O que falta | CVC-06, Sítio Água Limpa (demonstração), Patrocínio/MG | Imóvel sem achado nas fontes, com documento informado. É o caso que prova o limite: mesmo sem pendência, a ficha lista o que não foi verificado e o sistema não diz "conforme". |

Reserva: CVC-07 (coordenada com latitude e longitude trocadas) não gera ficha; aparece na carteira como "inconclusivo" com o motivo e serve de recurso no plano B.

## Antes de entrar na sala

Ver o [checklist da véspera](#checklist-da-véspera). Com tudo pronto: terminal na raiz do repositório, console em `http://127.0.0.1:8765`, uma aba na carteira.

## Passo a passo

### 1. Problema (1:00)

- **Fazer:** nenhuma tela; ou deixar a carteira aberta ao fundo.
- **Dizer:** a cooperativa tem dezenas de imóveis e cada triagem exige abrir embargos, alertas de desmatamento, Lista Suja, terras indígenas, quilombolas, unidades de conservação e o SICAR, um por um. A EUDR veda desmatamento após 31/12/2020, mesmo autorizado, e o crédito rural veda embargo ativo. O AgroValid faz o pré-diagnóstico sobre dados públicos.
- **Destacar:** é pré-diagnóstico com evidência, não atestado.

### 2. Carteira da cooperativa (1:45)

- **Fazer:** abrir `http://127.0.0.1:8765` (a raiz abre a carteira).
- **Caso:** os 12 imóveis da cooperativa, em ordem de prioridade.
- **Destacar:** os contadores por situação (7 com pendência, 3 com indício, 1 inconclusivo, 1 sem pendência nas fontes verificadas) com a área de cada grupo; clicar em um contador filtra a lista; os chips Café, Gado e "Falta dado"; a faixa "Fontes" com a idade de cada fonte; a coluna "Primeiro passo" e "A tratar". Mostrar a linha de CVC-07: **inconclusivo, com o motivo** ("lat/lon fora do Brasil (conferir se não estão trocados)"), sem ficha.
- **Dizer:** a lista já vem ordenada; o que não deu para consultar não some nem vira "limpo".

### 3. Ficha 1: pendência com plano de ação, CVC-05 (1:30)

- **Fazer:** na carteira, clicar na linha de CVC-05 (prioridade 1) e abrir a ficha.
- **Destacar:** o veredito no topo ("com pendência"); nos cartões do plano de ação, **Embargo IBAMA** (TAD 2X4MM2H9 e TAD GIPXHOIX, fonte IBAMA, 03/11/2026) e **Desmatamento após 31/12/2020 (EUDR)** (alertas DETER e polígonos PRODES, fonte INPE); em cada cartão o "por quê" com a norma, quem faz o quê (técnico, produtor, órgão), o órgão com link e o que bloqueia (crédito rural, EUDR). O CAR com notificação aparece como indício.
- **Dizer:** causa identificada, fonte e data na mesma tela; o técnico sai com o que fazer, não só com um alerta.

### 4. Ficha 2: indício e mapa, CVC-03 (1:30)

- **Fazer:** voltar à carteira e abrir CVC-03; rolar até o mapa de satélite.
- **Destacar:** o indício "Desmatamento após 31/12/2020 (EUDR)" na **área de produção** (3 alertas DETER aguardando consolidação, talhão de 78,4 ha) e o indício separado "no resto do imóvel" (1 alerta, 0,6 ha); o mapa mostra 2020 (corte da EUDR) e 2025 lado a lado, com as camadas do talhão e dos alertas; "Ver no mapa" num cartão do plano centraliza a evidência.
- **Dizer:** indício não é pendência: o alerta ainda não foi confirmado pelo PRODES, então o plano manda conferir em imagem e com o produtor.
- **Se estiver sem rede:** o mapa de satélite não carrega e a ficha volta ao mapa SVG com o aviso "Imagem de satélite indisponível". Seguir o roteiro (ver plano B).

### 5. Ficha 3: o que falta, CVC-06 (1:00)

- **Fazer:** voltar à carteira e abrir CVC-06; rolar até "O que falta para fechar o diagnóstico".
- **Destacar:** o veredito é "sem pendência nas fontes verificadas" (não "conforme"); a Lista Suja foi verificada porque o documento foi informado; a tabela "O que falta" lista o relatório do AgroBrasil+Sustentável do produtor (critérios 1, 2 e 8) e a área de produção (talhão), com quem traz e onde obter. Em fichas com documento ausente (por exemplo CVC-03), o botão **Informar agora** leva à consulta com o CAR já preenchido.
- **Dizer:** o limite do sistema: o que não foi verificado fica escrito.

### 6. Consulta ao vivo de um CAR (1:00)

- **Fazer:** aba **Consulta**; digitar o CAR de CVC-02 (Sítio Boa Safra, Serra do Salitre/MG: `MG-3166808-A726F93D7AFF4A0883BFDEA10D64B1F4`), opcionalmente o documento de demonstração, e clicar em **Cruzar agora**.
- **Destacar:** as fontes aparecendo uma por linha (SICAR, PRODES da UF, IBAMA, DETER, Lista Suja, Áreas protegidas) e o "Tempo total medido" ao final; depois abrir a ficha gerada.
- **Dizer:** é o mesmo cruzamento da carteira, imóvel a imóvel. A resposta do SICAR fica em cache local (`data/raw/sicar/`), por isso este CAR responde também sem rede; um CAR fora do cache exige o SICAR no ar.

### 7. Rastreabilidade (0:30)

- **Fazer:** na ficha aberta, expandir o bloco **Rastreabilidade** (vem recolhido).
- **Destacar:** execução, fontes com data, carga, SHA-256 e o comando que refaz.
- **Dizer:** cada evidência liga ao registro e à carga da fonte; dá para refazer e auditar. O documento só existe como `documento_hash`.

### 8. Limites (0:45)

- **Fazer:** nenhuma tela nova (ou o botão Imprimir, que gera a ficha em preto e branco).
- **Dizer:**
  - O sistema **nunca diz "conforme"**: o melhor resultado é "sem pendência nas fontes verificadas".
  - Dado incompleto vira **inconclusivo com motivo** (CVC-07), nunca "sem ocorrência" (ADR 0013).
  - O **AB+S** (relatório AgroBrasil+Sustentável do produtor) é o gabarito para conferir o pré-diagnóstico (ADR 0012) e continua **pendente**: depende do relatório do produtor.
  - Não há caso positivo de Lista Suja na demonstração: exigiria o documento de uma pessoa real.
  - Os critérios fundiários (1, 2 e 8) ficam "não verificado" até o AB+S entrar.

## Plano B (offline)

Tudo da demonstração é pré-gerado e roda sem rede.

| Se acontecer | Faça | Diga |
|---|---|---|
| Sem rede | Seguir o roteiro. O mapa de satélite some e fica o mapa SVG com o aviso. A carteira, as fichas e a consulta de CARs em cache funcionam. | "O mapa SVG é o mesmo dado; o satélite é só conferência visual." |
| SICAR fora do ar na consulta ao vivo (bloco 6) | Deixar a consulta terminar: a ficha sai **inconclusiva com o motivo** ("SICAR fora do ar ou sem resposta agora; a consulta não foi concluída"). Voltar a CVC-07 na carteira como segundo exemplo. | "Quando a fonte cai, o sistema não chuta: diz que não concluiu e por quê. Isso é o recurso, não a falha." |
| Consulta ao vivo travou | Pular para o bloco 7 usando a ficha de CVC-02 já gravada na carteira. | "Esta é a ficha que a mesma consulta gerou na carteira." |
| Console não sobe | Abrir `data/saidas/console/demonstracao/carteira.html` e as fichas `.html` da pasta `fichas/` direto no navegador (estáticos). | "Mesmo conteúdo, sem o console." |
| Carteira vazia | Rodar `.venv/bin/python docs/evidencias/entrega-final/01_cooperativa_demonstracao.py` (cerca de 18 s) e recarregar. | |

## Checklist da véspera

- [ ] Na raiz do repositório, com o `.venv`: `git status` limpo e a `main` atualizada.
- [ ] Gerar a demonstração: `.venv/bin/python docs/evidencias/entrega-final/01_cooperativa_demonstracao.py`. Esperado ao fim: 12 imóveis (7 com pendência, 3 com indício, 1 inconclusivo, 1 sem pendência nas fontes verificadas) e a tabela do [LEIA-ME](../evidencias/entrega-final/LEIA-ME.md) igual à deste roteiro.
- [ ] Abrir o console: `.venv/bin/python -m console` e `http://127.0.0.1:8765`; a carteira mostra os 12 imóveis e a idade das fontes.
- [ ] Abrir as fichas de CVC-05, CVC-03 e CVC-06; conferir os cartões, o mapa e o "O que falta".
- [ ] Consultar na tela o CAR de CVC-02 uma vez e anotar o tempo medido.
- [ ] **Testar sem rede** (Wi-Fi desligado): recarregar a carteira, abrir CVC-03 (mapa SVG com aviso) e repetir a consulta de CVC-02.
- [ ] Confirmar que nada com CPF ou CNPJ está visível (campo documento vazio ou com o documento de demonstração, sem imprimir).
- [ ] Deixar abertas as abas: carteira, consulta, e o `carteira.html` estático como reserva. Fechar notificações e ampliar a fonte do navegador.
- [ ] Levar este roteiro impresso e o [LEIA-ME das evidências](../evidencias/entrega-final/LEIA-ME.md).

## Ensaio cronometrado (preencher)

| Bloco | Estimado | Medido | Notas |
|---|---|---|---|
| 1 Problema | 1:00 | | |
| 2 Carteira | 1:45 | | |
| 3 Ficha CVC-05 | 1:30 | | |
| 4 Ficha CVC-03 | 1:30 | | |
| 5 Ficha CVC-06 | 1:00 | | |
| 6 Consulta ao vivo | 1:00 | | |
| 7 Rastreabilidade | 0:30 | | |
| 8 Limites | 0:45 | | |
| **Total** | **9:00** | | |

Data do ensaio: ____ · Rede: com / sem · Resultado a anotar como comentário na issue #36.
