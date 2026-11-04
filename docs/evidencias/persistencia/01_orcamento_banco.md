# Orçamento do banco: lite e completo

Medido em 2026-11-04 00:01 UTC num PostGIS 17-3.5 local (`banco/docker-compose.yml`), com `python -m pipeline.armazenamento.banco`. Tamanho por `pg_total_relation_size` (dados, índices e TOAST). Cada perfil foi carregado num banco novo.

| | MB | Meta | Supabase gratuito (500 MB) | Neon gratuito (1 GB por projeto) |
|---|---:|---|---|---|
| **Lite** | **184,8** | ≤ 250 MB (limite 300): dentro da meta | cabe | cabe |
| **Completo** | **2.030,0** | | não cabe | não cabe |

## Perfil lite

| Tabela | Origem | Linhas | MB | Segundos |
|---|---|---:|---:|---:|
| `ref.embargo_ibama` | legado | 110.377 | 70,1 | 1,9 |
| `ref.unidade_conservacao` | legado | 3.301 | 66,3 | 3,7 |
| `ref.terra_indigena` | legado | 665 | 31,5 | 1,3 |
| `geo.bioma` | legado | 6 | 11,3 | 0,7 |
| `ref.territorio_quilombola` | legado | 540 | 3,9 | 0,2 |
| `geo.municipio` | legado | 5.571 | 0,7 | 0,0 |
| `geo.uf` | legado | 27 | 0,3 | 0,0 |
| `diag.evidencia` | ausente | não carregada | 0,0 | 0,0 |
| `geo.imovel_car` | ausente | não carregada | 0,0 | 0,0 |
| `cad.area_producao` | ausente | não carregada | 0,0 | 0,0 |
| `cad.imovel` | ausente | não carregada | 0,0 | 0,0 |
| `cad.produtor` | ausente | não carregada | 0,0 | 0,0 |
| `diag.conferencia_ab_s` | ausente | não carregada | 0,0 | 0,0 |
| `diag.resultado_imovel` | ausente | não carregada | 0,0 | 0,0 |
| `ref.lista_suja` | legado | não carregada | 0,0 | 0,0 |
| `cad.carteira` | ausente | não carregada | 0,0 | 0,0 |
| `cad.carteira_item` | ausente | não carregada | 0,0 | 0,0 |
| `cad.consentimento` | ausente | não carregada | 0,0 | 0,0 |
| `cad.documento_trazido` | ausente | não carregada | 0,0 | 0,0 |
| `cad.organizacao` | ausente | não carregada | 0,0 | 0,0 |
| `cad.produtor_imovel` | ausente | não carregada | 0,0 | 0,0 |
| `cad.usuario` | ausente | não carregada | 0,0 | 0,0 |
| `diag.criterio` | ausente | não carregada | 0,0 | 0,0 |
| `diag.execucao` | ausente | não carregada | 0,0 | 0,0 |
| `diag.execucao_carga` | ausente | não carregada | 0,0 | 0,0 |
| `meta.carga` | ausente | não carregada | 0,0 | 0,0 |
| `meta.descarte` | ausente | não carregada | 0,0 | 0,0 |
| `meta.fonte` | ausente | não carregada | 0,0 | 0,0 |
| `meta.validacao` | ausente | não carregada | 0,0 | 0,0 |
| **Total das tabelas** | | | **184,8** | 8,2 |

## Perfil completo

| Tabela | Origem | Linhas | MB | Segundos |
|---|---|---:|---:|---:|
| `ref.desmatamento_prodes` | legado | 1.493.882 | 1.551,4 | 50,6 |
| `ref.alerta_deter` | legado | 247.970 | 212,6 | 6,3 |
| `ref.embargo_ibama` | legado | 110.377 | 144,3 | 6,2 |
| `ref.unidade_conservacao` | legado | 3.301 | 66,3 | 4,4 |
| `ref.terra_indigena` | legado | 665 | 31,5 | 1,8 |
| `geo.bioma` | legado | 6 | 11,3 | 0,7 |
| `ref.territorio_quilombola` | legado | 540 | 3,9 | 0,2 |
| `ref.quilombola_incra` | legado | 446 | 3,6 | 0,2 |
| `ref.quilombola_ibge` | legado | 495 | 3,4 | 0,3 |
| `geo.municipio` | legado | 5.571 | 0,7 | 0,0 |
| `geo.uf` | legado | 27 | 0,3 | 0,0 |
| `diag.evidencia` | ausente | não carregada | 0,0 | 0,0 |
| `geo.imovel_car` | ausente | não carregada | 0,0 | 0,0 |
| `cad.area_producao` | ausente | não carregada | 0,0 | 0,0 |
| `cad.imovel` | ausente | não carregada | 0,0 | 0,0 |
| `cad.produtor` | ausente | não carregada | 0,0 | 0,0 |
| `diag.conferencia_ab_s` | ausente | não carregada | 0,0 | 0,0 |
| `diag.resultado_imovel` | ausente | não carregada | 0,0 | 0,0 |
| `ref.lista_suja` | legado | não carregada | 0,0 | 0,0 |
| `cad.carteira` | ausente | não carregada | 0,0 | 0,0 |
| `cad.carteira_item` | ausente | não carregada | 0,0 | 0,0 |
| `cad.consentimento` | ausente | não carregada | 0,0 | 0,0 |
| `cad.documento_trazido` | ausente | não carregada | 0,0 | 0,0 |
| `cad.organizacao` | ausente | não carregada | 0,0 | 0,0 |
| `cad.produtor_imovel` | ausente | não carregada | 0,0 | 0,0 |
| `cad.usuario` | ausente | não carregada | 0,0 | 0,0 |
| `diag.criterio` | ausente | não carregada | 0,0 | 0,0 |
| `diag.execucao` | ausente | não carregada | 0,0 | 0,0 |
| `diag.execucao_carga` | ausente | não carregada | 0,0 | 0,0 |
| `meta.carga` | ausente | não carregada | 0,0 | 0,0 |
| `meta.descarte` | ausente | não carregada | 0,0 | 0,0 |
| `meta.fonte` | ausente | não carregada | 0,0 | 0,0 |
| `meta.validacao` | ausente | não carregada | 0,0 | 0,0 |
| **Total das tabelas** | | | **2.030,0** | 71,1 |

## Linhas do legado fora da chave

Enquanto a fonte não grava no lago, `lago.ler` entrega o arquivo antigo sem a validação do contrato. O carregador deixa de fora as linhas com chave nula ou repetida (o banco não as aceitaria):

- `ref.desmatamento_prodes`: 1726

## Observações

- "Não carregada": a tabela ainda não está no lago ou o legado não tem as colunas do contrato (`ref.lista_suja` espera `chave_registro`, que a fonte passa a gravar ao migrar para o lago). Ocupa só o espaço vazio (índices e catálogo).
- `cad`, `diag`, `meta` e `geo.imovel_car` ainda não têm dados reais. Com uma carteira real, o lite cresce pouco: o peso está nas geometrias das camadas públicas.
- O completo inclui o PRODES do Brasil inteiro, lido do legado `data/processed/inpe_prodes/`.
