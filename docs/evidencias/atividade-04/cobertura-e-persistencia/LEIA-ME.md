# Cobertura nacional, critérios do AB+S e persistência

Medições de 30/10/2026 que sustentam os ADRs [0011](../../../arquitetura/adr/0011-persistir-em-parquet-por-uf-e-adiar-o-postgis.md), [0012](../../../arquitetura/adr/0012-conferir-o-prediagnostico-com-o-relatorio-ab-s-do-imovel.md) e [0013](../../../arquitetura/adr/0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md) e as seções 4 a 7 de [`atividade-04-prediagnostico.md`](../../../atividade-04-prediagnostico.md).

| Arquivo | O que é |
|---|---|
| `01_fontes_criterios_ab_s.py` e `.json` | Testa as fontes candidatas aos critérios 1, 2, 5, 6, 8 e 9 do AB+S: WFS da FUNAI, conjunto CNUC do MMA, formulário do SNCR, camadas do TerraBrasilis e resolução de nome dos servidores do INCRA |
| `fontes/` | Respostas brutas do script 01, cada uma com o `.meta.json` (URL, data UTC, status, SHA-256). A resposta do CKAN do MMA fica em `data/raw/cnuc/`, fora do repositório, porque traz links pessoais de servidores |
| `02_prodes_brasil.py` e `.json` | Polígonos PRODES por bioma e ano no Brasil (`resultType=hits`). Cerrado 2019 e Pampa 2021 aparecem como `erro HTTPError`: o serviço respondeu 502 nas quatro tentativas |
| `03_prediagnostico_brasil.py` e `.json` | Um CAR por bioma, achado pelo ponto com a UF informada, e o pré-diagnóstico pelo código. Os 7 CARs foram achados; as 7 fichas pararam no PRODES sob demanda (HTTP 502). Durante o teste, a contagem do script 02 também consultava o TerraBrasilis |
| `04_persistencia_benchmark.py` e `.json` | A mesma consulta (PRODES, DETER e IBAMA que tocam cada um de 300 CARs de Patrocínio) em Parquet + STRtree, DuckDB spatial e PostGIS: tempo de carga, tempo por consulta, espaço, memória e conferência dos achados |

## Como regerar

```bash
.venv/bin/python docs/evidencias/atividade-04/cobertura-e-persistencia/01_fontes_criterios_ab_s.py
.venv/bin/python docs/evidencias/atividade-04/cobertura-e-persistencia/02_prodes_brasil.py
.venv/bin/python docs/evidencias/atividade-04/cobertura-e-persistencia/03_prediagnostico_brasil.py
docker run -d --rm --name siod-bench-postgis -e POSTGRES_PASSWORD=bench -p 127.0.0.1:55439:5432 imresamu/postgis:17-3.5
.venv/bin/python docs/evidencias/atividade-04/cobertura-e-persistencia/04_persistencia_benchmark.py
docker stop siod-bench-postgis
```

Os scripts 02 e 03 dependem do TerraBrasilis, que respondeu HTTP 502 de forma intermitente em 30/10/2026; rode um de cada vez. O script 04 precisa dos parquets de `python -m pipeline` (com o PRODES) e do SICAR de Patrocínio em cache. A memória do script 04 é o `ru_maxrss` do macOS, em bytes.
