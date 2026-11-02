# Usar a base quilombola do INCRA republicada pelo CMR/FUNAI

## Context and Problem Statement

O critério 6 do AB+S (área quilombola) consulta o INCRA. Desde o [ADR 0014](0014-verificar-terras-indigenas-quilombolas-e-unidades-de-conservacao-por-sobreposicao.md), o pré-diagnóstico usa a base do IBGE, parada em 31/07/2022, porque o acervo fundiário do INCRA não tem endereço público. Em 02/11/2026, de uma máquina no Brasil (ipinfo: BR), a situação era esta:

* `certificacao.incra.gov.br`, `acervofundiario.incra.gov.br` e `geoserver.incra.gov.br` continuam sem DNS. A hipótese "não respondem de fora do Brasil" está descartada.
* `sigef.incra.gov.br` responde, mas a consulta de parcelas devolve "Request Rejected" e exige login gov.br.

O GeoServer do CMR/FUNAI (`cmr.funai.gov.br/geoserver/ows`, encontrado no pacote `agrobr` do projeto) republica camadas do INCRA sem login:

| Camada | Feições | Recorte (testado) |
|---|---:|---|
| `CMR-PUBLICO:lim_quilombolas_a` | 446 | **Nacional**: só 4 tocam terra indígena; cadastro de 28/10/2026; traz processo, superintendência e fase |
| `CMR-PUBLICO:lim_assentamento_rural_a` | 7.484 | Assentamentos do INCRA (fora do AB+S) |
| `CMR-PUBLICO:vw_lim_imovel_certificado_sigef_privado_a` | 2.334 | **Só em volta de terra indígena**: 2.329 tocam uma TI, e todas estão a menos de 10 km de uma |
| `..._sigef_publico_a`, `..._certificado_privado_a`, `..._certificado_publico_a` | 473, 610, 154 | Mesmo recorte |

Comparada com a do IBGE, a base do INCRA cobre 401 dos 495 territórios. Traz também 37 áreas que o IBGE não tem: 22 em fase de RTID, 14 sem fase informada e 1 com a fase "INCRA".

## Considered Options

* Manter só o IBGE 2022
* Trocar o IBGE pelo INCRA
* Combinar: o INCRA inteiro, mais o território do IBGE que o INCRA não cobre

## Decision Outcome

Chosen option: "Combinar", because o INCRA é a base do AB+S e é mais nova, mas não cobre 94 territórios do IBGE. A camada combinada (`data/processed/quilombolas.parquet`, `pipeline/fontes/incra_quilombolas.py`) tem 540 áreas: 446 do INCRA e 94 só do IBGE.

Regras:
1. **Mesmo território nas duas bases:** se ao menos 50% da área do território do IBGE está coberta pelo INCRA, fica a versão do INCRA.
2. **Situação:**
   * pendência: RTID, portaria, decreto, título, título parcial e CCDRU;
   * indício: "estudo técnico" (IBGE), "título anulado" e fase em branco;
   * cada achado diz a base de onde veio.
3. **`python -m pipeline --fontes quilombolas`** roda o IBGE, depois o INCRA, depois a combinação. Sem o IBGE, a combinação interrompe a fonte.
4. **O SIGEF do CMR não entra nos critérios 2 e 8.** É um recorte em volta de terras indígenas. Usá-lo daria "sem sobreposição" falso para quase todo imóvel. Os critérios continuam "não verificado".

### Consequences

* Good, because o critério 6 passa a usar a base que o AB+S consulta, atualizada em 28/10/2026. O caso de Santarém (PA) mostra o território Saracura com a fase do INCRA (portaria) em vez da situação de 2022.
* Good, because 37 áreas recentes, sobretudo em fase de RTID, passam a ser verificadas.
* Bad, because a base depende de um espelho mantido pela FUNAI, não pelo INCRA. Se o espelho sair do ar, a fonte falha e o critério fica inconclusivo, nunca "sem ocorrência" (ADR 0013).
* Bad, because os critérios 1, 2 e 8 continuam sem fonte aberta: o SNCR tem captcha e o SIGEF nacional exige login gov.br. A saída prevista é o produtor trazer o CCIR e o número da certificação SIGEF no atendimento.
