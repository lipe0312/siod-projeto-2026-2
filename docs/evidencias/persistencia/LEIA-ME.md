# Persistência: banco

Medição do banco PostGIS carregado a partir do lago ([ADR 0017](../../arquitetura/adr/0017-separar-o-dado-em-cinco-esquemas-guardar-historico-no-lago-e-carregar-um-perfil-lite.md); [`banco/LEIA-ME.md`](../../../banco/LEIA-ME.md)).

| Arquivo | O que é |
|---|---|
| `01_orcamento_banco.py` | Carrega o perfil lite e o completo, cada um num banco local novo, e mede o tamanho por tabela (`pg_total_relation_size`). Meta: lite ≤ 250 MB; o script falha acima de 300 MB. Só roda em `localhost` |
| `01_orcamento_banco.json` e `.md` | O resultado: tamanho e linhas por tabela, tempo de carga, e se o lite cabe no Supabase e no Neon gratuitos |

## Como regerar

```bash
docker compose -f banco/docker-compose.yml up -d --wait
AGROVALID_DATABASE_URL=postgresql://agrovalid:agrovalid@localhost:5433/postgres \
  .venv/bin/python docs/evidencias/persistencia/01_orcamento_banco.py
docker compose -f banco/docker-compose.yml down
```

O script lê com `lago.ler`: do lago, ou do legado em `data/processed/` enquanto a fonte não grava no lago. A carga completa (PRODES do Brasil, cerca de 1,5 milhão de polígonos) leva alguns minutos.
