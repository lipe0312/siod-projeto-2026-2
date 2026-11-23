# DESIGN.md — AgroValid

> Fonte de verdade visual das telas (console local, ficha, carteira, dossiê) para pessoas e agentes. **Vigente desde 23/11/2026** (issue #28, escolhas do dono na prancha). Mudou aqui → mude em `docs/marca/design-system/decisoes.md` e na prancha `docs/marca/design-system/preview-console.html` no mesmo PR. A escolha antiga vira alternativa, nunca é apagada.

## 0. De onde vem
- Marca: direção **C, Marca de ferro** (aprovada em 03/11/2026). Situações: **semáforo v3** (aprovado).
- Console: a prancha `preview-console.html` tem os 3 estilos (A Laudo, B Mesa de triagem, C Ferro e carimbo) e 3 opções por item, com a escolha do dono marcada como "Escolhida". Tudo pode mudar: mudar é editar a prancha e esta página primeiro.

## 1. Atmosfera
Ferramenta de campo, não app de startup. A linguagem vem do **couro** (sela, marca de ferro) e da **brasa** (o ferro quente): sóbria, quente, técnica. O técnico precisa saber em 3 segundos se o imóvel bloqueia crédito ou venda, e em seguida **o que fazer**. O **carimbo** é o gesto da marca.

## 2. Regras que nenhuma tela quebra
1. Situação sempre com **ícone + nome escrito**; cor nunca sozinha. Couro e brasa são da marca, nunca de situação.
2. Nunca "conforme". O melhor resultado é "sem pendência nas fontes verificadas"; "não verificado" fica separado do que foi encontrado (ADR 0013).
3. Toda afirmação leva fonte e data a um clique. Nenhum CPF/CNPJ na tela, na URL ou no log; só `documento_hash` encurtado.
4. Movimento **expressivo, mas com hora certa**: o carimbo e a contagem acontecem quando uma tela abre ou um resultado muda, nunca em laço nem ao rolar. `prefers-reduced-motion`: tudo chega ao estado final sem animar.
5. Projetor e sol: texto principal AAA, alvo de toque ≥ 44 px, 390 px sem rolagem horizontal, impressão legível em preto e branco.
6. Fora: folha, gradiente, verde vivo, azul de banco, glassmorphism, emoji como ícone, quatro cartões de KPI iguais, caixa alta espaçada, animação ao rolar.

## 3. Tokens
| Papel | Claro | Escuro |
|---|---|---|
| `--bg` fundo | `#ffffff` | `#1d1714` |
| `--sf` superfície | `#f7f4f1` | `#2a221e` |
| `--tx` texto | `#241914` (17,15:1) | `#f5f2f1` (15,91:1) |
| `--mu` apoio | `#5e534d` (7,45:1) | `#c9c0ba` (9,90:1) |
| `--ctl` contorno de controle | `#8a7f78` (3,90:1) | `#8a7d75` (4,45:1) |
| `--pri` botão principal | couro `#5c3621`, texto branco (10,48:1) | brasa `#f07c43`, texto `#160d09` (7,00:1) |
| `--lk` link | brasa `#ae4d15` (5,42:1) | `#bc896e` (5,86:1) |

Situações (ícone Lucide; claro / escuro): pendência `octagon-x` `#a51d14`/`#f0695e` · indício `triangle-alert` `#a86200`/`#f2b53a` · sem pendência `circle-check` `#2d7a47`/`#62c486` · inconclusivo `map-pin-off` `#2d4f8c`/`#8ea6ec` · não verificado `circle-dashed` `#6f655f`/`#a39a93`. Medidas em `docs/marca/design-system/situacoes.json`.

Tipo: **Zilla Slab** 600/700 em títulos e números grandes; **Source Sans 3** 400/600/700 no texto e nas tabelas, algarismos tabulares; mono (JetBrains Mono ou a do sistema) só para código do CAR, hash e comando. Todas OFL.

## 4. Console: escolhas de 23/11/2026
| # | Item | Escolha | Como fica | Alternativas (na prancha) |
|---|---|---|---|---|
| — | Estilo-base | **B · Mesa de triagem** | Ficha em duas colunas: à esquerda a fila (eixos crédito/EUDR, plano de ação, o que falta); à direita o painel de evidência (mapa, auditoria). J/K navega a fila, Enter abre. Abaixo de 960 px, uma coluna; na impressão, o formato do laudo (A) por CSS | A Laudo · C Ferro e carimbo |
| 1 | Botões | **C · Seta anda e sublinha** | Onde o botão leva a outra tela (abrir ficha, ver no mapa), a seta anda 4 px e um traço sublinha em 180 ms. Ação na mesma tela (Cruzar agora) afunda 1 px, como já era | A afunda 1 px · B couro preenche |
| 2 | Selo de situação | **B · Selo com o que bloqueia** | Ícone, nome e chips do impacto: `crédito`, `EUDR`, `conferir`, `falta AB+S`. Na ficha e na carteira | A selo v3 simples · C linha com contagem |
| 3 | Cartão de ação | **A · Trilho vertical de passos** | Um cartão por pendência; passos ligados por um trilho, cada um com quem age (técnico, produtor, órgão), órgão e link oficial; fonte e data no pé | B acordeão · C tarefas por responsável |
| 4 | Números da carteira | **C · Contagem que sobe ao abrir** | Números grandes em Zilla Slab por situação, sobem de 0 em 600 ms (ease-out) quando a carteira abre; cada número filtra a lista (#34) | A faixa única · B número herói + barra |
| 5 | Cruzamento ao vivo | **A · Lista de etapas com tempo** | Uma linha por fonte (SICAR, PRODES da UF, IBAMA, DETER, Lista Suja, áreas protegidas): girando → ✓ com o que achou e o tempo; a última leva à ficha | B trilho · C barra + frase |
| 6 | Veredito | **B · Carimbo** | Carimbo inclinado com o número de pendências (ou "sem pendência nas fontes verificadas") bate em 260 ms ao abrir a ficha e quando a rotina mensal muda o resultado. A frase de apoio e os eixos crédito/EUDR da mesa ficam ao lado | A frase · C dois eixos |
| 7 | Satélite antes/depois | **B · Lado a lado** | Dois mapas de mesma extensão, 2020 (corte da EUDR) e o mais recente, com as camadas e o zoom sincronizados; a data de cada imagem escrita; no celular, um sobre o outro. Provedor: decisão da #35 | A cortina · C alternador |
| 8 | Rastreabilidade | **C · Trilho de auditoria clicável** | Etapas fontes → SICAR → cruzamento → AB+S; cada uma abre suas linhas (fonte, data, carga, SHA-256, comando); etapa que falta fica tracejada. Na impressão vira lista | A gaveta · B recibo |
| 9 | Movimento | **C · Expressivo: carimbo e contagem** | Carimbo do veredito e contagem da carteira (acima), etapas do cruzamento girando. Nada em laço, nada ao rolar, tudo desligado com movimento reduzido | A só resposta ao clique · B cartões em sequência |
| 10 | Navegação | **Mistura de A, B e C** | **Abas no topo** trocam de tela (Carteira, Nova consulta, Fontes; traço de couro sob a ativa). **Trilho de ícones escuro** à esquerda do painel de evidência troca o que a mesa mostra (mapa, linha do tempo, auditoria), sempre com rótulo no foco e no hover. **Ctrl/⌘ K** abre a busca de comando ("CAR, produtor ou comando"), também como botão de busca na barra. No celular: abas viram barra de baixo, trilho vira abas do painel, busca vira botão | — |

## 5. Componentes
- Botão: canto 6 px, alvo 44 px; salvando = barra fina na base, `aria-busy`, mesmo tamanho; seta anda só onde leva a outra tela.
- Aba ativa: traço curto de couro (brasa no escuro) que desliza em 180 ms.
- Carimbo: 260 ms, borda de 3 px na cor do ícone da situação, inclinado −4°.
- Selo: v3 (fundo claro da situação, ícone cheio, texto escuro) + chips de impacto.
- Foco: contorno de 3 px afastado 2 px na cor `--fo`.
- Abaixo de 720 px a tabela da carteira vira lista.

## 6. Implementação no console
HTML gerado no servidor (`html.escape`), CSS com estes tokens em `console/estatico/base.css`, JS puro, sem React, Tailwind nem CDN de script (regra 8). O shadcn (MCP) serve de referência de estrutura e acessibilidade, nunca de instalação. Pipeline de tela: skill `ui-build`; conferência: `ui-verify` e `web-design-guidelines`; portão: `preview-aprovacao`.

## 7. Pendente para virar padrão
Telas reais da ficha e da carteira (#33, #34), provedor e mapa de satélite (#35), dossiê EUDR, estados de vazio e erro, impressão, kit de marca (`brand.py kit` do set C).
