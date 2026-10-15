# Combinar DETER e PRODES pela data da imagem e pela cobertura de cada bioma

## Context and Problem Statement

O recorte do projeto é café em Minas Gerais. Nos 10 municípios do recorte, 75,9% da área está no Cerrado e 24,1% na Mata Atlântica. O DETER cobre só a Amazônia e o Cerrado; o PRODES cobre todos os biomas, mas uma vez por ano. Em 13/10/2026, a última imagem do PRODES era de agosto a dezembro de 2025, conforme o bioma, e a do DETER, de 02/10/2026.

As duas fontes dizem coisas diferentes: o DETER é alerta, o PRODES é supressão consolidada. É preciso decidir qual vale em cada caso, como comparar com a data de corte da EUDR (31/12/2020) e o que mostrar quando nenhuma fonte cobre o período.

O teste mostrou três fatos (consulta em [`pipeline/fontes/inpe_prodes.py`](../../../pipeline/fontes/inpe_prodes.py), reproduzidos no caderno [`notebooks/02_fontes_antes_e_depois.ipynb`](../../../notebooks/02_fontes_antes_e_depois.ipynb), seção 6):
- O INPE recomenda comparar pela `image_date` (data da imagem que detectou a supressão). `publish_year` não é data de publicação: é sempre 01/01 do ano.
- No Cerrado de MG, nenhum polígono do ano 2021 em diante tem imagem de 2020. Mas a imagem é a data da detecção: o PRODES 2021 inclui a supressão ocorrida entre a imagem de 2020 e a de 2021, e 166 alertas DETER com imagem entre agosto e dezembro de 2020 caem em polígonos do PRODES 2021.
- De 2021 a 2025, o PRODES confirmou 69,6% dos alertas DETER do Cerrado de MG; 16,7% caíram em área já suprimida antes e 13,7% não foram confirmados.

## Considered Options

* Usar só o PRODES, filtrado por `year` ≥ 2021
* Usar só o DETER onde existe e o PRODES onde não existe
* Escada por bioma e data: PRODES quando publicado, DETER no período depois do último PRODES, DETER para datar o ano de 2021, e estado "sem cobertura" quando nenhuma fonte cobre

## Decision Outcome

Chosen option: "Escada por bioma e data", because é a única que não marca como limpo um período sem fonte e não marca como posterior ao corte uma supressão que o DETER registrou antes dele.

Regras, todas explícitas (sem ML):
1. Comparação com o corte pela `image_date` do PRODES e pela `view_date` do DETER, nunca pelo `year` ou pelo `publish_year`.
2. O alerta DETER é **confirmado** quando polígonos PRODES com imagem na mesma data ou depois cobrem ao menos 10% da sua área; **já suprimido antes** quando a cobertura vem de PRODES com imagem anterior; **não confirmado** quando o ano PRODES já foi publicado e não há cobertura; **não consolidado** quando o alerta é posterior ao último ano publicado.
3. Polígono do PRODES 2021 sobre alerta DETER com imagem até 31/12/2020 é exibido como indício de supressão anterior ao corte. Sem DETER (Mata Atlântica, Caatinga, Pampa, Pantanal), o PRODES 2021 fica com data incerta em relação ao corte, até o projeto ter o mapa Marco UE do INPE.
4. Em bioma sem DETER, o período depois da última imagem PRODES é exibido como "sem cobertura de [data] até hoje", nunca como "sem pendência".
5. A última imagem e a data de publicação de cada camada são lidas do próprio serviço a cada execução, não de notícia.

O limiar de 10% evita que um contato de borda entre polígonos de resoluções diferentes conte como confirmação. Ele não foi calibrado; é o ponto de partida para a comparação com o AB+S.

### Consequences

* Good, because o falso negativo mais perigoso (bioma sem fonte recente parecer limpo) vira um estado explícito.
* Good, because o alerta DETER sobre área já desmatada não é contado como desmatamento novo.
* Good, because cada estado exibido carrega fonte e data da imagem, e o usuário vê de onde veio a conclusão.
* Bad, because na Mata Atlântica, sem DETER, a supressão do PRODES 2021 continua sem data precisa em relação ao corte até o Marco UE ser incorporado. O Marco UE não está no WFS do TerraBrasilis.
* Bad, because o limiar de 10% é arbitrário; outro limiar muda a taxa de confirmação.
* Bad, because o projeto passa a depender de duas fontes do INPE com calendários diferentes, e cada nova publicação do PRODES muda a situação de alertas já classificados.
