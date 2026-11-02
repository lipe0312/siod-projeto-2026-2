# PRODES em lote, com verificação mensal

Execuções de `python -m pipeline --fontes prodes --evidencia docs/evidencias/atividade-04/prodes-lote`.

| Arquivo | O que é |
|---|---|
| `execucao_20261030_010627.*` | Primeira versão (filtro pelo campo `state`, só MG, Cerrado e Mata Atlântica): verificação feita, 15 anos-bioma baixados, 112.817 polígonos recebidos e 112.717 no parquet (100 descartados por classe fora do domínio) |
| `execucao_20261030_011148.*` | Mesma versão, mesmo dia: verificação reaproveitada, sem nenhuma requisição ao serviço |
| `execucao_20261030_231838.*` | Versão por UF ([ADR 0013](../../../arquitetura/adr/0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md)): partição de MG, recortada pelo contorno do IBGE, com Caatinga, Cerrado e Mata Atlântica |
| `execucao_20261101_051309.*` | Com as 8 UFs no lote (MG, RS, PR, SP, MS, BA, PA, MT): verificação reaproveitada, sem requisição |
| `execucao_20261102_123327.*` | PA e MT regravados do cache, sem requisição, depois da correção da classe em minúsculas (abaixo) |
| `manifesto.json` | Cópia de `data/raw/inpe_prodes/lote/manifesto.json`: contagem por ano no Brasil, último ano publicado por bioma, biomas de cada UF e, por ano, UF e parte do retângulo, contagem, arquivo, SHA-256 da resposta e do conteúdo e datas de imagem |
| `inpe_prodes_publicacao.json` | Cópia de `data/processed/inpe_prodes_publicacao.json`, o que o pré-diagnóstico lê: último ano por bioma, última imagem por UF e bioma, SHA-256 de cada partição e histórico |

## O que a verificação encontrou

| Bioma | Último ano publicado |
|---|---|
| Cerrado | 2026 |
| Amazônia, Caatinga, Mata Atlântica, Pampa, Pantanal | 2025 |

Até esta atividade, o último ano era a constante `PRODES_ULTIMO_ANO_PUBLICADO = 2025`, conferida em 14/10/2026. A primeira verificação achou o Cerrado 2026 já publicado. Com ele, os 8 alertas DETER de 2025 do caso de Serra do Salitre passaram de "aguardando consolidação" a "confirmado" (ver `../prediagnostico/`).

## Lote por UF (30/10 a 01/11/2026)

Cada UF entra no lote quando o primeiro imóvel dela é consultado. As 8 UFs abaixo são as dos imóveis da demonstração.

| UF | Biomas | Polígonos na partição | Parquet | `state` diferente do contorno | Tempo da primeira carga |
|---|---|---:|---:|---:|---:|
| MG | Caatinga, Cerrado, Mata Atlântica | 125.815 | 28 MB | 217 | cerca de 78 min |
| BA | Caatinga, Cerrado, Mata Atlântica | 166.703 | 37 MB | 302 | 5,3 h |
| PA | Amazônia, Cerrado | 171.020 | 51 MB | 66 | 7,9 h |
| RS | Mata Atlântica, Pampa | 61.970 | 18 MB | 31 | 2,6 h |
| MT | Amazônia, Cerrado, Pantanal | 69.049 | 21 MB | 78 | 5,1 h |
| MS | Cerrado, Mata Atlântica, Pantanal | 18.828 | 6,1 MB | 11 | 2,6 h |
| PR | Cerrado, Mata Atlântica | 18.568 | 4,0 MB | 47 | 1,4 h |
| SP | Cerrado, Mata Atlântica | 5.476 | 1,1 MB | 19 | 16 min |
| **Total** | | **637.429** | **167 MB** | **771** | |

O tempo se deve ao TerraBrasilis, que respondeu HTTP 502 em boa parte dos pedidos na madrugada de 31/10/2026. A carga retomou do que já estava gravado em cada nova tentativa. Das 386 combinações de ano, bioma e UF, 292 precisaram ser divididas em partes de até 8 mil polígonos.

**O que o recorte pelo contorno mudou em MG,** em relação à primeira versão (campo `state`):
- **Caatinga (norte de MG):** 12.933 polígonos que ficavam de fora.
- **Cerrado:** 63.003 em vez de 62.897, ou seja, 106 polígonos de divisa a mais.
- **Mata Atlântica:** 49.879 em vez de 49.820, ou seja, 59 a mais.

**Classe em minúsculas na Amazônia (corrigida em 02/11/2026).** A camada da Amazônia grava `main_class` como `desmatamento`, em minúsculas, em quase todo 2019 e 2020 e em alguns polígonos dos anos seguintes. A comparação exata com `DESMATAMENTO` descartava esses polígonos como classe fora do domínio: 68.132 em PA e MT, sendo 254 de 2021 a 2025. A classe passou a ser comparada em maiúsculas, com a validação `PRODES_CLASSE_CAIXA_DIFERENTE` (correção), e PA e MT foram regravados do cache. A demonstração continuou 17 de 17, sem mudança de resultado nos imóveis de PA e MT. O que mudou foi a base do "já suprimido antes" na Amazônia, que agora tem 2019 e 2020.

Na primeira montagem de MG, um polígono da Mata Atlântica 2024 com anel degenerado interrompeu o `make_valid` do GEOS ("mixed-dimension"). A correção (`vetor.tornar_valida`) passou a valer para todas as fontes.

## Validações próprias do lote

| Código | Severidade | O que pega |
|---|---|---|
| `PRODES_ULTIMO_ANO_RECUOU` | erro | Último ano publicado menor que o da verificação anterior: não substitui o lote |
| `PRODES_SEM_ANO_PUBLICADO` | erro | Bioma sem nenhum ano com polígono |
| `PRODES_NOVO_ANO_PUBLICADO` | alerta | Ano novo desde a verificação anterior |
| `PRODES_ANO_CONSOLIDADO_ALTERADO` | alerta | Ano anterior ao último mudou de conteúdo (comparado pelo SHA-256 das feições ordenadas pelo uuid, porque o da resposta muda a cada pedido) |
| `PRODES_CLASSE_CAIXA_DIFERENTE` | correção | `main_class` igual a `DESMATAMENTO` só sem diferenciar maiúsculas: normalizada |
| `PRODES_RETANGULO_DIVIDIDO` | correção | Ano e UF com mais de 8 mil polígonos no retângulo, ou com resposta 5xx, pedido em partes |
| `PRODES_FORA_DO_CONTORNO_DA_UF` | descarte | Polígono do retângulo que não toca o contorno da UF (é de UF vizinha) |
| `PRODES_UF_DIFERE_DO_CONTORNO` | alerta | Campo `state` diferente da UF do contorno; vale o contorno, e o `state` fica em `uf_fonte` |
| `PRODES_DATA_IMAGEM_FUTURA` | alerta | `image_date` depois da data da execução |

As demais (estrutura, contagem anunciada x recebida, CRS, uuid, classe, geometria, UF, datas, área) são as da fonte sob demanda e estão em `pipeline/fontes/inpe_prodes.py`. Os testes, com um serviço WFS falso e contornos fictícios, estão em `tests/test_prodes_lote.py`.

## Como regerar

```bash
.venv/bin/python -m pipeline --fontes prodes --verificar-prodes --evidencia docs/evidencias/atividade-04/prodes-lote
```

Sem `--verificar-prodes`, a execução dentro de 30 dias da última verificação não vai à rede. UF nova entra pelo pré-diagnóstico (`inpe_prodes.garantir_uf`); a carga de cada UF pode levar horas quando o TerraBrasilis está instável.
