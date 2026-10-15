# Obter o CAR pelo WFS público do SICAR e atribuir embargos e alertas pela área de interseção

## Context and Problem Statement

Sem o polígono e a situação do CAR, nenhum embargo IBAMA, alerta DETER ou registro da Lista Suja pode ser atribuído a um imóvel. O projeto precisa de uma fonte do CAR que seja aberta, gratuita e sem dado pessoal, e de uma regra para decidir a quais CARs um embargo ou alerta pertence.

Os testes da Atividade 3 ([car.md](../../atividade-03/car.md)) mostraram que:
- o SICAR publica um WFS aberto, com uma camada por UF, sem CPF nem nome; nos 10 maiores municípios produtores de café de MG, os 33.452 imóveis anunciados foram recebidos, uma requisição por município;
- um embargo ou alerta toca, em geral, mais de um CAR (mediana 2, máximo 7 no recorte), porque vizinhos encostam na divisa e porque 20% dos imóveis têm 95% ou mais da área coberta por outro CAR;
- o servidor exige TLS antigo: o `requests` com a configuração padrão falha no *handshake*; com cifras de nível 1 e renegociação legada, e a verificação do certificado ligada, funciona;
- os filtros espaciais devolvem zero, sem erro, quando a ordem dos eixos está trocada.

## Considered Options

* Baixar o shapefile do CAR pela consulta pública do SICAR, município a município, de forma manual
* Usar a API SICAR Demonstrativo (catálogo Conecta gov.br) ou um serviço pago de consulta do CAR
* Usar o WFS público do SICAR: coleta por município, com conferência da contagem, e consulta espacial por objeto para a atribuição

## Decision Outcome

Chosen option: "Usar o WFS público do SICAR", because é a única aberta, sem contrato e automatizável, e porque entrega polígono, código, status e condição na mesma resposta. A API do catálogo Conecta e os serviços pagos ficam registrados como **fontes de produção** (plano, seção 7). O download manual de shapefile não se reproduz em pipeline.

**Coleta em lote.** Uma requisição por município (`cod_municipio_ibge`), conferindo o `numberMatched` de um pedido `resultType=hits` contra as feições recebidas, como na partição mensal do DETER ([ADR 0004](0004-coletar-alertas-deter-em-particoes-mensais-e-identificar-pelo-conteudo.md)). Município incompleto é coletado de novo.

**Atribuição.** Para cada embargo ou alerta, uma consulta `BBOX` sem filtro de município (em 7 objetos do recorte, um CAR atingido estava registrado em outro município; 5 deles eram principais), interseção calculada localmente e, por par (objeto, CAR), `fracao_objeto`, `fracao_car` e largura média da faixa comum. Classes:
- **principal:** `fracao_objeto` >= 50%, no vale da distribuição em U das frações;
- **tangente:** `fracao_objeto` < 5% e faixa comum com menos de 30 m, metade do pixel (55 a 64 m) das câmeras usadas pelo DETER;
- **parcial:** o resto.

Um objeto pode ter mais de um principal quando há CARs sobrepostos. A regra lista todos, sem escolher um. Objeto sem CAR é "sem CAR localizado", nunca "sem CAR".

**Escada de obtenção.** Código do CAR (0,30 s), ponto (0,27 s), polígono (0,36 s), relatório AB+S via código do CAR (frente B) e, sem nenhum desses, o recibo pedido ao produtor. O SICAR não publica documento, então CPF/CNPJ não leva ao CAR por fonte aberta.

**Acesso.** Nunca `verify=False`. O módulo [`pipeline/fontes/sicar.py`](../../../pipeline/fontes/sicar.py) monta na sessão do `requests` um adaptador com o contexto TLS descrito no plano (`DEFAULT:@SECLEVEL=1` e `OP_LEGACY_SERVER_CONNECT`, com verificação ligada). O SICAR é consultado sob demanda, por município, retângulo ou ponto, com a resposta bruta guardada em `data/raw/sicar/`. Os filtros espaciais usam a forma sem SRS, em (latitude, longitude), com a ordem fixada em `config.ORDEM_EIXOS_FILTRO`; um teste confere a ordem, e a validação `CAR_PARTICAO_INCOMPLETA` confere anunciado = recebido. A regra de atribuição está em [`pipeline/cruzamento.py`](../../../pipeline/cruzamento.py).

### Consequences

* Good, because o CAR entra no projeto sem contrato e sem dado pessoal, e a completude de cada município é verificada.
* Good, because a atribuição separa o CAR que contém o embargo dos vizinhos que só encostam, e deixa explícita a sobreposição entre cadastros em vez de escondê-la.
* Good, because os limiares têm gráfico e tabela de sensibilidade; trocar um limiar é mudar uma constante.
* Bad, because o status `AT` não indica ausência de sobreposição: dos 6.727 imóveis quase inteiramente sobrepostos, 5.537 estão `AT`. O projeto não pode tratar `AT` como regularidade.
* Bad, because o limiar de largura vem da resolução do DETER; para embargos do IBAMA, a resolução de origem não é conhecida.
* Bad, because a coleta depende de um servidor com TLS antigo e de comportamento não documentado na ordem dos eixos; uma mudança no servidor pode quebrar a coleta sem erro aparente, o que exige os testes de contagem e de ponto conhecido.
