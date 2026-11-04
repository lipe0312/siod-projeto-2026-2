# Contratos de dados

Um arquivo YAML por tabela, em `contratos/<esquema>/<tabela>.yaml`. O contrato diz:
- quais colunas a tabela tem, com tipo e se aceitam nulo;
- qual é a chave;
- como o histórico é guardado;
- se a tabela vai ao banco.

O pipeline valida o DataFrame contra o contrato antes de gravar no lago (`pipeline/armazenamento/contratos.py`). As migrações 0002 a 0005 do banco (`banco/migracoes/`) são geradas a partir dos contratos por `python -m pipeline.armazenamento.ddl`.

Os contratos não dependem de Python. Qualquer ferramenta que leia YAML (dbt, um serviço em outra linguagem, uma API) usa a mesma definição. Decisão em [ADR 0017](../docs/arquitetura/adr/0017-separar-o-dado-em-cinco-esquemas-guardar-historico-no-lago-e-carregar-um-perfil-lite.md).

## Esquemas

| Esquema | O que guarda | Pode ser reaproveitado por outro projeto do agro? |
|---|---|---|
| `meta` | Catálogo de fontes, cargas, validações e descartes | Sim |
| `geo` | Base territorial: UF, município, bioma e o imóvel do CAR consultado | Sim |
| `ref` | Fontes públicas de restrição socioambiental | Só se o projeto for socioambiental |
| `cad` | Cadastro do cliente: organização, usuário, produtor, imóvel, consentimento, carteira | Sim |
| `diag` | Resultado do pré-diagnóstico e conferência com o AB+S | Não; é do AgroValid |

`ref` e `geo` nunca apontam para `cad`. A ligação entre o dado público e o cliente fica em `diag.evidencia`.

## Campos do contrato

| Campo | Valores | Para quê |
|---|---|---|
| `tabela` | `esquema.nome` | Nome no lago (`data/lago/esquema/nome/`) e no banco |
| `fonte` | nome do `ResultadoFonte` ou `pipeline` ou `cadastro` | Liga a tabela a `meta.fonte` e a `meta.carga` |
| `chave` | lista de colunas | Identifica o registro; não aceita repetição nem nulo |
| `historico` | `fotografia`, `validade`, `acrescimo`, `por_consulta`, `registro` | Como as versões são guardadas (abaixo) |
| `acompanhar` | lista de colunas | Só em `validade`: abre uma versão nova quando uma delas muda |
| `particao` | coluna | Subpasta `coluna=valor/` no lago (ex.: `uf`, `ano_mes`) |
| `substituir_particao` | `true` | Em `acrescimo`: a partição gravada é a verdade inteira dela (PRODES por UF) |
| `perfil_banco` | `lite`, `completo`, `fora` | `lite` cabe no plano gratuito do Supabase e do Neon; `completo` é o resto; `fora` nunca vai ao banco |
| `geometria` | `{coluna, tipo, srid, perfil_banco}` | A geometria pode exigir um perfil maior que a tabela (o embargo vai ao lite sem geometria) |
| `legado` | arquivo em `data/processed/` | Leitura de transição, enquanto a fonte não grava no lago |
| `colunas` | `{nome, tipo, nulo}` | Tipos: `texto`, `inteiro`, `decimal`, `logico`, `data_hora`, `data`, `json`, `geometria` |

## Histórico

| Tipo | Como grava | Colunas que o lago acrescenta |
|---|---|---|
| `fotografia` | Uma pasta `carga=<id>/` nova só quando o conteúdo muda; `_vigente.json` aponta a atual | `carga_id` |
| `validade` | Um arquivo com todas as versões; registro alterado fecha a versão anterior | `carga_id`, `valido_de`, `valido_ate`, `hash_linha` |
| `acrescimo` | Registro novo entra e registro alterado é regravado. O que some da fonte continua no lago, salvo com `substituir_particao` | `carga_id`, `hash_linha` |
| `por_consulta` | Uma versão por consulta; a vigente é a mais recente por chave | `carga_id`, `consultado_em` |
| `registro` | Linhas próprias do sistema (cadastro e resultado), só acrescentadas | — |

## Convenções

- Nomes em `snake_case`, em português, sem acento.
- Chaves naturais públicas sempre que existirem: `cod_car`/`cod_imovel`, `cod_municipio` com 7 dígitos, `cd_cnuc`, `terrai_codigo`, `id_alerta`, `uuid` do PRODES.
- Identificadores criados pelo sistema (`*_id` em `cad` e `diag`) são UUID em texto.
- Geometria em SIRGAS 2000 (EPSG 4674). No lago fica como WKT (`geometria_wkt`); no banco vira `geometry` com o mesmo SRID.
- `carga_id` tem o formato `<fonte>:<AAAAMMDDTHHMMSS>`.
- **Nenhum CPF ou CNPJ em claro, em nenhum esquema.** Só `documento_hash` (HMAC, ADR 0002).
- Toda tabela de `cad` e `diag` tem `organizacao_id`, usado pela segurança por linha.

## Criar uma tabela ou um esquema novo

1. Escreva `contratos/<esquema>/<tabela>.yaml`. Um esquema novo é só uma pasta nova, por exemplo `mercado/` para o CEPEA.
2. Se for uma fonte nova, acrescente-a em `contratos/fontes.yaml`.
3. No módulo da fonte, grave com `lago.gravar("<esquema>.<tabela>", df, resultado)`.
4. Gere as migrações de novo (`python -m pipeline.armazenamento.ddl`) e rode `python -m pytest`. O teste acusa migração desatualizada.
