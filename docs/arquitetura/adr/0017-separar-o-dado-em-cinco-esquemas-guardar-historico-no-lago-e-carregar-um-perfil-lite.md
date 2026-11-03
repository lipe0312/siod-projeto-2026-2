# Separar o dado em cinco esquemas, guardar o histórico no lago Parquet e carregar um perfil lite no banco

Situação: **decidido em 03/11/2026**. Complementa o [ADR 0011](0011-persistir-em-parquet-por-uf-e-adiar-o-postgis.md), sem substituí-lo: o Parquet continua sendo o contrato entre etapas, e o banco continua sendo carregado a partir dele. Plano de execução em [`docs/plans/persistencia-plano.md`](../../plans/persistencia-plano.md).

## Context and Problem Statement

Em 03/11/2026, toda fonte pública já virava Parquet tratado em `data/processed/`, mas faltavam três coisas.

* **Sem histórico.** Cada execução sobrescrevia o arquivo, e `procedencia_fontes.json` guardava só a última carga. Não dava para dizer o que mudou de um mês para o outro, nem reproduzir uma ficha antiga com os dados da época.
* **Fora de tabela.** SICAR, AB+S, fichas e carteira ficavam como cache bruto ou como HTML e JSON soltos.
* **Sem separação entre dado geral e dado cadastral.** O dado geral é público e igual para qualquer cliente. O dado cadastral é da cooperativa: produtor, imóvel atendido, consentimento.

O banco gratuito tem limite de espaço: 500 MB no Supabase e 1 GB por projeto no Neon (ADR 0011). O PRODES do Brasil, sozinho, foi estimado em cerca de 1,2 GB.

## Considered Options

* Carregar tudo no banco já, com o recorte por UF
* Manter o Parquet como está e adiar a separação para quando houver banco
* Separar já em esquemas no lago Parquet, com histórico por tipo de fonte, e carregar no banco só um perfil que caiba no plano gratuito

## Decision Outcome

Chosen option: "Separar já em esquemas no lago Parquet e carregar um perfil lite", because resolve agora o histórico e a separação, sem custo, e deixa o banco como uma cópia que pode ser refeita a qualquer momento a partir do lago.

**Cinco esquemas**, iguais no lago (`data/lago/<esquema>/<tabela>/`) e no banco:

| Esquema | O que guarda |
|---|---|
| `meta` | Catálogo de fontes, cargas (URL, data, SHA-256, contagens), validações e descartes |
| `geo` | Base territorial: UF, município, bioma e o imóvel do CAR consultado |
| `ref` | Fontes públicas de restrição: embargo, DETER, PRODES, Lista Suja, terra indígena, UC, quilombola |
| `cad` | Cadastro do cliente: organização, usuário, produtor, imóvel, área de produção, documento trazido, consentimento, carteira |
| `diag` | Resultado: execução, resultado por imóvel, critério, evidência e conferência com o AB+S |

Regras:

1. **`ref` e `geo` nunca apontam para `cad`.** O cruzamento é por geometria ou por `documento_hash`. A ligação fica só em `diag.evidencia`, que guarda a fonte, o registro e a carga.
2. **Nenhum CPF ou CNPJ em claro**, também em `cad` (ADR 0002). O produtor é identificado pelo código da cooperativa e pelo `documento_hash`.
3. **Contrato por tabela** em `contratos/<esquema>/<tabela>.yaml`: colunas, tipos, chave, histórico e perfil do banco. O pipeline valida o DataFrame contra ele antes de gravar, e o DDL do banco é gerado dele.
4. **Histórico conforme o ritmo da fonte:**

   | Tipo | Como funciona | Fontes |
   |---|---|---|
   | Fotografia | Cópia nova só quando o conteúdo muda | UF, município, bioma, TI, UC, quilombolas |
   | Validade por registro | `valido_de` e `valido_ate` em cada registro | Embargo do IBAMA, Lista Suja |
   | Acréscimo | Novo registro entra; registro alterado é regravado | DETER, PRODES por UF |
   | Por consulta | Uma versão por consulta | SICAR, AB+S |
5. **Perfil do banco** declarado no contrato:
   * `lite` cabe no plano gratuito: `meta`, `geo`, `cad`, `diag`, as camadas pequenas que quase não mudam e o embargo sem geometria.
   * `completo` acrescenta DETER, PRODES e as geometrias do embargo.
   * `fora` nunca vai ao banco.
6. **O cálculo espacial roda no lago.** O banco lite recebe o resultado e a geometria da interseção, não as camadas pesadas. SICAR, AB+S e a malha municipal continuam consultados na hora.
7. **Segurança por linha** em `cad` e `diag` por `current_setting('app.organizacao_id')`. É Postgres puro e vale no Neon, no Supabase e no Postgres local.

### Consequences

* Good, because o "o que mudou desde o mês passado" passa a ser uma comparação entre cargas e execuções guardadas, e não entre arquivos sobrescritos.
* Good, because o banco é descartável: `python -m pipeline.armazenamento.banco` o refaz a partir do lago, no Neon, no Supabase ou no Docker local.
* Good, because `meta`, `geo` e `cad` servem a outro projeto do agro sem mudança. Um projeto novo acrescenta o próprio esquema (por exemplo, `mercado` para o CEPEA) com o mesmo formato de contrato.
* Bad, because o lago ocupa mais disco: guarda versões em vez de uma cópia só.
* Bad, because DETER e PRODES ficam fora do banco lite. Uma API sobre o lite não consegue refazer o cruzamento sozinha; mostra o que o pipeline já calculou.
