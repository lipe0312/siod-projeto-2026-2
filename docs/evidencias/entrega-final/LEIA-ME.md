# Entrega final: carteira de demonstração

**Cooperativa Vale do Cerrado (demonstração)**: 12 imóveis (7 de café, 5 de gado), `organizacao_id = 'demonstracao'`. Os 12 usam CARs públicos já conferidos (os mesmos da demonstração do pré-diagnóstico); os nomes, os ids de produtor e as commodities são fictícios. Nenhum CPF/CNPJ está na planilha nem aqui: três linhas (CVC-06, CVC-08, CVC-10) recebem o documento de demonstração em memória, na hora de rodar, e ele só aparece pseudonimizado no lago. Não há caso positivo de Lista Suja (decisão de 23/11/2026): um caso positivo exigiria o documento de uma pessoa real ou um lago sintético.

| Arquivo | O que é |
|---|---|
| `01_cooperativa_demonstracao.py` | Desenha os talhões, roda a carteira sem rede e reescreve este arquivo |
| `../../modelos/cooperativa_demonstracao.csv` | A planilha de 12 linhas (formato de `pipeline/carteira.py`) |
| `../../modelos/talhoes/*.kml` | Talhões sintéticos, desenhados dentro do CAR a partir da geometria dele |
| `data/saidas/console/demonstracao/` | Fichas (`fichas/`), `carteira.csv` e `carteira.html` (não versionada) |

As camadas de mapa de cada ficha (`.camadas.geojson`) vêm da issue #31 e aparecem nessa pasta quando ela entrar; este script não as gera.

## Caso → o que mostra → situação obtida

Carteira de 12 imóveis: 7 com pendência, 3 com indício, 1 inconclusivo, 1 sem pendência nas fontes verificadas.

| Caso | Imóvel | O que mostra | Situação obtida |
|---|---|---|---|
| CVC-01 | Fazenda Pé de Serra (demonstração), café, Patrocínio/MG (com talhão) | Talhão desenhado longe do desmatamento: o critério EUDR limpa na área de produção, mas o desmatamento do resto do imóvel continua como indício | **com indício**; indício: Desmatamento após 31/12/2020 no resto do imóvel (risco de legalidade e de mistura) |
| CVC-02 | Sítio Boa Safra (demonstração), café, Serra do Salitre/MG | Embargo do IBAMA e alertas confirmados pelo PRODES, em Serra do Salitre | **com pendência**; pendência: Embargo IBAMA; Desmatamento após 31/12/2020 (EUDR) |
| CVC-03 | Fazenda Alto do Cerrado (demonstração), café, Patrocínio/MG (com talhão) | Talhão sobre os alertas DETER de ago. 2026 (ainda sem PRODES): o indício cai na área de produção e o técnico confere em imagem | **com indício**; indício: Desmatamento após 31/12/2020 (EUDR); Desmatamento após 31/12/2020 no resto do imóvel (risco de legalidade e de mistura) |
| CVC-04 | Sítio Grota Funda (demonstração), café, Patrocínio/MG | Embargo do IBAMA e alerta sobre área já suprimida antes: o alerta fica como indício, não como pendência | **com pendência**; pendência: Embargo IBAMA; indício: Desmatamento após 31/12/2020 (EUDR) |
| CVC-05 | Fazenda Três Barras (demonstração), café, Patrocínio/MG | CAR com notificação pendente, embargos e alerta confirmado: o caso mais pesado do café | **com pendência**; pendência: Embargo IBAMA; Desmatamento após 31/12/2020 (EUDR); indício: CAR |
| CVC-06 | Sítio Água Limpa (demonstração), café, Patrocínio/MG | Imóvel analisado e sem achado nas fontes, com documento informado: o limite do sistema (nunca diz "conforme") | **sem pendência nas fontes verificadas** |
| CVC-07 | Sítio Coordenada Trocada (demonstração), café, sem localização | Coordenada com latitude e longitude trocadas: a linha não é consultada e diz por quê | **inconclusivo**; motivo: lat/lon fora do Brasil (conferir se não estão trocados) |
| CVC-08 | Fazenda Pantanal Alto (demonstração), gado de corte, Corumbá/MS | Pantanal: PRODES após 2020 em Corumbá, com documento informado e item do gado no plano de ação | **com pendência**; pendência: Desmatamento após 31/12/2020 (EUDR) |
| CVC-09 | Fazenda Rio Capim (demonstração), gado de corte, Paragominas/PA | Amazônia: PRODES de 2021 com data incerta diante do corte (indício, não pendência) | **com indício**; indício: Desmatamento após 31/12/2020 (EUDR) |
| CVC-10 | Fazenda Saracura (demonstração), gado de corte, Santarém/PA | Sobreposição com território quilombola (Santarém), com documento informado | **com pendência**; pendência: Sobreposição: território quilombola; indício: CAR |
| CVC-11 | Fazenda Ypoi (demonstração), gado de corte, Paranhos/MS | Sobreposição com terra indígena declarada e APA (Paranhos) | **com pendência**; pendência: Sobreposição: terras indígenas; indício: CAR; Sobreposição: unidade de conservação |
| CVC-12 | Fazenda Ponto em Goiás (demonstração), gado de corte, Rio Verde/GO | Localização só por coordenada em Goiás: o ponto precisa cair em um único CAR | **com pendência**; pendência: Desmatamento após 31/12/2020 (EUDR) |

Nos dois casos com talhão o cruzamento de desmatamento passa a ser com a área desenhada, e a ficha separa o que está na área de produção do que está no resto do imóvel. O talhão de CVC-01 deixa de fora todo o desmatamento do CAR (o resto vira indício); o de CVC-03 cobre os alertas (o indício cai na área de produção).

## Rastreabilidade desta execução

- Execução de carteira `519fd0b3-62f3-43fc-a2d8-2a606c0829ca` (`diag.execucao`, organização `demonstracao`), iniciada em 23/11/2026 17:42:10 (horário de Brasília).
- Carteira importada `91a354fc-adbd-4b25-9d4a-0f50dddce79e` em `cad.carteira` (23/11/2026 17:42:10); cargas: `cadastro:20261123T174210` (cadastro) e `pipeline:20261123T174210` (diag).
- Cargas das fontes em uso (`diag.execucao_carga`): funai_terras_indigenas `funai_terras_indigenas:20261103T210956`, ibama_embargos `ibama_embargos:20261103T210432`, ibge_municipios `ibge_municipios:20261103T210432`, ibge_territorios_quilombolas `ibge_territorios_quilombolas:20261103T211002`, incra_quilombolas `incra_quilombolas:20261103T211003`, inpe_deter `inpe_deter:20261103T210437`, inpe_prodes `inpe_prodes:20261103T210506`, mma_unidades_conservacao `mma_unidades_conservacao:20261103T210958`, mte_lista_suja `mte_lista_suja:20261103T210953`, territorio `territorio:20261103T210500`.
- SICAR: cache em `data/raw/sicar/` (um arquivo por consulta, com `.meta.json` e SHA-256); PRODES: lote em `data/` (`--sem-baixar-prodes`).

## Como regerar

```bash
.venv/bin/python docs/evidencias/entrega-final/01_cooperativa_demonstracao.py
```

Leva menos de 30 s. Duas execuções dão a mesma tabela (o SICAR vem do cache); só mudam o id e o horário da execução, e a carteira passa a comparar com a execução anterior. Sem cache do SICAR, o imóvel fica inconclusivo com o motivo e o script avisa; `--ao-vivo` permite a consulta à rede.
