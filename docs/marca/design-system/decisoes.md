# Design system do AgroValid: rascunho geral (03/11/2026)

Base: direção **C, Marca de ferro** (`docs/marca/preview.html`), escolhida pelo dono. Este é o rascunho geral. O objetivo final é virar padrão item a item, como no design system do CarroAberto: escolha vigente, alternativas e o porquê de cada uma. Tudo pode mudar.

Prévia local: `docs/marca/preview.html` (a de três direções foi guardada em `preview-direcoes.html`). Canvas com as pranchas (privado): https://claude.ai/artifact/3uvs5nSpdHyP7pn5HFqa55. Os arquivos-fonte ficam em `canvas/`.

## Regras
1. Couro e brasa são da marca, não do dado. Botão, logo e foco usam a marca; situação de imóvel nunca usa couro nem brasa.
2. Situação em vermelho, amarelo e verde no tom da marca, sempre com ícone e nome escrito.
3. O movimento só responde a quem agiu. O único gesto da marca é o carimbo, quando uma situação muda.

## Tokens
| Papel | Claro | Escuro |
|---|---|---|
| Fundo | `#ffffff` | `#1d1714` |
| Superfície | `#f7f4f1` | `#2a221e` |
| Texto | `#241914` (17,15:1) | `#f5f2f1` (15,91:1) |
| Texto de apoio | `#5e534d` (7,45:1) | `#c9c0ba` (9,90:1) |
| Contorno de controle | `#8a7f78` (3,90:1) | `#8a7d75` (4,45:1) |
| Botão principal | Couro `#5c3621`, texto branco (10,48:1) | Brasa `#f07c43`, texto `#160d09` (7,00:1) |
| Link | Brasa `#ae4d15` (5,42:1) | `#bc896e` (5,86:1) |

Tipo: Zilla Slab 600/700 nos títulos e números grandes; Source Sans 3 400/600/700 no texto e nas tabelas, com algarismos tabulares. As duas são OFL.

## Situações, v3 (semáforo)
A v1 (pílula colorida com ícone genérico) e a v2 (legenda de campo, só forma e cor) foram rejeitadas. A v3 usa vermelho, amarelo e verde no tom da marca, com ícone da Lucide (ISC) e nome escrito sempre. Selo: fundo claro da cor, ícone na cor cheia, texto escuro da mesma família.

| Situação | Ícone | Ícone claro | Ícone escuro |
|---|---|---|---|
| Pendência | octagon-x (parada) | `#a51d14` | `#f0695e` |
| Indício | triangle-alert | `#a86200` | `#f2b53a` |
| Sem pendência | circle-check | `#2d7a47` | `#62c486` |
| Inconclusivo | map-pin-off (falta localização) | `#2d4f8c` | `#8ea6ec` |
| Não verificado | circle-dashed | `#6f655f` | `#a39a93` |

Medido (`gerar/status_v3.py`, dados em `situacoes.json`): o ícone tem de 4,25 a 6,85:1 no selo claro e de 4,88 a 7,39:1 no escuro; o texto do selo fica acima de 7:1. A distância para as cores da marca é de pelo menos 10,9. A menor ΔE2000 entre ícones no claro é 22,7 em visão normal, 9,4 com protanopia, 8,6 com deuteranopia e 9,9 com tritanopia. No escuro é 24,1, 12,7, 9,0 e 3,8; o 3,8 é verde contra azul na tritanopia, separados pelo ícone e pelo nome. Vermelho, amarelo e verde se aproximam com daltonismo por natureza; por isso nenhuma situação depende só da cor.

## Componentes e movimento (vindos das escolhas do CarroAberto, adaptados)
- Botão com canto de 6 px; afunda 1 px ao apertar (120 ms); a seta anda só onde leva a outra tela (180 ms).
- Salvando: barra fina na base do botão, `aria-busy`, botão do mesmo tamanho.
- Aba ativa: traço curto de couro que desliza em 180 ms.
- Carimbo da situação: 260 ms, só quando a rotina mensal muda o resultado.
- Carteira: resumo numa faixa única com quatro células (ícone, nome, contagem, área), que filtram a tabela; busca; tabela com selo de situação. Abaixo de 720 px a tabela vira lista. No celular, tocar no imóvel mostra o primeiro passo.
- `prefers-reduced-motion`: tudo chega no estado final sem animar.

## Fora do sistema
Folha, gradiente, verde vivo, azul de banco; situação só por cor; barra colorida na lateral de linha; quatro cartões de KPI iguais; rótulo em caixa alta espaçada; animação de entrada ao rolar.

## Pendente para virar padrão
Ficha do imóvel, Mudanças do mês, dossiê EUDR, estados de vazio, carregando e erro, impressão em preto e branco, e o kit da marca (`brand.py kit` do set C) com logo final e tokens exportados.
