# Plano — Persistência do AgroValid: lago Parquet com histórico e banco lite

## Contexto

Hoje toda fonte pública já vira Parquet tratado em `data/processed/`, mas:
- cada execução **sobrescreve** o arquivo (sem histórico) e `procedencia_fontes.json` guarda só a última carga;
- SICAR, AB+S, fichas e carteira não viram tabela (cache bruto ou HTML/JSON soltos);
- não existe separação entre **dado geral** (público, igual para todos) e **dado cadastral** (da cooperativa).

O ADR 0011 decidiu: **Parquet é o contrato entre etapas; o banco (PostgreSQL + PostGIS) é carregado a partir dele, depois, sem custo**; Neon gratuito comporta o recorte por UF, Supabase gratuito só um recorte pequeno; o PRODES do Brasil (~1,2 GB) não cabe. Este plano mantém essa escolha e a completa: organiza o Parquet num **lago com esquemas e histórico**, define o banco com os mesmos esquemas, e cria um **perfil lite** que cabe com folga no Supabase gratuito (500 MB) e no Neon gratuito. As fontes pesadas ou de mudança contínua ficam fora do banco lite: o pipeline continua lendo-as do lago ou consultando o serviço na hora.

Regra central: **o cálculo espacial roda no lago (Python); o banco lite guarda o cadastro, o resultado com a evidência e as camadas pequenas que mudam pouco.**

## 1. Cinco esquemas

| Esquema | Conteúdo | Reuso em outro projeto agro |
|---|---|---|
| `meta` | Catálogo de fontes, cargas (URL, data, SHA-256, contagens), validações e descartes por carga | Igual em qualquer projeto |
| `geo` | Base territorial: UF, município, bioma, imóvel do CAR (só os consultados) | Igual em qualquer projeto |
| `ref` | Fontes públicas de restrição: embargo, DETER, PRODES, Lista Suja, TI, UC, quilombola | Específico do socioambiental; um projeto novo cria o próprio esquema (ex.: `mercado` para CEPEA) |
| `cad` | Organização (cooperativa ou ATER), usuário, produtor, vínculo produtor-imóvel, área de produção, documento trazido, consentimento LGPD, carteira importada | Igual em qualquer projeto com cliente |
| `diag` | Execução, resultado por imóvel, critério, evidência (com a carga e a geometria da interseção), conferência AB+S, visão de mudanças | Específico do AgroValid |

Ligações:
- `ref` e `geo` **nunca** apontam para `cad`. O cruzamento acontece por geometria ou por `documento_hash`, e quem guarda as duas pontas é `diag.evidencia (fonte, registro_id, carga_id)`.
- `cad.produtor` guarda só o `documento_hash` (ADR 0002), com a mesma chave usada no IBAMA e na Lista Suja.
- `cad.imovel` guarda só o `cod_car` e a organização dona; o polígono do imóvel fica em `geo.imovel_car`.
- Segurança por linha em `cad` e `diag` usa `organizacao_id = current_setting('app.organizacao_id')`. É Postgres puro, então funciona no Neon e no Supabase; no Supabase, o JWT preenche a variável depois.

Convenções, em `contratos/LEIA-ME.md`:
- nomes em `snake_case`, em português, sem acento;
- chaves naturais públicas (`cod_car`, `cod_municipio` de 7 dígitos, `cd_cnuc`, `terrai_codigo`, `id_alerta`, `uuid` do PRODES);
- SRID 4674 (o do lago, conferido em `config`);
- `carga_id` em toda linha de `geo` e `ref`;
- datas ISO.

## 2. Histórico por tipo de fonte

| Tipo | Fontes | Como grava no lago |
|---|---|---|
| `fotografia`: nova cópia só quando o SHA-256 do conteúdo muda | `geo.uf`, `geo.municipio`, `geo.bioma`, `ref.terra_indigena`, `ref.unidade_conservacao`, `ref.territorio_quilombola` (INCRA + IBGE; a união vira visão) | `ref/<tabela>/carga=<id>/part.parquet` + visão "vigente" |
| `validade`: `valido_de` e `valido_ate` por registro | `ref.embargo_ibama` (desembargo), `ref.lista_suja` (entra e sai) | Um arquivo de versões, regravado; uma versão nova só quando muda o hash das colunas acompanhadas |
| `acrescimo`: só acrescenta, sem duplicar a chave | `ref.alerta_deter` (por ano), `ref.desmatamento_prodes` (por UF, como hoje) | Partição regravada só quando muda |
| `por_consulta` | `geo.imovel_car` (SICAR), `diag.conferencia_ab_s` | Uma versão por consulta, por UF |

## 3. Perfis do banco e o que fica de fora (versão lite)

Cada contrato declara `perfil_banco: lite | completo | fora`. Atribuição inicial, confirmada pela medição da Fase 5:

| Tabela | Lite (Supabase/Neon gratuitos) | Completo (Postgres local ou pago) |
|---|---|---|
| `meta.*`, `cad.*`, `diag.*` | Sim | Sim |
| `geo.uf`, `geo.bioma`, `geo.municipio`, `geo.imovel_car` | Sim, com geometria | Sim |
| `ref.lista_suja`, `ref.terra_indigena`, `ref.territorio_quilombola`, `ref.unidade_conservacao` | Sim, com geometria (são as fontes que quase não mudam) | Sim |
| `ref.embargo_ibama` | Só atributos, sem geometria (para a consulta por documento) | Com geometria |
| `ref.alerta_deter`, `ref.desmatamento_prodes` | **Fora**: o pipeline lê do lago | Sim |

Fora do banco lite e consultado na hora: SICAR (WFS), AB+S (API), malha municipal do IBGE e PRODES/DETER sob demanda (notebook). O mapa da ficha continua funcionando, porque `diag.evidencia` guarda a geometria da interseção.

Meta de orçamento: **lite ≤ 250 MB** medidos por `pg_total_relation_size`. O script de evidência falha acima de 300 MB.

## 4. Pastas

```
contratos/                 NOVO, sem código, legível por qualquer tecnologia
  LEIA-ME.md               convenções e como criar um esquema novo
  meta/ geo/ ref/ cad/ diag/   um <tabela>.yaml por tabela: chave, colunas, tipos, nulos,
                               geometria, historico, perfil_banco, fonte
banco/                     NOVO, só SQL e infraestrutura
  migracoes/0001_extensoes_e_esquemas.sql  (postgis; esquemas)
            0002_tabelas.sql               (GERADO dos contratos; teste garante que está em dia)
            0003_seguranca_por_linha.sql   (RLS de cad e diag)
            0004_visoes.sql                (*_vigente, quilombola_unificado, diag.mudanca)
  docker-compose.yml       imresamu/postgis:17-3.5, o mesmo da medição do ADR 0011
  LEIA-ME.md               subir local; ligar Neon ou Supabase por AGROVALID_DATABASE_URL
pipeline/
  fontes/                  já existe; passa a gravar pelo armazenamento
  armazenamento/           NOVO
    contratos.py           lê o YAML, valida o DataFrame, gera schema pyarrow e DDL
    lago.py                caminhos, gravar(tabela, df, carga), ler_vigente(tabela, uf=None)
    cargas.py              meta.carga, hash de conteúdo, validações, descartes
    historico.py           fotografia, validade, acréscimo
    banco.py               lago → Postgres via COPY, perfil lite ou completo (só com a variável de ambiente)
data/                      não versionado
  raw/                     bruto, sem mudança
  lago/<esquema>/<tabela>/ tratado, com contrato e histórico (substitui data/processed)
  saidas/                  HTML e MD para pessoas: fichas/, carteiras/<org>/<AAAA-MM>/
  logs/                    logs e relatórios de execução
```

Dependências novas, versões fixadas em `requirements.txt`: `psycopg[binary]` e `PyYAML`. Sem DuckDB nem ORM.

Exemplo de contrato (`contratos/ref/embargo_ibama.yaml`):
```yaml
tabela: ref.embargo_ibama
fonte: ibama_embargos
chave: [id_embargo]
historico: validade
acompanhar: [situacao, data_desembargo, area_ha, geometria]
perfil_banco: lite
geometria: {coluna: geometria, tipo: MultiPolygon, srid: 4674, perfil_minimo: completo}
colunas:
  - {nome: id_embargo, tipo: texto, nulo: false}
  - {nome: documento_hash, tipo: texto}
  # ... as colunas atuais do parquet
```

## 5. Fases, ordem e paralelismo

**Fase 0. Decisão e contratos (sequencial, eu).**
- ADR 0017 ("Separar em cinco esquemas, guardar histórico no lago e carregar um perfil lite"); o ADR 0011 ganha a linha "complementada pela 0017".
- Este plano copiado em `docs/plans/persistencia-plano.md`.
- `contratos/` completo: os contratos de `ref` e `geo` saem dos esquemas atuais dos Parquet; os de `cad` e `diag` saem da ficha JSON (`criterios[]`: chave, criterio_ab_s, situacao, evidencia, encaminhamento, fonte, aviso) e de `docs/visao-do-produto.md` §3.

**Fase 1. Fundação do armazenamento (sequencial, eu; bloqueia o resto).**
- `pipeline/armazenamento/` (contratos, lago, cargas, historico), com testes.
- `ResultadoFonte` (`pipeline/validacao.py`) vira linha de `meta.carga` e de `meta.validacao`. `atualizar_procedencia` (`pipeline/__main__.py`) passa a gravar `meta.carga` com histórico. O JSON continua sendo gerado, por compatibilidade.
- `ler_vigente` devolve as mesmas colunas dos Parquet de hoje, mais `carga_id`, para a troca nos leitores ser de uma linha.

**Fase 2. Fontes no lago (paralelo, 3 agentes em worktrees separadas).** Cada um mexe só nos próprios módulos de `pipeline/fontes/` e nos testes deles, sem tocar em `armazenamento/`.
- **A, validade:** `ibama_embargos.py`, `mte_lista_suja.py`.
- **B, acréscimo:** `inpe_deter.py`, `inpe_prodes.py` (`arquivo_uf` e `ARQ_DESCARTADOS` passam para o lago).
- **C, fotografia:** `municipios.py`, `territorio.py`, `funai_terras_indigenas.py`, `mma_unidades_conservacao.py`, `ibge_territorios_quilombolas.py`, `incra_quilombolas.py`.

**Fase 3. Banco (paralelo à Fase 2, 1 agente).** Depende só dos contratos.
- `banco/` completo: migrações, gerador de DDL, docker-compose, RLS e visões.
- `pipeline/armazenamento/banco.py` com `--perfil lite|completo`.
- Testes de geração e de RLS, que rodam só com o Docker de pé (marca `banco`, como a `rede`).

**Fase 4. Leitores, cadastro e diagnóstico (sequencial, eu, depois da 2).** Arquivos compartilhados; paralelizar aqui só gera conflito.
- Trocar as 34 leituras de `DADOS_PROCESSADOS` por `lago.ler_vigente`: `prediagnostico.py:544`, `carteira.py`, `cruzamento.py`, `territorio.py`, `notebooks/02_fontes_antes_e_depois.ipynb`. Os scripts de evidência antigos ficam como estão, porque registram como era.
- SICAR passa a gravar em `geo.imovel_car`.
- A ficha vira `diag.resultado_imovel`, `diag.criterio` e `diag.evidencia`. `para_json` e `ficha_html` continuam gerando HTML e MD em `data/saidas/`.
- A carteira grava `cad` (organização, produtor, imóvel, carteira) e `diag.execucao`.
- O AB+S (`fontes/ab_s.py`) grava `diag.conferencia_ab_s`.
- A visão `diag.mudanca` (últimas duas execuções por imóvel) também no lago, para o "o que mudou".

**Fase 5. Rotina, orçamento e documentação (sequencial, eu).**
- `agendamento/rotina_mensal.sh`: uma etapa final de carga no banco, só se `AGROVALID_DATABASE_URL` existir.
- `docs/evidencias/persistencia/01_orcamento_banco.py` (tamanho por tabela no lite e no completo) e `02_regressao_lago.py` (os 17 imóveis com o mesmo resultado de antes).
- Documentação: `arquitetura.md` v5 (persistência definida), README (reprodução e próximos passos), `visao-do-produto.md` §5.
- Limpeza de `inpe_prodes.parquet` e `inpe_prodes_wfs_20261101/`, só depois de você confirmar.
- Ligar o Neon ou o Supabase de verdade **só com a sua confirmação**, porque é um envio para serviço externo. Os dados de teste em `cad` são sintéticos.

**Revisão independente (1 agente, no fim).** `/code-review` sobre o diff inteiro, sem a minha conclusão.

Resumo dos agentes: **não são obrigatórios**. Tudo roda em série. O ganho real está na **onda das Fases 2 e 3**: são 4 frentes independentes depois da Fase 1, em worktrees separadas, que eu integro na Fase 4. As Fases 0, 1, 4 e 5 ficam comigo, porque mexem em arquivos compartilhados.

```
F0 → F1 → ┬ F2-A ┐
          ├ F2-B ├→ F4 → F5 → revisão
          ├ F2-C ┤
          └ F3 ──┘
```

Commits: um por fase, mensagem no padrão "Persistência: …", **sem a linha Co-Authored-By** (memória do repositório).

## 6. Verificação

1. `python -m pytest` (sem rede). Testes novos cobrem:
   - fotografia sem mudança não cria carga nova;
   - validade fecha a versão anterior;
   - acréscimo não duplica a chave;
   - DataFrame fora do contrato falha;
   - `0002_tabelas.sql` em dia com os contratos.
2. `python -m pipeline` completo: `data/lago/` populado. Rodando de novo sem mudança na fonte, nenhuma carga nova é criada em `fotografia`.
3. `python -m pipeline.prediagnostico --demo --sem-baixar-prodes`: os 17 imóveis com a mesma situação por critério de `docs/evidencias/atividade-04/prediagnostico/*.json` (script 02).
4. `docker compose -f banco/docker-compose.yml up -d`, depois `python -m pipeline.armazenamento.banco --perfil lite`, depois `pytest -m banco`:
   - carga sem erro;
   - uma organização não enxerga a carteira da outra (RLS);
   - `diag.mudanca` aponta o critério alterado num caso sintético.
5. Script 01: lite ≤ 250 MB, com a tabela por tabela registrada em evidência.
6. `agendamento/rotina_mensal.sh` à mão, terminando com código 0.
