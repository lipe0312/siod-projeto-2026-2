# Conferir o pré-diagnóstico com o relatório AB+S do imóvel

## Context and Problem Statement

A página da demonstração (Atividade 04) confere 6 CARs reais com um resultado esperado escrito pelo próprio autor depois de olhar as mesmas fontes que o pipeline usa. Isso é teste de regressão, não medida de acerto: em 30/10/2026, o esperado de Serra do Salitre foi reescrito quando o PRODES Cerrado 2026 saiu. É preciso um gabarito que não venha do próprio pipeline.

O AgroBrasil+Sustentável (AB+S) é a qualificação oficial do MAPA e já está como referência no [ADR 0008](0008-usar-o-ab-s-como-referencia-sem-declarar-conformidade.md). A API pública confirma um relatório pelo código de autenticidade (UUID). O relatório só é emitido pelo titular do imóvel, com o login gov.br dele e o imóvel no SNCR.

## Considered Options

* Gabarito escrito pelo autor (situação atual)
* Revisão dos casos por um técnico
* Cruzamento primeiro, depois conferência com o relatório AB+S do mesmo imóvel, usado como gabarito

## Decision Outcome

Chosen option: "Cruzamento primeiro, depois conferência com o relatório AB+S", because é o único gabarito oficial, externo ao projeto e com o mesmo recorte de critérios. A revisão de um técnico continua útil para a causa e o encaminhamento, que o AB+S não traz.

Fluxo:
1. O pré-diagnóstico roda com as fontes abertas e grava a ficha (fonte, data e evidência de cada critério).
2. O relatório AB+S do mesmo imóvel entra por um destes caminhos:
   * **UUID ou PDF entregue pelo produtor.** O código sai do texto do PDF (`ab_s.extrair_uuid`), nunca de print ou OCR;
   * **relatório emitido no atendimento.** O próprio produtor entra com o login gov.br dele e emite o relatório, com o técnico ao lado. O técnico não guarda nem digita a senha do produtor, e o projeto não emite relatório em nome de ninguém.
3. `ab_s.consultar` confirma o relatório na API pública e grava a resposta pseudonimizada. Os critérios 1 a 9 vêm da qualificação, e o desmatamento vem do endpoint `area-producao`.
4. Cada critério é classificado na matriz de concordância de [`ab-s-validacao-cruzada.md`](../../atividade-03/ab-s-validacao-cruzada.md), seção 7: concordância, falso positivo, falso negativo, fora de cobertura, ou "Não conforme" por falta de dado na fonte oficial.
5. A ficha mostra os dois resultados lado a lado. Quando divergem, prevalece o oficial, e a divergência fica registrada com as duas datas de consulta.

Regras:
* Consentimento escrito do titular antes de usar o UUID. O UUID dá acesso ao resultado do produtor.
* A diferença de data entre a consulta do projeto e a emissão do relatório é registrada. Uma pendência que surgiu depois da emissão não conta como falso positivo.
* O gabarito do autor continua só como teste de regressão e aparece separado da medida de acerto na página.

### Consequences

* Good, because a qualidade do pré-diagnóstico passa a ser medida contra o resultado oficial, critério por critério.
* Good, because cada atendimento gera mais uma linha na matriz, sem custo extra para o produtor, que já precisa do relatório para o crédito.
* Bad, because a amostra depende de produtores que aceitem participar; um relatório só confere o mapeamento e não mede taxa de erro.
* Bad, because a estrutura da resposta 200 ainda não é conhecida (nenhum relatório real até 30/10/2026); o primeiro relatório pode exigir ajuste em `ab_s.interpretar`.
* Bad, because o AB+S também erra ("Não conforme" por falta de dado no INCRA, datas de atualização fixas em 01/01/2010); esses casos ficam numa classe própria, e não contam como erro do projeto.
