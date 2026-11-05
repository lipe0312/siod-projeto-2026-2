# Orçamento do banco: lite e completo

Medido em 2026-11-05 15:09 UTC num PostGIS 17-3.5 local (`banco/docker-compose.yml`), com `python -m pipeline.armazenamento.banco`. Tamanho por `pg_total_relation_size` (dados, índices e TOAST). Cada perfil foi carregado num banco novo.

| | MB | Meta | Supabase gratuito (500 MB) | Neon gratuito (1 GB por projeto) |
|---|---:|---|---|---|
| **Lite** | **210,3** | ≤ 250 MB (limite 300): dentro da meta | cabe | cabe |
| **Completo** | **2.133,7** | | não cabe | não cabe |

## Perfil lite

| Tabela | Origem | Linhas | MB | Segundos |
|---|---|---:|---:|---:|
| `ref.embargo_ibama` | lago | 110.377 | 75,9 | 2,2 |
| `ref.unidade_conservacao` | lago | 3.301 | 66,5 | 4,4 |
| `ref.terra_indigena` | lago | 665 | 31,6 | 1,8 |
| `meta.descarte` | lago | 30.003 | 16,7 | 0,4 |
| `geo.bioma` | lago | 6 | 11,3 | 0,7 |
| `ref.territorio_quilombola` | lago | 540 | 3,9 | 0,2 |
| `diag.evidencia` | lago | 496 | 1,0 | 0,1 |
| `geo.municipio` | lago | 5.571 | 1,0 | 0,0 |
| `diag.criterio` | lago | 1.360 | 0,6 | 0,1 |
| `ref.lista_suja` | lago | 507 | 0,4 | 0,0 |
| `geo.uf` | lago | 27 | 0,4 | 0,0 |
| `geo.imovel_car` | lago | 17 | 0,1 | 0,0 |
| `diag.resultado_imovel` | lago | 136 | 0,1 | 0,0 |
| `meta.validacao` | lago | 143 | 0,1 | 0,0 |
| `meta.carga` | lago | 10 | 0,1 | 0,0 |
| `diag.execucao_carga` | lago | 80 | 0,1 | 0,0 |
| `diag.execucao` | lago | 8 | 0,0 | 0,0 |
| `meta.fonte` | lago | 12 | 0,0 | 0,0 |
| `cad.area_producao` | ausente | não carregada | 0,0 | 0,0 |
| `cad.imovel` | ausente | não carregada | 0,0 | 0,0 |
| `cad.produtor` | ausente | não carregada | 0,0 | 0,0 |
| `diag.conferencia_ab_s` | ausente | não carregada | 0,0 | 0,0 |
| `cad.carteira` | ausente | não carregada | 0,0 | 0,0 |
| `cad.carteira_item` | ausente | não carregada | 0,0 | 0,0 |
| `cad.consentimento` | ausente | não carregada | 0,0 | 0,0 |
| `cad.documento_trazido` | ausente | não carregada | 0,0 | 0,0 |
| `cad.organizacao` | ausente | não carregada | 0,0 | 0,0 |
| `cad.produtor_imovel` | ausente | não carregada | 0,0 | 0,0 |
| `cad.usuario` | ausente | não carregada | 0,0 | 0,0 |
| **Total das tabelas** | | | **210,3** | 10,2 |

## Perfil completo

| Tabela | Origem | Linhas | MB | Segundos |
|---|---|---:|---:|---:|
| `ref.desmatamento_prodes` | lago | 1.495.608 | 1.618,9 | 56,8 |
| `ref.alerta_deter` | lago | 247.970 | 221,7 | 6,6 |
| `ref.embargo_ibama` | lago | 110.377 | 151,7 | 4,8 |
| `ref.unidade_conservacao` | lago | 3.301 | 66,5 | 3,9 |
| `ref.terra_indigena` | lago | 665 | 31,6 | 1,3 |
| `meta.descarte` | lago | 30.003 | 16,8 | 0,4 |
| `geo.bioma` | lago | 6 | 11,3 | 0,7 |
| `ref.territorio_quilombola` | lago | 540 | 3,9 | 0,2 |
| `ref.quilombola_incra` | lago | 446 | 3,7 | 0,2 |
| `ref.quilombola_ibge` | lago | 495 | 3,5 | 0,2 |
| `diag.evidencia` | lago | 496 | 1,0 | 0,0 |
| `geo.municipio` | lago | 5.571 | 0,8 | 0,0 |
| `diag.criterio` | lago | 1.360 | 0,6 | 0,1 |
| `ref.lista_suja` | lago | 507 | 0,4 | 0,0 |
| `geo.uf` | lago | 27 | 0,4 | 0,0 |
| `geo.imovel_car` | lago | 17 | 0,1 | 0,0 |
| `diag.resultado_imovel` | lago | 136 | 0,1 | 0,0 |
| `meta.validacao` | lago | 143 | 0,1 | 0,0 |
| `meta.carga` | lago | 10 | 0,1 | 0,0 |
| `diag.execucao_carga` | lago | 80 | 0,1 | 0,0 |
| `diag.execucao` | lago | 8 | 0,0 | 0,0 |
| `meta.fonte` | lago | 12 | 0,0 | 0,0 |
| `cad.area_producao` | ausente | não carregada | 0,0 | 0,0 |
| `cad.imovel` | ausente | não carregada | 0,0 | 0,0 |
| `cad.produtor` | ausente | não carregada | 0,0 | 0,0 |
| `diag.conferencia_ab_s` | ausente | não carregada | 0,0 | 0,0 |
| `cad.carteira` | ausente | não carregada | 0,0 | 0,0 |
| `cad.carteira_item` | ausente | não carregada | 0,0 | 0,0 |
| `cad.consentimento` | ausente | não carregada | 0,0 | 0,0 |
| `cad.documento_trazido` | ausente | não carregada | 0,0 | 0,0 |
| `cad.organizacao` | ausente | não carregada | 0,0 | 0,0 |
| `cad.produtor_imovel` | ausente | não carregada | 0,0 | 0,0 |
| `cad.usuario` | ausente | não carregada | 0,0 | 0,0 |
| **Total das tabelas** | | | **2.133,7** | 75,4 |

## Observações

- "Não carregada": a tabela ainda não está no lago. Ocupa só o espaço vazio (índices e catálogo).
- `cad`, `diag`, `meta` e `geo.imovel_car` ainda não têm dados reais. Com uma carteira real, o lite cresce pouco: o peso está nas geometrias das camadas públicas.
- O completo inclui o PRODES do Brasil inteiro, lido do lago.
