# Cobrir o Brasil inteiro sem aceitar dado incompleto como limpo

## Context and Problem Statement

O pré-diagnóstico foi feito e conferido no café de MG. A decisão de 30/10/2026 é que ele funcione em qualquer imóvel do Brasil, ou na quase totalidade. O teste desse dia ([`evidencias/atividade-04/cobertura-e-persistencia/`](../../evidencias/atividade-04/cobertura-e-persistencia/), scripts 02 e 03) achou um CAR em cada bioma e mostrou o que impede isso hoje:

| Achado | Efeito |
|---|---|
| `sicar.consultar_ponto` usa `uf="MG"` por padrão, e o pré-diagnóstico por coordenada não informa a UF | Qualquer ponto fora de MG sai "CAR não localizado" (inconclusivo). Nos 7 pontos testados, todos saíram assim; informando a UF, os 7 CARs foram achados (PA, MT, BA, RS, MS, SP, PR) |
| `config.CAMADAS_PRODES` só tem Cerrado e Mata Atlântica | Um imóvel na Amazônia, na Caatinga, no Pampa ou no Pantanal fica sem PRODES e pode sair "sem ocorrência" de desmatamento: falso negativo |
| O PRODES sob demanda depende do WFS do TerraBrasilis, que respondeu HTTP 502 durante o teste | As 7 fichas fora de MG pararam com erro; nenhuma foi gerada |
| Amazônia e Caatinga passam de 50 mil polígonos em alguns anos (Caatinga 2024: 85.099; Amazônia 2022: 64.669) | Uma requisição por ano e bioma, como hoje, fica acima do limite de 50 mil do código |
| A regra 4 do [ADR 0009](0009-combinar-deter-e-prodes-por-data-de-imagem-e-cobertura.md) ("sem cobertura de [data] até hoje" em bioma sem DETER) não está implementada | Na Mata Atlântica, na Caatinga, no Pampa e no Pantanal, o período depois da última imagem PRODES aparece como limpo |
| O lote filtra o PRODES pelo campo `state` ([ADR 0010](0010-persistir-o-prodes-em-lote-e-verificar-a-publicacao-todo-mes.md)) | Um polígono gravado com a UF vizinha, junto à divisa, fica de fora |

## Considered Options

* Manter o PRODES sob demanda fora do recorte do lote
* PRODES em lote nacional de uma vez
* PRODES em lote por UF, com a UF entrando quando o primeiro imóvel dela é consultado, recortado pelo contorno da UF, e "inconclusivo" quando uma fonte falhar

## Decision Outcome

Chosen option: "PRODES em lote por UF, com a UF entrando quando o imóvel chega", because o serviço sob demanda falhou nos 7 casos do teste e a carga nacional de uma vez faz centenas de requisições a um serviço instável. Por UF, só se baixa o que vai ser usado, e cada UF fica pronta para os imóveis seguintes.

Regras (implementadas em 30/10/2026):
1. **PRODES dos seis biomas**, de 2019 em diante.
   * A partição Parquet de cada UF ([ADR 0011](0011-persistir-em-parquet-por-uf-e-adiar-o-postgis.md)) recebe os biomas que tocam o contorno da UF (`territorio.biomas_da_geometria`).
   * Na Amazônia vale a camada do bioma (`prodes-amazon-nb`), e não a da Amazônia Legal, que repete o Cerrado de MT, MA e TO.
   * O lote começa com `config.PRODES_UFS_INICIAIS` (MG), e `inpe_prodes.garantir_uf` inclui a UF de cada imóvel novo no pré-diagnóstico.
2. **Requisição pelo retângulo do contorno da UF**, não pelo campo `state`.
   * O retângulo é dividido em quatro enquanto passar de 8 mil polígonos (`config.PRODES_POLIGONOS_POR_PARTE`).
   * Também é dividido quando o serviço responde 5xx: respostas grandes recebem 502 do gateway.
3. **A UF de cada polígono vem do contorno do IBGE**: a do ponto representativo.
   * Um polígono que cruza a divisa entra na partição das duas UFs.
   * O `state` do INPE fica em `uf_fonte`; a diferença vira o alerta `PRODES_UF_DIFERE_DO_CONTORNO`.
   * Polígono do retângulo que não toca a UF é descartado da partição (`PRODES_FORA_DO_CONTORNO_DA_UF`).
4. **A UF do imóvel por coordenada vem do contorno**: o ponto é localizado na malha de UFs do IBGE antes da consulta ao SICAR. Ponto fora do Brasil ou no mar fica inconclusivo, com esse motivo, sem consulta.
5. **Dado incompleto nunca vira "sem ocorrência".**
   * Fonte que não respondeu (PRODES depois das tentativas) ou parquet de fonte ausente deixam o critério inconclusivo, com o motivo.
   * O resultado segue a ordem pendência > inconclusivo > indício > sem pendência. Uma pendência confirmada continua aparecendo, e um inconclusivo impede "sem pendência nas fontes verificadas".
6. **Bioma sem DETER** (Mata Atlântica, Caatinga, Pampa, Pantanal), por decisão de 30/10/2026: o critério de desmatamento sai "sem ocorrência" se nada for achado até a última imagem PRODES, com o aviso "sem cobertura de [última imagem] até hoje" na ficha.
   * Não sai inconclusivo: senão quase todo imóvel desses biomas ficaria assim até o próximo PRODES.
   * Isso substitui a regra 4 do [ADR 0009](0009-combinar-deter-e-prodes-por-data-de-imagem-e-cobertura.md).
7. **Conjunto de teste nacional na demonstração:**
   * um CAR por bioma (os 7 do teste de 30/10/2026);
   * 4 casos de área protegida ([ADR 0014](0014-verificar-terras-indigenas-quilombolas-e-unidades-de-conservacao-por-sobreposicao.md));
   * ao lado dos 6 de MG.

### Consequences

* Good, because o imóvel em qualquer bioma passa a ter PRODES, e a falha de um serviço externo aparece como inconclusivo, não como imóvel limpo.
* Good, because o polígono de divisa deixa de ser perdido. Isso fecha o ponto aberto no ADR 0010.
* Good, because a primeira consulta de cada UF retoma do que já foi gravado se o serviço cair no meio. Depois disso, o pré-diagnóstico da UF não depende do TerraBrasilis.
* Good, because o aviso de cobertura deixa visível o período sem fonte, sem bloquear o resultado.
* Bad, because a primeira consulta de uma UF demora: em 30/10/2026, MG (3 biomas, 8 anos) levou dezenas de minutos, com muitos 502 e divisões.
* Bad, because no bioma sem DETER um desmatamento recente só aparece no próximo PRODES; até lá, o imóvel pode sair "sem pendência", com o aviso.
* Bad, because os 7 pontos foram escolhidos à mão, um por bioma; não medem a taxa de sucesso no Brasil.
