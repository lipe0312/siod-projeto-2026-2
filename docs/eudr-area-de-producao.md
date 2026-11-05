# EUDR: área de produção, imóvel inteiro e o que comprova cada um

Pesquisa de 05/11/2026 para a #5 (área de produção na carteira) e a #6 (dossiê EUDR). A decisão de projeto que sai daqui está no [ADR 0018](arquitetura/adr/0018-cruzar-o-desmatamento-na-area-declarada-e-a-legalidade-no-imovel-inteiro.md). Fonte principal: o [FAQ da Comissão Europeia, 5ª versão, de 30/04/2026](https://environment.ec.europa.eu/document/download/744919a7-8650-4850-89ad-a597268cd69e_en?filename=FAQ-UPDATE-5th-Iteration+FINAL.pdf), perguntas 1.1, 1.6 a 1.18. Os números entre parênteses abaixo são perguntas desse FAQ.

## 1. Área de produção ou fazenda inteira

As duas importam, cada uma para um requisito diferente do [Regulamento (UE) 2023/1115](https://eur-lex.europa.eu/eli/reg/2023/1115/oj).

| Requisito da EUDR | Onde é verificado | Base |
|---|---|---|
| **Livre de desmatamento** depois de 31/12/2020 | Só na **parcela declarada** (*plot of land*) | art. 2(27), art. 9(1)(d); FAQ 1.15 |
| **Legalidade** pela lei do país de produção (uso da terra, Código Florestal, embargo, trabalho, terras indígenas) | No **imóvel inteiro** | art. 2(40); FAQ 1.15 (iii) |
| **Gado** | Um ponto por estabelecimento onde o animal esteve, sem polígono | art. 2(29); FAQ 1.8 |

A parcela é "terra dentro de um único imóvel, reconhecido pela lei do país de produção, com condições homogêneas o bastante para avaliar o risco de desmatamento em conjunto" (art. 2(27)). Ela pode ser o imóvel inteiro, se for homogêneo, ou só a parte cultivada (1.15).

O exemplo do FAQ (1.15), com um imóvel A, uma área B de soja e uma área C desmatada depois de 2020:

1. **C foi desmatada legalmente e não produz soja.** A soja de B continua conforme, desde que só B seja declarada.
2. **C produz outra commodity (gado).** O gado de C não é conforme; a soja de B continua conforme se só B for declarada.
3. **B e C produzem soja.** O importador precisa demonstrar risco desprezível de mistura dentro do imóvel (art. 10(2)(j)).
4. **O desmatamento em C é ilegal.** A soja de B **também deixa de ser conforme**, porque a legalidade vale para o imóvel inteiro.

Consequências práticas:
- **Declarar a fazenda inteira "por precaução" é um erro.** Qualquer desmatamento numa parcela declarada desqualifica tudo o que sai dela (art. 9(1)(d)). Declare só onde a commodity foi produzida (1.18 só admite declarar a mais em cadeia a granel totalmente rastreada).
- **Um polígono por parcela, contígua ou não** (1.14). Um polígono não pode contornar uma área que só em parte é parcela.
- **Sem cadastro fundiário, a parcela ainda vale.** A EUDR aceita a terra usada de fato como parcela (1.6, 1.10); se a lei brasileira não exige título para produzir e vender, a EUDR também não exige.

## 2. Como a área de produção é demarcada

No Brasil não existe cadastro oficial de "área de produção". O CAR e o SIGEF registram o perímetro do imóvel, não da lavoura. Quem desenha o polígono é o produtor, a cooperativa ou o comprador. O FAQ (1.1) aceita celular, receptor GNSS de mão e aplicativos de mapa gratuitos, sem precisar de sinal de celular.

| Método | Como funciona | Observação |
|---|---|---|
| Andar o perímetro com GPS | Celular com QField, SW Maps ou Avenza, ou receptor GNSS | Barato e em campo. Erro de 3 a 10 m no celular |
| Desenhar sobre imagem de satélite | Google Earth ou QGIS, partindo do polígono do CAR | O mais comum em cooperativa. Depende de a imagem estar atualizada |
| Mapas de talhão da agricultura de precisão | Mapas de plantio e colheita das máquinas, ou ortofoto de drone | Muito preciso. Comum em soja, raro em café de pequeno produtor |
| Camadas que o próprio produtor declarou no CAR | Uso consolidado × vegetação nativa | Ponto de partida, mas o CAR foi declarado anos atrás e às vezes não bate com a realidade |

### Regras do formato

- WGS 84 (EPSG 4326), latitude e longitude com pelo menos 6 casas decimais (1.1).
- Polígono obrigatório acima de 4 ha; até 4 ha, aceita um ponto (1.8). Não há tamanho mínimo nem máximo, desde que a parcela seja homogênea (1.7).
- Um polígono por parcela (1.14). Não vale um polígono que cubra áreas com e sem produção.
- Não pode ser um ponto com raio (1.16).
- Na rotação de culturas, pode declarar mais de uma parcela (1.15, 1.18).
- A declaração inteira enviada ao sistema de informação da UE tem no máximo 25 MB (1.7).

## 3. O que comprova

**Nenhum documento certifica a área de produção.** O importador europeu pode usar o polígono do produtor, mas responde pela exatidão dele (1.11) e precisa "verificar e conseguir provar" que ele está certo (1.12). O produtor brasileiro não tem obrigação direta, a menos que ele mesmo venda para a UE (1.1, 1.11). Na prática, a prova é a coerência entre evidências:

1. **O polígono cai dentro do imóvel do CAR.** A carteira já avisa quando a área está fora ou mais de 5% fora (#5).
2. **A imagem de satélite mostra a cultura ali**, e a cobertura em 31/12/2020 já não era floresta. O FAQ cita imagem de satélite, foto aérea e foto de campo com localização e data (1.1).
3. **O volume vendido é plausível** para a área multiplicada pela produtividade da região. Se a nota fiscal soma 300 t de café numa área de 10 ha, ou o polígono está errado ou houve mistura.
4. **Documentos do imóvel, para a legalidade:** recibo do CAR, CCIR e SIGEF, certidão negativa de embargo, ausência na Lista Suja, licenças e, no gado, a GTA. O CAR é declaratório e não substitui o documento fundiário ([STCP](https://www.stcp.com.br/cinco-lacunas-documentais-recorrentes-em-diagnosticos-de-due-diligence-para-a-eudr-no-brasil/)).

## 4. O que isso muda na AgroValid

| Onde | Antes (#5) | Depois |
|---|---|---|
| Ficha com `area_producao` | DETER e PRODES cruzados só com a área de produção. O desmatamento no resto do imóvel **sumia da ficha** | Duas linhas: "desmatamento na área declarada" (reprova pela EUDR) e "desmatamento no resto do imóvel" (risco de legalidade e de mistura). Escopo da #6 |
| Embargo, terra indígena, quilombola, unidade de conservação, Lista Suja | Cruzados com o CAR inteiro | Sem mudança: já é o certo, porque são critérios de legalidade |
| Dossiê EUDR (#6) | A fazer | Declara só a área de produção; diz quando usou o imóvel inteiro; marca o polígono como "declarado pelo produtor", nunca "comprovado"; leva o desmatamento do resto do imóvel em "o que não foi verificado" ou em risco |
| Orientação ao técnico | "polígono da área de produção, quando não for o imóvel inteiro" | Não declarar a fazenda inteira por precaução; um polígono por parcela; parcela até 4 ha pode ser ponto |

**Fica para depois** (ainda sem issue):
- Conferir se o volume vendido cabe na área declarada (item 3.3).
- Gado: um ponto por estabelecimento e a cadeia de GTA. A carteira hoje só trata polígono de lavoura.
- Shapefile na coluna `area_producao` (hoje só KML e GeoJSON).

## Fontes

Consultadas em 05/11/2026.

- Comissão Europeia. [Frequently Asked Questions — Implementation of the EU Deforestation Regulation, 5ª versão (30/04/2026)](https://environment.ec.europa.eu/document/download/744919a7-8650-4850-89ad-a597268cd69e_en?filename=FAQ-UPDATE-5th-Iteration+FINAL.pdf). Perguntas 1.1, 1.6 a 1.18.
- Comissão Europeia. [FAQ EUDR, versão de março de 2024](https://www.eeas.europa.eu/sites/default/files/documents/2024/240314_EN_FAQ%20EUDR%20(1)_0.pdf).
- União Europeia. [Regulamento (UE) 2023/1115](https://eur-lex.europa.eu/eli/reg/2023/1115/oj). Art. 2(27), 2(28), 2(29), 2(40), 9(1)(d), 10(2)(j).
- Coolset. [EUDR geolocation requirements](https://www.coolset.com/academy/eudr-geolocation-requirements-how-to-collect-and-validate-gps-polygon-data-for-your-dds).
- eudrguide.com. [EUDR Geolocation: points, polygons, 4 ha rule](https://eudrguide.com/compliance/geolocation/).
- STCP. [Cinco lacunas documentais recorrentes em diagnósticos de due diligence para a EUDR no Brasil](https://www.stcp.com.br/cinco-lacunas-documentais-recorrentes-em-diagnosticos-de-due-diligence-para-a-eudr-no-brasil/).
- Agrotools. [EUDR 2026: o que exige do agro brasileiro](https://agrotools.com.br/blog/esg-sustentabilidade/eudr-2026-o-que-e-o-que-mudou-e-o-que-o-regulamento-exige-do-agro-brasileiro/).
- Imaflora. [EUDR e a nova conformidade ambiental para exportação](https://imaflora.org/noticias/eudr-e-a-nova-conformidade-ambiental-para-exportacao).

As tabelas de métodos de demarcação e o erro do GPS de celular são síntese prática da pesquisa, não texto do FAQ.
