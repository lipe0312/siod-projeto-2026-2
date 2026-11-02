# PRODES em lote pelo arquivo do bioma (02/11/2026)

Decisão no [ADR 0015](../../../arquitetura/adr/0015-montar-o-prodes-e-o-deter-do-pantanal-pelo-arquivo-do-terrabrasilis.md). Regerar, da raiz:

```bash
.venv/bin/python -m pipeline --fontes prodes --evidencia docs/evidencias/atividade-04/prodes-arquivo
.venv/bin/python docs/evidencias/atividade-04/prodes-arquivo/01_comparar_wfs_e_arquivo.py
```

| Arquivo | O que é |
|---|---|
| `execucao_20261102_150109.*` | Carga das 27 UFs a partir dos seis arquivos: 245 s, pico de 4,8 GB de memória |
| `manifesto.json` | Cópia de `data/raw/inpe_prodes/arquivo_bioma/manifesto.json`: por bioma, URL, versão, SHA-256 e tamanho do arquivo, último ano, polígonos por ano, UFs que toca e histórico |
| `inpe_prodes_publicacao.json` | Cópia do que o pré-diagnóstico lê, no mesmo formato do lote pelo WFS, mais a versão de cada arquivo |
| `01_comparar_wfs_e_arquivo.py` | Compara, UF por UF, o lote pelo WFS de 01/11/2026 (cópia em `data/processed/inpe_prodes_wfs_20261101/`) com o lote pelo arquivo |
| `01_comparacao.md`, `01_comparacao.csv` | Saída do script |

## Por que não era erro de conexão

A carga pelo WFS das 8 UFs (30/10 a 01/11/2026, `data/logs/prodes_ufs_demonstracao.log`) registra 287 avisos de falha: HTTP 502 do gateway, `ReadTimeout`, `ConnectionError` e `ChunkedEncodingError`. Cada um custa uma nova tentativa ou a divisão do retângulo em quatro. O serviço responde, mas é lento e instável em respostas grandes: PA levou 7,9 h e MT, 5,1 h. Repetir a carga não resolveria. A saída foi outra fonte do mesmo dado.

## Arquivos (catálogo do TerraBrasilis, 02/11/2026)

| Bioma | Versão | Tamanho | Polígonos desde 2019 | Descartados | UFs |
|---|---|---:|---:|---:|---:|
| Amazônia | 16/10/2026 | 414 MB | 358.162 | 0 | 9 |
| Caatinga | 05/08/2026 | 826 MB | 414.383 | 5.608 | 10 |
| Cerrado | 16/10/2026 | 753 MB | 513.989 | 0 | 13 |
| Mata Atlântica | 06/08/2026 | 451 MB | 152.176 | 887 | 15 |
| Pampa | 07/08/2026 | 92 MB | 45.887 | 393 | 1 |
| Pantanal | 17/07/2026 | 17 MB | 9.413 | 0 | 2 |
| **Total** | | **2,6 GB** | **1.494.010** | | |

Os descartados são de classe fora do domínio (ex.: `RESERVATORIO`). Os polígonos de divisa entram nas duas UFs. Por isso as 27 partições somam 1.495.608 linhas e 616 MB.

## Conferência

1. **Contagem por ano:** idêntica à do WFS no Brasil (manifesto do lote pelo WFS de 30/10/2026) nos 44 pares bioma x ano.
2. **As 8 UFs que já estavam no lote** (`01_comparacao.md`):
   * 637.415 polígonos estão nos dois lotes;
   * 14 estão só no WFS e 5 só no arquivo, todos na borda da UF, onde a geometria arredondada toca ou deixa de tocar o contorno;
   * ano PRODES, data da imagem e bioma são 100% iguais; a UF, 99,98% ou mais.
3. **Precisão:** o WFS devolve coordenadas com 4 casas decimais (~11 m). Com isso:
   * 64.328 polígonos viraram `GEOMETRYCOLLECTION` depois do `make_valid`;
   * a área difere mais de 10% em 24.227;
   * a diferença mediana de área é de 1,2% a 2,4%, conforme a UF.

   O arquivo tem precisão completa, gravada com 6 casas (~0,1 m).
4. **Codificação:** os DBF da Amazônia e do Cerrado estão em latin1. Lidos em UTF-8, "MARANHÃO" virava UF inválida em 300.454 polígonos do Cerrado. Isso foi corrigido antes da carga final (`PRODES_DBF_LATIN1`).
5. **Demonstração:** os 17 imóveis conferem com o lote novo. GO, MA, TO e MT, consultados por coordenada, saíram em 1,8 a 2,8 s cada, sem download.
6. **Verificação mensal:** a segunda execução, no mesmo dia, levou 5 s e não foi à rede.

## Partições por UF

| UF | Biomas | Polígonos | Parquet |
|---|---|---:|---:|
| AC | Amazônia | 45.625 | 20,8 MB |
| AL | Caatinga, Mata Atlântica | 5.986 | 2,1 MB |
| AM | Amazônia | 47.035 | 23,4 MB |
| AP | Amazônia | 3.713 | 1,2 MB |
| BA | Caatinga, Cerrado, Mata Atlântica | 166.705 | 62,6 MB |
| CE | Caatinga | 127.175 | 54,7 MB |
| DF | Cerrado | 659 | 0,2 MB |
| ES | Mata Atlântica | 5.402 | 1,6 MB |
| GO | Cerrado, Mata Atlântica | 57.800 | 21,0 MB |
| MA | Amazônia, Caatinga, Cerrado | 187.363 | 78,7 MB |
| MG | Caatinga, Cerrado, Mata Atlântica | 125.814 | 44,1 MB |
| MS | Cerrado, Mata Atlântica, Pantanal | 18.826 | 9,3 MB |
| MT | Amazônia, Cerrado, Pantanal | 69.045 | 32,5 MB |
| PA | Amazônia, Cerrado | 171.017 | 76,5 MB |
| PB | Caatinga, Mata Atlântica | 31.827 | 12,1 MB |
| PE | Caatinga, Mata Atlântica | 51.396 | 20,6 MB |
| PI | Caatinga, Cerrado | 105.913 | 37,8 MB |
| PR | Cerrado, Mata Atlântica | 18.568 | 5,9 MB |
| RJ | Mata Atlântica | 2.022 | 0,6 MB |
| RN | Caatinga, Mata Atlântica | 23.063 | 8,5 MB |
| RO | Amazônia, Cerrado | 32.201 | 14,2 MB |
| RR | Amazônia | 21.475 | 9,0 MB |
| RS | Mata Atlântica, Pampa | 61.969 | 25,9 MB |
| SC | Mata Atlântica | 15.802 | 5,0 MB |
| SE | Caatinga, Mata Atlântica | 7.082 | 2,4 MB |
| SP | Cerrado, Mata Atlântica | 5.476 | 1,5 MB |
| TO | Amazônia, Cerrado | 86.649 | 43,9 MB |
