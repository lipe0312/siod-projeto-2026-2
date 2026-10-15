# Atividade 03 — Investigação de fontes: CAR, PRODES e AB+S

Escopo inicial. O detalhe de cada frente está em [`atividade-03/car.md`](atividade-03/car.md), [`atividade-03/prodes-e-escada-de-fontes.md`](atividade-03/prodes-e-escada-de-fontes.md) e [`atividade-03/ab-s-validacao-cruzada.md`](atividade-03/ab-s-validacao-cruzada.md). O plano está em [`plans/atividade-03-plano.md`](plans/atividade-03-plano.md). O caderno [`notebooks/02_fontes_antes_e_depois.ipynb`](../notebooks/02_fontes_antes_e_depois.ipynb) mostra, fonte a fonte, o dado bruto, o dado tratado e as validações, e reproduz os números principais desta página.

## 1. Perguntas de partida e o que os testes responderam

| Pergunta | Hipótese inicial | Resultado |
|---|---|---|
| O CAR pode ser obtido sem captcha nem API paga? | Só por download manual, município a município | Sim. O WFS público do SICAR entregou o CAR completo dos 10 municípios do recorte (33.452 imóveis, anunciado = recebido) |
| Há fonte de desmatamento para os biomas sem DETER? | PRODES | Sim. O PRODES cobre os 6 biomas, com cadência anual e data de imagem, não de evento |
| O AB+S pode servir de validação cruzada? | Só pela API do Serpro | Só relatório a relatório, pela API pública de autenticidade, com o código (UUID) que o produtor já tem. Ainda sem resposta válida |
| O pré-diagnóstico gera falso positivo ou falso negativo? | Preocupação teórica | Medido em parte (seção 4) |

## 2. CAR

- **Fornecedor.** `geoserver.car.gov.br`, o GeoServer do SICAR, mantido pelo Serviço Florestal Brasileiro. Uma camada por UF (`sicar:sicar_imoveis_{uf}`), sem login, sem CPF.
- **Os 10 municípios são recorte, não limite do serviço.** O recorte são os 10 maiores produtores de café de MG na PAM/IBGE de 2025. Não se encontrou limite de quantidade: cada município veio inteiro numa requisição. A coleta da UF inteira não foi testada.
- **O que significa.** Ter os dados do CAR não é o problema. Os problemas são:
  - o cadastro autodeclarado: 20,1% dos imóveis têm 95% ou mais da área coberta por outro CAR, e 73% estão "aguardando análise";
  - quem não tem CAR, que não aparece em base nenhuma.
- **Atribuição.** 128 dos 179 embargos e alertas do recorte caem num único CAR principal. Os demais são reportados como ambíguos, sem escolher um dono.

## 3. PRODES e o "match" de 69,6%

**Como foi medido.** Para cada alerta DETER de desmatamento no Cerrado de MG (2021–2025, 5.612 alertas em anos PRODES já publicados), verificou-se se polígonos PRODES cobrem ao menos 10% do alerta:

| Resultado | Alertas | % | Leitura |
|---|---:|---:|---|
| Confirmado (PRODES com imagem na data do alerta ou depois) | 3.907 | 69,6 | Supressão nova, confirmada pela consolidação anual |
| Já suprimido antes (só PRODES de imagem anterior) | 935 | 16,7 | Supressão real, mas não nova: área já registrada antes |
| Não confirmado | 770 | 13,7 | O PRODES não registrou supressão ali |

Fonte: caderno, seção 6 (`inpe_prodes.confirmar_alertas`). Por área, a confirmação é de 71,9%.

**Bom ou ruim?** A taxa não é uma nota de qualidade do DETER. O DETER é um alerta rápido para fiscalização, e o PRODES é o mapeamento anual consolidado. A leitura correta:

- **86,3% dos alertas** (confirmados mais já suprimidos) estão em área que o PRODES também registra como suprimida. O DETER raramente aponta onde não houve nada.
- **Só 69,6% indicam supressão nova** naquela data. Para a EUDR, o que importa é a data, então o DETER sozinho é indício e não prova.
- **13,7% sem confirmação** é o teto do falso positivo do DETER, não o falso positivo em si. Parte se explica pelo método: o limiar de 10% foi escolhido pelo projeto, há diferença de resolução e de área mínima entre os dois mapeamentos, e há desalinhamento de geometria.
- **Vale para o Cerrado de MG.** Não foi medido em outros biomas ou UFs.

**Consequência para o projeto.**
- **Alerta DETER sem PRODES:** "indício de supressão".
- **Com PRODES posterior:** "supressão confirmada", com a data da imagem.
- **Data de corte da EUDR (31/12/2020):** continua incerta na faixa entre a imagem de 2020 e o fim daquele ano. Há 166 alertas DETER nessa janela que o PRODES só registra como 2021.

## 4. Falso positivo e falso negativo, ponderados

| Situação | Tipo | Peso real |
|---|---|---|
| Alerta DETER não confirmado pelo PRODES (13,7%) | Falso positivo em potencial | Teto, não medida: inclui efeito do limiar e da resolução. Mitigado ao rotular como "indício" |
| Alerta "já suprimido antes" (16,7%) | Falso positivo de data, não de evento | Não acusa desmatamento novo; conta como passivo anterior |
| Supressão entre a imagem de 2020 e 31/12/2020 | Falso positivo da data de corte | 166 alertas no Cerrado de MG; sem DETER (Mata Atlântica), não há como separar |
| 6 dos 9 critérios do AB+S sem fonte aberta | Falso negativo **só se** reportado como "conforme" | O projeto exibe "não verificado". Vira lacuna de cobertura declarada, não erro |
| Produtor sem CAR | Falso negativo estrutural | Não detectável com dado aberto; declarado como limite |
| CAR sobreposto tratado como confiável | Pode gerar os dois tipos | 20,1% do recorte; a atribuição lista todos os CARs atingidos |

## 5. AB+S

**O que seria o uso "em massa".** Consultar a situação de uma carteira inteira (todos os produtores de uma cooperativa ou banco), periodicamente, sem depender de cada produtor emitir e entregar o relatório. A entrada seria CAR mais CPF/CNPJ, e a saída a qualificação de cada imóvel. Com isso, o técnico veria quem mudou de situação sem pedir nada ao produtor.

**Por que não dá.**
- **O único canal em lote é a API do Serpro:** paga, sob contrato e restrita a operadores financeiros autorizados pelo Banco Central.
- **O canal público responde só a quem já tem o código de autenticidade.** O código só existe depois que o titular emite o relatório com login gov.br e imóvel no SNCR.
- **Não se procura código por varredura.** O espaço de UUIDs aleatórios torna isso inviável, e cada código dá acesso ao resultado de um produtor.

**O que dá, um a um.** O produtor (ou o técnico, com o PDF que o produtor entrega) informa o código e o projeto consulta a API pública. O resultado oficial aparece ao lado do pré-diagnóstico, citado com data, UUID e SHA-256 da resposta. É lento, mas resolve o caso de uso principal: confirmar ou desmentir o pré-diagnóstico de um produtor específico.

**Como obter um código válido** (pendência B3):
1. **Conta gov.br própria:** só funciona com um imóvel rural vinculado ao CPF no SNCR.
2. **Produtor voluntário:** cede o PDF, com consentimento por escrito.
3. **Relatório divulgado pelo próprio titular.**

Até hoje, nenhum código real foi obtido. O código do relatório de demonstração é de ambiente de teste, e a API de produção responde 404 a ele.

## 6. Tentado e descartado (no-go)

| Tentativa | Resultado | Motivo |
|---|---|---|
| API do Serpro (AB+S em lote) | Descartada | Paga e restrita a operadores autorizados pelo Banco Central. Fica como fonte de produção |
| APIs pagas de terceiros para o CAR | Descartadas | Desnecessárias: o WFS público entrega o mesmo dado |
| Ler o código de autenticidade por OCR de print | Falhou | Melhor caso: 29 de 36 caracteres. O projeto exige o PDF |
| Validar o relatório de demonstração | 404 | Relatório de ambiente de teste |
| Ligar CAR a CPF com dado aberto | Impossível | O CAR público não traz documento |
| Datar o desmatamento antes ou depois de 31/12/2020 só com o PRODES | Impossível | `image_date` é a data da imagem, não do evento |
| `requests` do Python contra o SICAR com a configuração padrão | Falha de TLS | Servidor exige configuração antiga. Resolvido em `pipeline/fontes/sicar.py` com um adaptador de cifras de nível 1 e renegociação legada; a verificação do certificado nunca foi desligada |

## 7. O que entra no projeto

- **SICAR e PRODES** como fontes do pipeline consultadas sob demanda (`pipeline/fontes/sicar.py` e `pipeline/fontes/inpe_prodes.py`), com o mesmo tratamento, as mesmas validações (`ResultadoFonte`) e os testes das fontes da Atividade 02. Consulta-se só a área que o caso toca, com cache da resposta bruta; não há carga em massa. A atribuição embargo ou alerta → CAR está em `pipeline/cruzamento.py`.
- **AB+S** como consulta sob demanda, um relatório por vez (`pipeline/fontes/ab_s.py`). Nunca é uma afirmação de conformidade do projeto ([ADR 0008](arquitetura/adr/0008-usar-o-ab-s-como-referencia-sem-declarar-conformidade.md)).
- **Escada DETER × PRODES** por bioma ([ADR 0009](arquitetura/adr/0009-combinar-deter-e-prodes-por-data-de-imagem-e-cobertura.md)).

## 8. Pendências

- B3: obter um código AB+S real e registrar a primeira resposta 200.
- Levar o resultado das consultas sob demanda ao relatório do pré-diagnóstico.
- Medir a confirmação DETER × PRODES fora do Cerrado de MG.
- Slides.
