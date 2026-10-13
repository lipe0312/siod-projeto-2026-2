# Atividade 02 — Pipeline inicial de dados

Execução de referência em 13/09/2026, com o comando `python -m pipeline --atualizar --evidencia docs/evidencias/atividade-02`. Status **ok**, duração de 385,0 s. O relatório completo e o log estão em [`docs/evidencias/`](evidencias/).

## 1. Definição da entrada

As fontes são as analisadas na Atividade 01, mais a lista de municípios do IBGE, que entrou como referência para permitir a junção entre as bases (seção 6).

| Fonte | Tipo | Formato de entrada | Volume nesta versão | Elementos relevantes para o sistema |
|---|---|---|---|---|
| IBAMA — Áreas Embargadas | Tabular | CSV (`;`, UTF-8), 148 MB | Base completa: 91.199 registros, 36 colunas (arquivo de 13/09/2026) | CPF/CNPJ do responsável, número, série e sequencial do termo, data, município e UF, coordenada, área, bioma, polígono, descrição da infração |
| INPE — DETER (Amazônia e Cerrado) | API | GeoJSON do serviço WFS | 233.777 alertas das classes de desmatamento com imagem de 01/01/2021 a 04/09/2026 (Amazônia 146.543, Cerrado 87.234), em 138 requisições mensais | `gid`, classe, data da imagem, município e UF, código IBGE (só Amazônia), área no município, geometria |
| MTE — Cadastro de Empregadores | Documento | PDF, 45 páginas | Documento completo: 714 linhas de tabela, 579 registros (cadastro atualizado em 04/09/2026) | CPF/CNPJ, UF, estabelecimento, CNAE, trabalhadores envolvidos, ano da ação fiscal, datas de decisão e de inclusão |
| IBGE — Municípios | API (referência) | JSON | 5.571 municípios | Código, nome e UF |

## 2. Definição da transformação

O objetivo comum às quatro fontes é chegar a tabelas tipadas, validadas e sem dados pessoais, que as camadas seguintes possam cruzar pelo **código IBGE do município**, pelo **documento pseudonimizado** e pela **geometria**.

**IBAMA (tabular)**
1. Leitura com separador `;`, UTF-8 e todas as colunas como texto, para que nenhum tipo seja inferido (o CPF/CNPJ não perde zeros à esquerda).
2. Seleção das 16 colunas relevantes, remoção de espaços, texto vazio convertido em ausente.
3. Identificador `id_embargo` = número + série + sequencial do termo.
4. CPF/CNPJ reduzido a dígitos, validado por tamanho e dígito verificador e substituído por HMAC-SHA256.
5. Datas convertidas de texto e marcação `pos_corte_eudr` (embargo após 31/12/2020).
6. Nome do município e UF padronizados pela referência do IBGE.
7. Coordenadas e área convertidas em número (a área usa vírgula decimal).
8. Bioma com itens únicos, ordenados e acentuados.
9. Geometria WKT lida e verificada (tipo, limites, validade topológica).
10. Remoção do documento original, do nome do responsável e das colunas não usadas.

**INPE DETER (API)**
1. Uma requisição ao WFS por mês de imagem, sem paginação, filtrando as classes de desmatamento desde 01/01/2021. Cada resposta é gravada compactada, com hash, e registrada em um manifesto.
2. Cada feature GeoJSON vira uma linha: propriedades selecionadas e geometria em WKT com 6 casas decimais.
3. Identificador `id_alerta` = camada + `gid` + hash de (gid, data, município, geometria), porque o `gid` não é único.
4. Datas da imagem e do mês de publicação convertidas de texto.
5. Código IBGE do município: o da fonte, na Amazônia, ou resolvido por nome + UF, no Cerrado, que não traz código.
6. Área do trecho no município (`areamunkm`), em km².

**MTE Lista Suja (documento)**
1. Extração do texto e da tabela de cada página do PDF.
2. Segmentação das linhas em cabeçalho repetido, título de página e registro.
3. Limpeza das quebras de linha dentro das células.
4. CPF/CNPJ validado e substituído por HMAC-SHA256, e o nome do empregador removido.
5. UF, ano, número de trabalhadores e CNAE validados, com a marcação `cnae_agropecuaria` (divisões 01 a 03).
6. Datas de decisão e inclusão convertidas de texto. Quando a célula traz vários períodos, a primeira e a última data vão para colunas separadas.
7. Data de atualização do cadastro lida do próprio documento.

**IBGE Municípios (API, referência)**
1. Lista oficial convertida em tabela `cod_municipio`, `municipio`, `uf`.
2. Chave nome normalizado (sem acento, maiúsculas, só letras e números) + UF.

## 3. Implementação

| Arquivo | Responsabilidade |
|---|---|
| `pipeline/__main__.py` | Linha de comando, ordem de execução, isolamento de falhas por fonte, relatório final |
| `pipeline/config.py` | Endereços das fontes, caminhos e constantes de domínio (UFs, biomas, limites do Brasil, classes DETER) |
| `pipeline/download.py` | Download com procedência (URL, data, cabeçalho HTTP, SHA-256), até 3 tentativas e conferência do tamanho recebido |
| `pipeline/validacao.py` | Registro de cada validação (código, severidade, tratamento, contagens) e coluna de alertas |
| `pipeline/documentos.py` | Dígito verificador de CPF/CNPJ e pseudonimização |
| `pipeline/municipios.py` | Referência do IBGE e resolução de município por nome |
| `pipeline/relatorio.py` | Log em arquivo e relatório JSON/Markdown |
| `pipeline/fontes/ibama_embargos.py` | Fonte tabular |
| `pipeline/fontes/inpe_deter.py` | Fonte API |
| `pipeline/fontes/mte_lista_suja.py` | Fonte documento |
| `tests/` | Um teste por validação, com dados sintéticos |

Execução (instruções de ambiente no [README](../README.md)):

```bash
python -m pipeline                                  # todas as fontes
python -m pipeline --fontes ibama deter lista_suja  # escolher fontes
python -m pipeline --desde 2021-01-01               # início do recorte do DETER
python -m pipeline --atualizar                      # baixar tudo de novo
python -m pipeline --evidencia docs/evidencias/atividade-02      # copiar relatório e log da execução
python -m pytest                                    # testes
```

Toda transformação e toda validação são registradas no log (`data/logs/`) e no relatório (`data/processed/relatorio_execucao.md`). Nenhuma etapa é manual. A única lista escrita à mão é a tabela de apelidos de municípios, que fica no código e é validada a cada execução.

## 4. Validações

São 70 verificações sobre o conteúdo das fontes, cada uma com código, severidade e tratamento fixos:

- **erro:** interrompe a fonte;
- **descarte:** o registro vai para um arquivo de descartados, com o motivo;
- **correção:** o ajuste é determinístico e fica registrado;
- **alerta:** o registro é mantido, o campo inválido é anulado quando for o caso e o código vai para a coluna `alertas`.

A coluna *Ocorrências* vem da execução de referência. Cada verificação é comprovada por um teste automatizado com dados sintéticos (`python -m pytest`: 51 testes, todos passando).

**IBAMA — Áreas Embargadas**

| Código | O que verifica | Severidade | Tratamento | Ocorrências | Teste |
|---|---|---|---|---:|---|
| `IBAMA_COLUNAS_OBRIGATORIAS` | Colunas obrigatórias presentes (ausentes: nenhuma) | erro | interrompe a fonte | 0 de 16 | `test_ibama_embargos.py`: `test_colunas_obrigatorias_ausentes_interrompem` |
| `IBAMA_SEM_REGISTROS` | Arquivo com ao menos um registro | erro | interrompe a fonte | 0 de 1 | `test_ibama_embargos.py`: `test_arquivo_sem_registros_interrompe` |
| `IBAMA_NUMERO_TERMO_AUSENTE` | Registro sem número do termo de embargo | descarte | registro vai para descartados | 0 de 91.199 | `test_ibama_embargos.py`: `test_numero_do_termo_ausente_e_descartado` |
| `IBAMA_ID_DUPLICADO` | id_embargo único | erro | interrompe a fonte | 0 de 91.199 | `test_ibama_embargos.py`: `test_identificador_duplicado_interrompe` |
| `IBAMA_DOC_AUSENTE` | CPF/CNPJ ausente | alerta | registro mantido, sem vínculo por documento | 9.233 de 91.199 | `test_ibama_embargos.py`: `test_documentos_invalidos_sao_anulados` |
| `IBAMA_DOC_TAMANHO_INVALIDO` | CPF/CNPJ sem 11 ou 14 dígitos | alerta | documento anulado | 2 de 91.199 | `test_ibama_embargos.py`: `test_documentos_invalidos_sao_anulados` |
| `IBAMA_DOC_DV_INVALIDO` | CPF/CNPJ com dígito verificador inválido | alerta | documento anulado | 164 de 91.199 | `test_ibama_embargos.py`: `test_documentos_invalidos_sao_anulados` |
| `IBAMA_DATA_EMBARGO_INVALIDA` | Data do embargo fora do formato esperado ou anterior a 1980 | alerta | data anulada | 0 de 91.199 | `test_ibama_embargos.py`: `test_datas_futura_e_invalida_sao_anuladas` |
| `IBAMA_DATA_EMBARGO_FUTURA` | Data do embargo posterior à data de execução | alerta | data anulada | 1 de 91.199 | `test_ibama_embargos.py`: `test_datas_futura_e_invalida_sao_anuladas` |
| `IBAMA_MUNICIPIO_DESCONHECIDO` | Código de município inexistente na referência do IBGE | alerta | mantido com nome e UF da própria base | 17 de 91.199 | `test_ibama_embargos.py`: `test_municipio_desconhecido_e_uf_divergente` |
| `IBAMA_MUNICIPIO_UF_DIVERGENTE` | Código do município pertence a outra UF | alerta | mantido; UF passa a ser a do município no IBGE | 0 de 91.199 | `test_ibama_embargos.py`: `test_municipio_desconhecido_e_uf_divergente` |
| `IBAMA_COORD_INCOMPLETA` | Só latitude ou só longitude preenchida | alerta | coordenada anulada | 1.087 de 91.199 | `test_ibama_embargos.py`: `test_coordenadas_impossiveis_sao_anuladas` |
| `IBAMA_COORD_ZERO` | Coordenada (0, 0) | alerta | coordenada anulada | 3.180 de 91.199 | `test_ibama_embargos.py`: `test_coordenadas_impossiveis_sao_anuladas` |
| `IBAMA_COORD_FORA_BRASIL` | Coordenada fora do retângulo do território brasileiro | alerta | coordenada anulada | 255 de 91.199 | `test_ibama_embargos.py`: `test_coordenadas_impossiveis_sao_anuladas` |
| `IBAMA_AREA_INVALIDA` | Área embargada não numérica | alerta | área anulada | 0 de 91.199 | `test_ibama_embargos.py`: `test_area_nao_positiva_e_texto_invalido` |
| `IBAMA_AREA_NAO_POSITIVA` | Área embargada igual a zero ou negativa | alerta | área anulada | 406 de 91.199 | `test_ibama_embargos.py`: `test_area_nao_positiva_e_texto_invalido` |
| `IBAMA_BIOMA_NORMALIZADO` | Bioma com repetição, ordem variável ou sem acento | correção | itens únicos, ordenados e acentuados | 44.619 de 56.469 | `test_ibama_embargos.py`: `test_bioma_normalizado_e_desconhecido` |
| `IBAMA_BIOMA_DESCONHECIDO` | Bioma fora do domínio conhecido | alerta | item desconhecido removido | 0 de 56.469 | `test_ibama_embargos.py`: `test_bioma_normalizado_e_desconhecido` |
| `IBAMA_GEOM_ILEGIVEL` | WKT que não pode ser lido | alerta | geometria anulada | 1 de 50.524 | `test_ibama_embargos.py`: `test_geometrias_problematicas` |
| `IBAMA_GEOM_TIPO_INVALIDO` | Geometria que não é polígono ou multipolígono | alerta | geometria anulada | 0 de 50.524 | `test_ibama_embargos.py`: `test_geometrias_problematicas` |
| `IBAMA_GEOM_FORA_BRASIL` | Geometria fora do retângulo do território brasileiro | alerta | geometria anulada | 0 de 50.524 | `test_ibama_embargos.py`: `test_geometrias_problematicas` |
| `IBAMA_GEOM_INVALIDA` | Polígono topologicamente inválido (ex.: autointerseção) | alerta | geometria mantida sem correção | 117 de 50.524 | `test_ibama_embargos.py`: `test_geometrias_problematicas` |
| `IBAMA_SEM_VINCULO_NEM_LOCALIZACAO` | Sem documento válido, sem geometria e sem coordenada válida | descarte | registro vai para descartados | 252 de 91.199 | `test_ibama_embargos.py`: `test_sem_vinculo_nem_localizacao_e_descartado` |

**INPE — DETER**

| Código | O que verifica | Severidade | Tratamento | Ocorrências | Teste |
|---|---|---|---|---:|---|
| `DETER_ESTRUTURA_RESPOSTA` | Resposta é FeatureCollection com lista de features | erro | interrompe a fonte | 0 de 138 | `test_inpe_deter.py`: `test_estrutura_de_resposta_invalida_interrompe` |
| `DETER_PARTICAO_INCOMPLETA` | Resposta com menos features do que o próprio serviço anunciou | erro | interrompe a fonte | 0 de 138 | `test_inpe_deter.py`: `test_particao_incompleta_interrompe` |
| `DETER_CRS_INESPERADO` | Sistema de coordenadas diferente de EPSG::4674 (SIRGAS 2000) | erro | interrompe a fonte | 0 de 2 | `test_inpe_deter.py`: `test_crs_inesperado_interrompe` |
| `DETER_CONTAGEM_DIVERGENTE_AMAZONIA` | Alertas recebidos (146543) diferentes do total anunciado no início da coleta (146543) | alerta | segue com o que foi recebido; indica mudança na base durante a coleta | 0 de 1 | `test_inpe_deter.py`: `test_contagem_divergente_gera_alerta` |
| `DETER_CONTAGEM_DIVERGENTE_CERRADO` | Alertas recebidos (87234) diferentes do total anunciado no início da coleta (87234) | alerta | segue com o que foi recebido; indica mudança na base durante a coleta | 0 de 1 | `test_inpe_deter.py`: `test_contagem_divergente_gera_alerta` |
| `DETER_PROPRIEDADE_GID_AUSENTE` | Propriedade 'gid' ausente em todas as features | erro | interrompe a fonte | 0 de 1 | `test_inpe_deter.py`: `test_propriedade_obrigatoria_ausente_interrompe` |
| `DETER_PROPRIEDADE_CLASSNAME_AUSENTE` | Propriedade 'classname' ausente em todas as features | erro | interrompe a fonte | 0 de 1 | `test_inpe_deter.py`: `test_propriedade_obrigatoria_ausente_interrompe` |
| `DETER_PROPRIEDADE_VIEW_DATE_AUSENTE` | Propriedade 'view_date' ausente em todas as features | erro | interrompe a fonte | 0 de 1 | `test_inpe_deter.py`: `test_propriedade_obrigatoria_ausente_interrompe` |
| `DETER_PROPRIEDADE_UF_AUSENTE` | Propriedade 'uf' ausente em todas as features | erro | interrompe a fonte | 0 de 1 | `test_inpe_deter.py`: `test_propriedade_obrigatoria_ausente_interrompe` |
| `DETER_PROPRIEDADE_MUNICIPALITY_AUSENTE` | Propriedade 'municipality' ausente em todas as features | erro | interrompe a fonte | 0 de 1 | `test_inpe_deter.py`: `test_propriedade_obrigatoria_ausente_interrompe` |
| `DETER_GID_AUSENTE` | Feature sem identificador gid | descarte | registro vai para descartados | 0 de 233.777 | `test_inpe_deter.py`: `test_gid_ausente_descartado_e_uf_invalida_marcada` |
| `DETER_GEOM_AUSENTE` | Feature sem geometria legível | descarte | registro vai para descartados | 0 de 233.777 | `test_inpe_deter.py`: `test_descartes_por_classe_data_e_geometria` |
| `DETER_ALERTA_DUPLICADO` | Mesmo gid, data, município e geometria recebidos mais de uma vez | descarte | registro vai para descartados | 0 de 233.777 | `test_inpe_deter.py`: `test_mesmo_gid_em_municipios_diferentes_nao_e_duplicata`, `test_gid_reutilizado_em_outra_data_nao_e_duplicata` |
| `DETER_CLASSE_FORA_DO_RECORTE` | Classe diferente de desmatamento | descarte | registro vai para descartados | 0 de 233.777 | `test_inpe_deter.py`: `test_descartes_por_classe_data_e_geometria` |
| `DETER_DATA_INVALIDA` | Data da imagem ausente ou fora do formato AAAA-MM-DD | descarte | registro vai para descartados | 0 de 233.777 | `test_inpe_deter.py`: `test_descartes_por_classe_data_e_geometria` |
| `DETER_DATA_FORA_DO_RECORTE` | Data da imagem antes de 2021-01-01 ou depois da execução | descarte | registro vai para descartados | 0 de 233.777 | `test_inpe_deter.py`: `test_descartes_por_classe_data_e_geometria` |
| `DETER_GEOM_FORA_BRASIL` | Geometria fora do retângulo do território brasileiro | descarte | registro vai para descartados | 0 de 233.777 | `test_inpe_deter.py`: `test_descartes_por_classe_data_e_geometria` |
| `DETER_UF_INVALIDA` | UF fora das 27 siglas | alerta | mantido | 0 de 233.777 | `test_inpe_deter.py`: `test_gid_ausente_descartado_e_uf_invalida_marcada` |
| `DETER_MUNICIPIO_APELIDO` | Nome de município diferente do oficial (tabela de apelidos) | correção | nome substituído pelo oficial antes de buscar o código | 90 de 233.777 | `test_inpe_deter.py`: `test_mesmo_gid_em_municipios_diferentes_nao_e_duplicata` |
| `DETER_MUNICIPIO_CODIGO_DIVERGENTE` | Código IBGE da fonte diferente do código obtido pelo nome | alerta | mantido o código da fonte | 0 de 146.543 | `test_inpe_deter.py`: `test_alertas_de_municipio_area_e_geometria` |
| `DETER_MUNICIPIO_NAO_IDENTIFICADO` | Município sem código IBGE válido | alerta | código anulado | 0 de 233.777 | `test_inpe_deter.py`: `test_alertas_de_municipio_area_e_geometria` |
| `DETER_AREA_NAO_POSITIVA` | Área ausente, zero ou negativa | alerta | área anulada | 0 de 233.777 | `test_inpe_deter.py`: `test_alertas_de_municipio_area_e_geometria` |
| `DETER_GEOM_INVALIDA` | Polígono topologicamente inválido | alerta | geometria mantida sem correção | 17.841 de 233.777 | `test_inpe_deter.py`: `test_alertas_de_municipio_area_e_geometria` |
| `DETER_GEOMETRIA_REPETIDA` | Mesma classe, data e geometria em gids diferentes | alerta | mantido | 6 de 233.777 | `test_inpe_deter.py`: `test_geometria_repetida_em_gids_diferentes` |

**MTE — Lista Suja**

| Código | O que verifica | Severidade | Tratamento | Ocorrências | Teste |
|---|---|---|---|---:|---|
| `LS_DOCUMENTO_VAZIO` | Nenhum texto extraído do PDF | erro | interrompe a fonte | 0 de 1 | `test_mte_lista_suja.py`: `test_documento_vazio_interrompe` |
| `LS_PAGINA_SEM_TEXTO` | Página sem texto extraível | alerta | página ignorada | 0 de 45 | `test_mte_lista_suja.py`: `test_pagina_sem_texto_gera_alerta` |
| `LS_DATA_ATUALIZACAO_AUSENTE` | Data de atualização do cadastro não encontrada no documento | alerta | campo data_atualizacao_cadastro fica vazio | 0 de 1 | `test_mte_lista_suja.py`: `test_data_de_atualizacao_ausente_gera_alerta` |
| `LS_CABECALHO_INESPERADO` | Cabeçalho da tabela diferente das 10 colunas esperadas | erro | interrompe a fonte | 0 de 45 | `test_mte_lista_suja.py`: `test_cabecalho_inesperado_interrompe` |
| `LS_LINHA_NAO_RECONHECIDA` | Linha que não é cabeçalho, título nem registro | descarte | linha vai para descartados | 0 de 714 | `test_mte_lista_suja.py`: `test_linha_nao_reconhecida_e_descartada` |
| `LS_SEM_REGISTROS` | Nenhum registro extraído do documento | erro | interrompe a fonte | 0 de 1 | `test_mte_lista_suja.py`: `test_documento_sem_registros_interrompe` |
| `LS_ID_DUPLICADO` | ID do registro único | erro | interrompe a fonte | 0 de 579 | `test_mte_lista_suja.py`: `test_id_duplicado_interrompe` |
| `LS_DOC_FORMATO_INVALIDO` | CPF/CNPJ ausente ou sem 11 ou 14 dígitos | alerta | documento anulado | 0 de 579 | `test_mte_lista_suja.py`: `test_documentos_invalidos_e_repetidos` |
| `LS_DOC_DV_INVALIDO` | CPF/CNPJ com dígito verificador inválido | alerta | documento anulado | 0 de 579 | `test_mte_lista_suja.py`: `test_documentos_invalidos_e_repetidos` |
| `LS_DOC_REPETIDO` | Mesmo empregador em mais de um registro | alerta | mantido (estabelecimentos diferentes) | 22 de 579 | `test_mte_lista_suja.py`: `test_documentos_invalidos_e_repetidos` |
| `LS_UF_INVALIDA` | UF ausente ou fora das 27 siglas | alerta | UF anulada | 3 de 579 | `test_mte_lista_suja.py`: `test_registro_incompleto_gera_alertas_e_anula_campos` |
| `LS_ANO_ACAO_INVALIDO` | Ano da ação fiscal ausente ou fora de 1995 até o ano atual | alerta | ano anulado | 3 de 579 | `test_mte_lista_suja.py`: `test_registro_incompleto_gera_alertas_e_anula_campos` |
| `LS_TRABALHADORES_INVALIDO` | Número de trabalhadores ausente ou não inteiro positivo | alerta | valor anulado | 2 de 579 | `test_mte_lista_suja.py`: `test_registro_incompleto_gera_alertas_e_anula_campos` |
| `LS_CNAE_FORMATO_INVALIDO` | CNAE ausente ou fora do formato 9999-9/99 | alerta | CNAE anulado | 3 de 579 | `test_mte_lista_suja.py`: `test_registro_incompleto_gera_alertas_e_anula_campos` |
| `LS_DATA_DECISAO_INVALIDA` | Data da decisão ausente, fora do formato ou futura | alerta | data anulada | 3 de 579 | `test_mte_lista_suja.py`: `test_registro_incompleto_gera_alertas_e_anula_campos` |
| `LS_DATA_INCLUSAO_INVALIDA` | Data de inclusão ausente, fora do formato ou futura | alerta | datas anuladas | 0 de 579 | `test_mte_lista_suja.py`: `test_inclusao_antes_da_decisao_e_data_futura` |
| `LS_INCLUSAO_MULTIPLOS_PERIODOS` | Célula de inclusão com mais de uma data (vários períodos) | correção | primeira e última data extraídas em colunas separadas | 10 de 579 | `test_mte_lista_suja.py`: `test_multiplos_periodos_de_inclusao` |
| `LS_INCLUSAO_ANTES_DA_DECISAO` | Inclusão no cadastro anterior à decisão administrativa | alerta | mantido | 1 de 579 | `test_mte_lista_suja.py`: `test_inclusao_antes_da_decisao_e_data_futura` |

**IBGE — Municípios**

| Código | O que verifica | Severidade | Tratamento | Ocorrências | Teste |
|---|---|---|---|---:|---|
| `IBGE_ESTRUTURA_RESPOSTA` | Resposta da API é uma lista de municípios com id e nome | erro | interrompe IBAMA e DETER, que dependem da referência | 0 de 1 | `test_municipios.py`: `test_estrutura_invalida_interrompe` |
| `IBGE_QUANTIDADE_INESPERADA` | Lista com ao menos 5.500 municípios | erro | interrompe IBAMA e DETER, que dependem da referência | 0 de 1 | `test_municipios.py`: `test_referencia_pequena_interrompe` |
| `IBGE_UF_AUSENTE` | Município sem UF identificável | erro | interrompe IBAMA e DETER, que dependem da referência | 0 de 5.571 | `test_municipios.py`: `test_municipio_sem_uf_interrompe` |
| `IBGE_CODIGO_DUPLICADO` | Código IBGE repetido | erro | interrompe IBAMA e DETER, que dependem da referência | 0 de 5.571 | `test_municipios.py`: `test_referencia_com_codigo_duplicado_interrompe` |
| `IBGE_NOME_UF_DUPLICADO` | Nome normalizado + UF repetido (impede resolver por nome) | erro | interrompe IBAMA e DETER, que dependem da referência | 0 de 5.571 | `test_municipios.py`: `test_nome_e_uf_repetidos_interrompem` |

Além dessas, duas verificações de execução:

- **Download incompleto:** o tamanho recebido é comparado ao `Content-Length` do servidor, com até 3 tentativas antes de falhar (`test_download.py`).
- **Referência indisponível:** se a lista do IBGE não carregar, IBAMA e DETER são registrados como erro, com o motivo (`test_execucao.py`).

## 5. Evidência de execução

Arquivos: [`execucao_20260913_225434.md`](evidencias/atividade-02/execucao_20260913_225434.md) (relatório legível), [`execucao_20260913_225434.json`](evidencias/atividade-02/execucao_20260913_225434.json) (mesmo conteúdo, estruturado) e [`execucao_20260913_225434.log`](evidencias/atividade-02/execucao_20260913_225434.log) (mensagens da execução). Nenhum deles contém CPF, CNPJ ou nome.

| Fonte | Recebidos | Produzidos | Descartados | Com alerta | Principais ocorrências |
|---|---:|---:|---:|---:|---|
| IBAMA | 91.199 | 90.947 | 252 | 14.070 | 9.233 sem CPF/CNPJ; 166 documentos inválidos anulados; 3.180 coordenadas (0, 0); 255 fora do Brasil; 406 áreas não positivas; 117 polígonos inválidos; 1 data no futuro; 44.619 biomas normalizados |
| INPE DETER | 233.777 | 233.777 | 0 | 17.847 | Recebido igual ao anunciado nas duas camadas; 17.841 geometrias inválidas (7,6%); 90 nomes de município corrigidos; `gid` repetido: 1.848 alertas divididos entre municípios no Cerrado e 39.890 `gid` reutilizados por alertas diferentes na Amazônia |
| MTE Lista Suja | 714 linhas | 579 | 0 | 26 | 45 cabeçalhos e 90 títulos removidos; 22 registros de empregadores que aparecem mais de uma vez; 3 registros incompletos; 10 com vários períodos de inclusão |
| IBGE Municípios | 5.571 | 5.571 | 0 | 0 | Nenhuma falha de estrutura ou unicidade |

Saídas: `data/processed/ibama_embargos.parquet`, `inpe_deter_alertas.parquet`, `mte_lista_suja.parquet`, `ibge_municipios.parquet` e os arquivos de descartados. A pasta `data/` não é versionada.

## 6. Atualização da arquitetura

A arquitetura estava sem desenho registrado. A [versão 1](arquitetura/arquitetura.md) define as camadas de fontes de dados e de pipeline com base no que foi implementado, e mantém as demais como previstas. Mudanças em relação ao que se esperava antes da implementação:

- **Uma quarta fonte, de referência (IBGE).** A camada Cerrado do DETER não traz código de município ([ADR 0005](arquitetura/adr/0005-resolver-municipio-dos-alertas-deter-pela-referencia-do-ibge.md)).
- **Coleta do DETER por mês, sem paginação, e alerta identificado pelo conteúdo.** O `gid` não é único ([ADR 0004](arquitetura/adr/0004-coletar-alertas-deter-em-particoes-mensais-e-identificar-pelo-conteudo.md)).
- **Pseudonimização dentro do pipeline.** Dados pessoais não chegam às camadas seguintes ([ADR 0002](arquitetura/adr/0002-pseudonimizar-cpf-cnpj-com-hmac-no-pipeline.md)).
- **Registros inválidos marcados, não removidos.** Só é descartado o que não pode ser vinculado nem localizado ([ADR 0001](arquitetura/adr/0001-marcar-registros-invalidos-e-descartar-so-o-inutilizavel.md)).
- **Extração própria do PDF da Lista Suja,** no lugar da biblioteca usada na Atividade 01 ([ADR 0006](arquitetura/adr/0006-extrair-a-lista-suja-diretamente-do-pdf-oficial.md)).
- **Identificador dos embargos formado por três colunas** ([ADR 0003](arquitetura/adr/0003-identificar-embargos-por-numero-serie-e-sequencial.md)).

## 7. Registro de decisão

**O que a implementação do pipeline revelou sobre o projeto que não estava claro antes?**

A unidade de dado não era a que parecia. O `gid` do DETER não identifica um alerta: no Cerrado ele se repete para trechos do mesmo alerta em municípios vizinhos (1.848 casos) e, na Amazônia, é reutilizado por alertas de datas e lugares diferentes (39.890).
A primeira versão paginava a coleta por `gid` e tratava repetição como duplicata. Com isso, repetia alertas entre páginas e descartava alertas reais. A coleta passou a ser mensal e o identificador passou a depender do conteúdo.
Também ficou claro que o cruzamento entre as bases exige uma quarta fonte, a lista de municípios do IBGE, porque o Cerrado não traz código de município.
Na Lista Suja, os cabeçalhos e registros sem documento vistos na Atividade 01 vinham do parser usado, não do documento.
Por fim, 7,6% das geometrias do DETER são topologicamente inválidas, o que precisa ser tratado antes de qualquer cruzamento espacial, e os servidores das fontes podem interromper downloads sem erro, o que exigiu conferir o tamanho do que foi recebido.

## Documentos novos e alterados

| Arquivo | Situação | Por quê |
|---|---|---|
| `pipeline/` | Novo | Código do pipeline (seção 3) |
| `tests/` | Novo | Comprova cada validação com dados sintéticos (seção 4) |
| `docs/atividade-02-pipeline.md` | Novo | Este documento: entrada, transformação, validações, evidência e decisão |
| `docs/evidencias/atividade-02/execucao_20260913_225434.md`, `.json`, `.log` | Novo | Evidência da execução de referência (seção 5) |
| `docs/arquitetura/adr/0001` a `0006` | Novo | Registro das decisões técnicas que tiveram alternativas reais |
| `docs/arquitetura/arquitetura.md` | Alterado | Estava vazio; agora é a versão 1, com fontes e pipeline definidos (seção 6) |
| `docs/arquitetura/adr/.gitkeep` | Removido | A pasta passou a ter conteúdo |
| `README.md` | Alterado | Tabela das entregas, instruções para reproduzir cada atividade (macOS/Linux e Windows), mapa de arquivos e próximos passos |
| `requirements.txt` | Alterado | Dependências do pipeline e dos testes: `pdfplumber`, `pyarrow`, `shapely`, `pytest` |
| `.gitignore` | Alterado | Ignora `.pytest_cache/` |
