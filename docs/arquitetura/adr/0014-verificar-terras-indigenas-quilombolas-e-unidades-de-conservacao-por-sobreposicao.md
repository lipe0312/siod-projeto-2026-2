# Verificar terras indígenas, quilombolas e unidades de conservação por sobreposição

## Context and Problem Statement

Até 30/10/2026, o pré-diagnóstico mostrava 6 dos 9 critérios do AB+S como "não verificado". A pesquisa desse dia ([`atividade-04-prediagnostico.md`](../../atividade-04-prediagnostico.md), seção 5) testou uma fonte aberta para cada critério. As que respondem sem login são:

* **critério 5:** FUNAI, WFS `Funai:tis_poligonais`;
* **critério 9:** MMA, CNUC em shapefile;
* **critério 6:** IBGE, territórios quilombolas do Censo 2022.

O acervo fundiário do INCRA, que publicaria o SIGEF (critérios 2 e 8) e as áreas quilombolas, não tem endereço público: `certificacao.incra.gov.br` e `acervofundiario.incra.gov.br` não resolvem nem em DNS público, e o acervo passou a exigir login gov.br. A consulta pública do SNCR (critério 1) tem hCaptcha.

É preciso decidir como guardar essas camadas e como transformar a sobreposição com o CAR em situação do critério.

## Considered Options

* Consultar cada camada sob demanda, no retângulo do imóvel
* Guardar as três camadas nacionais em lote (Parquet) e cruzar localmente com o polígono do CAR

## Decision Outcome

Chosen option: "Guardar as três camadas nacionais em lote", because são pequenas e mudam pouco, e o serviço da FUNAI recusa o pedido sem `count` e a contagem (`resultType=hits`). Isso torna frágil a consulta por retângulo. Tamanhos em 30/10/2026:

| Camada | Feições |
|---|---:|
| FUNAI | 665 |
| CNUC | 3.301 (3.121 polígonos e 180 pontos) |
| IBGE | 495 |

Guardar as três não custa nada: são arquivos Parquet em `data/processed/`, como as outras fontes ([ADR 0011](0011-persistir-em-parquet-por-uf-e-adiar-o-postgis.md)).

Regras:
1. **Fontes:** `python -m pipeline --fontes terras_indigenas unidades_conservacao quilombolas`, com as validações de cada uma e a procedência no relatório:
   * FUNAI: a cadeia de certificado é completada pelo endereço AIA, com a verificação ligada;
   * CNUC: o recurso é escolhido pelo CKAN, o último shapefile com endereço em `dados.mma.gov.br`;
   * IBGE: zip do Censo 2022.
2. **Sobreposição** pela fração do CAR, não pela fração do objeto, porque a área protegida é muito maior que o imóvel.
   * Conta se atinge ao menos 5% do CAR ou se a faixa comum tem mais de 30 m.
   * Abaixo disso, é "tangente" (contato de borda, diferença de desenho) e não conta.
   * Ponto do CNUC (UC sem limite) dentro do CAR conta como indício.
3. **Situação:**
   * Terra indígena: pendência; "Em Estudo" = indício.
   * Quilombola: pendência; "Estudo técnico" = indício.
   * Unidade de conservação: pendência na proteção integral e nas de domínio público (Floresta, RESEX, RDS, Reserva de Fauna). Indício em APA, ARIE e RPPN, que admitem propriedade privada, e em polígono esquemático.
4. **A base quilombola do IBGE é de 31/07/2022.** A ficha cita a data, e o critério fica "parcial" na tabela do AB+S, porque o AB+S consulta o INCRA.
5. **Fonte não carregada** (parquet ausente) deixa o critério inconclusivo, nunca "sem ocorrência".
6. **Critérios 1, 2 e 8** continuam "não verificado", com o motivo atualizado em `ab_s.CRITERIOS`.

### Consequences

* Good, because o pré-diagnóstico passa de 3 para 6 critérios do AB+S verificados (um deles parcial). Ficam 3 sem fonte aberta.
* Good, because a demonstração tem casos reais de cada situação: TI declarada (MS), quilombo (PA), APA (MG) e parque estadual (MG).
* Bad, because o shapefile mais novo do CNUC (2026_07) só está num link do SharePoint; o lote usa o 2025_08 até o MMA publicá-lo no portal.
* Bad, because a base quilombola está parada em 2022. Um território delimitado depois disso não aparece.
* Bad, because 143 das 665 terras indígenas não têm data de atualização na FUNAI.
