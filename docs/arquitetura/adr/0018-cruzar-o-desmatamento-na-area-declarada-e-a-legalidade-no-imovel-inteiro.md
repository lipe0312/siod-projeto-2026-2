# Cruzar o desmatamento na área declarada e a legalidade no imóvel inteiro

Situação: **decidido em 05/11/2026**. Complementa a #5 (coluna `area_producao`) e entra no escopo da #6 (dossiê EUDR). Pesquisa completa em [`docs/eudr-area-de-producao.md`](../../eudr-area-de-producao.md).

## Context and Problem Statement

Desde a #5, quando a planilha traz `area_producao`, o DETER e o PRODES são cruzados só com esse polígono. Embargo, terras indígenas, quilombolas, unidades de conservação e Lista Suja continuam no imóvel inteiro do CAR. Com isso, o desmatamento no resto do imóvel deixa de aparecer na ficha.

O [FAQ da Comissão Europeia, 5ª versão](https://environment.ec.europa.eu/document/download/744919a7-8650-4850-89ad-a597268cd69e_en?filename=FAQ-UPDATE-5th-Iteration+FINAL.pdf), pergunta 1.15, separa os dois requisitos: a ausência de desmatamento vale para a parcela declarada (art. 9(1)(d)), e a legalidade vale para o imóvel inteiro (art. 2(40)). Um desmatamento ilegal fora da área de produção torna não conforme a commodity que sai dela. E, se a mesma commodity é produzida fora da área declarada, há risco de mistura (art. 10(2)(j)).

## Considered Options

* Cruzar o desmatamento só com a área de produção (como ficou na #5)
* Cruzar o desmatamento só com o imóvel inteiro (ignorar a área de produção)
* Cruzar com os dois e mostrar separado: na área declarada e no resto do imóvel

## Decision Outcome

Chosen option: "Cruzar com os dois e mostrar separado", because é a única que segue o FAQ nos dois requisitos sem esconder evidência do técnico.

Regras:
* **Desmatamento na área declarada** depois de 31/12/2020: é o critério da EUDR, decide o resultado do critério de desmatamento.
* **Desmatamento no resto do imóvel** depois de 31/12/2020: aparece como linha própria, com fonte e data, como risco de legalidade (conferir autorização de supressão) e de mistura (a mesma commodity produzida ali). Nunca fica oculto.
* Embargo, terras indígenas, quilombolas, unidades de conservação e Lista Suja continuam no imóvel inteiro.
* O polígono da área de produção é sempre "declarado pelo produtor". O sistema não diz que ele está comprovado (o importador responde pela verificação, FAQ 1.11 e 1.12).
* Sem `area_producao`, nada muda: o cruzamento é com o imóvel inteiro, e a ficha diz isso.

### Consequences

* Good, because o técnico vê o desmatamento que pode reprovar o lote pela legalidade, mesmo fora da lavoura.
* Good, because o dossiê da #6 pode declarar só a área de produção, que é o que o FAQ recomenda, sem perder a evidência do resto.
* Bad, because o critério de desmatamento fica com duas leituras, e o resultado geral precisa de regra clara para o "resto do imóvel" (indício, não pendência, enquanto não houver dado de autorização de supressão).
* Bad, because cada imóvel com área de produção faz dois cruzamentos de DETER e PRODES; o custo é pequeno, porque o recorte por imóvel já está carregado.
