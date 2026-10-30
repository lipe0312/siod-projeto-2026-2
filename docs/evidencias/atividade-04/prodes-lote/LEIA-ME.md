# PRODES em lote, com verificação mensal

Execuções de `python -m pipeline --fontes prodes --evidencia docs/evidencias/atividade-04/prodes-lote` em 30/10/2026. Recorte: MG, Cerrado e Mata Atlântica, anos PRODES 2019 em diante.

| Arquivo | O que é |
|---|---|
| `execucao_20261030_010627.*` | Primeira execução: verificação feita, 15 anos-bioma baixados, 112.817 polígonos recebidos e 112.717 no parquet (100 descartados por classe fora do domínio) |
| `execucao_20261030_011148.*` | Segunda execução no mesmo dia: verificação reaproveitada, sem nenhuma requisição ao serviço |
| `manifesto.json` | Cópia de `data/raw/inpe_prodes/lote/manifesto.json`: contagem por ano no Brasil, último ano publicado por bioma e, por ano e UF, contagem, arquivo, SHA-256 da resposta e do conteúdo e datas de imagem |
| `inpe_prodes_publicacao.json` | Cópia de `data/processed/inpe_prodes_publicacao.json`, o que o pré-diagnóstico lê: último ano por bioma, datas de verificação, SHA-256 do parquet e histórico |

## O que a verificação encontrou

| Bioma | Último ano publicado | Imagens do último ano |
|---|---|---|
| Cerrado | 2026 | 27/07/2026 a 12/08/2026 |
| Mata Atlântica | 2025 | 26/06/2025 a 16/10/2025 |

Até esta atividade, o último ano era a constante `PRODES_ULTIMO_ANO_PUBLICADO = 2025`, conferida em 14/10/2026. A primeira verificação achou o Cerrado 2026 já publicado. Com ele, os 8 alertas DETER de 2025 do caso de Serra do Salitre passaram de "aguardando consolidação" a "confirmado" (ver `../prediagnostico/`).

## Validações próprias do lote

| Código | Severidade | O que pega |
|---|---|---|
| `PRODES_ULTIMO_ANO_RECUOU` | erro | Último ano publicado menor que o da verificação anterior: não substitui o parquet |
| `PRODES_SEM_ANO_PUBLICADO` | erro | Bioma sem nenhum ano com polígono |
| `PRODES_NOVO_ANO_PUBLICADO` | alerta | Ano novo desde a verificação anterior |
| `PRODES_ANO_CONSOLIDADO_ALTERADO` | alerta | Ano anterior ao último mudou de conteúdo (comparado pelo SHA-256 das feições ordenadas pelo uuid, porque o da resposta muda a cada pedido) |
| `PRODES_ANO_SEM_POLIGONO_NO_RECORTE` | alerta | Ano publicado sem polígono numa UF do recorte |
| `PRODES_DATA_IMAGEM_FUTURA` | alerta | `image_date` depois da data da execução |

As demais (estrutura, contagem anunciada x recebida, CRS, uuid, classe, geometria, UF, datas, área) são as da fonte sob demanda e estão em `pipeline/fontes/inpe_prodes.py`. Os testes, com um serviço WFS falso, estão em `tests/test_prodes_lote.py`.

## Como regerar

```bash
.venv/bin/python -m pipeline --fontes prodes --verificar-prodes --evidencia docs/evidencias/atividade-04/prodes-lote
```

Leva cerca de 2 minutos na primeira vez (cerca de 25 MB de parquet). Sem `--verificar-prodes`, a execução dentro de 30 dias da última verificação não vai à rede.
