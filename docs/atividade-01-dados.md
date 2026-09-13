# Atividade 01 — Caracterização e avaliação inicial dos dados do projeto

Análise feita em 13/09/2026. Os números abaixo vêm do notebook [`notebooks/01_exploracao_dados.ipynb`](../notebooks/01_exploracao_dados.ipynb) e se referem ao arquivo do IBAMA baixado nessa data (SHA-256 `8eaf1ba8…d322`). As bases são atualizadas continuamente, então os valores mudam a cada nova execução.

## 1. Fonte de dados

O projeto precisa identificar três tipos de pendência que bloqueiam produtores rurais no crédito rural e na venda para compradores sujeitos à EUDR: embargo ambiental, desmatamento após 31/12/2020 e trabalho análogo ao de escravo.

- **Fonte principal:** Áreas Embargadas do IBAMA. Foi usada a **base completa**, não uma amostra.
- **Fontes complementares:**
  - alertas de desmatamento do INPE (DETER e PRODES);
  - Cadastro de Empregadores do Ministério do Trabalho ("Lista Suja");
  - indicadores de preço do CEPEA, para expressar em reais o que está em jogo.

As bases contêm CPF, CNPJ e nomes. Por isso nenhum arquivo de dados é versionado (a pasta `data/` está no `.gitignore`), e o notebook não exibe identificadores pessoais.

## 2. Caracterização da fonte

**Áreas Embargadas (IBAMA)**

| Item | Descrição |
|---|---|
| Origem e responsável | IBAMA. São os termos de embargo lavrados pela fiscalização ambiental federal. |
| Acesso | Download direto do CSV em `servicos.ibama.gov.br`, sem cadastro nem autenticação. Também listado no portal de dados abertos do IBAMA. |
| Formato e estrutura | CSV com separador `;`, codificação UTF-8 (não declarada pelo servidor), 36 colunas. A geometria da área embargada vem como texto WKT. |
| Dimensão | 148 MB; 91.197 registros; 67.460 responsáveis distintos (CPF/CNPJ); 3.793 municípios; de 1987 a 2026. São 24.690 embargos posteriores a 31/12/2020. |
| Periodicidade | Contínua. O arquivo analisado foi modificado em 12/09/2026, e entre 10/09 e 13/09/2026 a base passou de 91.154 para 91.197 registros. |
| Restrições | Dado público pela Lei de Acesso à Informação, mas com dados pessoais sujeitos à LGPD. O uso fica restrito à finalidade do projeto, sem redistribuir o arquivo bruto. |

**Fontes complementares**

| Fonte | Acesso | Formato | Dimensão (13/09/2026) | Periodicidade | Restrições |
|---|---|---|---|---|---|
| INPE DETER (Amazônia) | Serviço WFS do TerraBrasilis, sem autenticação | GeoJSON | 457.815 alertas; 259.934 desde 2021; 14.030 em 2026; último em 04/09/2026 | Contínua (Amazônia e Cerrado) | Citar a fonte |
| INPE PRODES | Mesmo serviço WFS | GeoJSON / shapefile | Camadas de desmatamento anual para Amazônia, Cerrado, Caatinga, Mata Atlântica, Pampa e Pantanal | Anual | Citar a fonte |
| MTE Lista Suja | PDF público, extraído com a biblioteca `agrobr` | Tabela extraída do PDF | 711 linhas extraídas; 579 registros válidos (567 CPF/CNPJ distintos) | Periódica | Dados pessoais |
| CEPEA | Página pública, lida com a biblioteca `agrobr` | Tabela | Cerca de 15 dias por consulta (café, soja, boi) | Diária | Citar a fonte |

## 3. Avaliação inicial da qualidade

**Valores ausentes.** Município e data estão sempre preenchidos. O CPF/CNPJ falta em 10,1% dos registros e a latitude em 13%. O polígono existe em só 55,4% e o nome do imóvel em 12,2%.

A cobertura é bem melhor nos embargos recentes. Após 31/12/2020, 77,4% têm polígono e 99,7% têm coordenada válida. Na base toda, 15,3% não têm nem polígono nem coordenada válida.

**Duplicidades.** Não há linhas idênticas. Porém 250 registros compartilham número e série de termo com outro registro (105 termos), com data, área e coordenadas diferentes. Ou seja, o número do termo não identifica um registro único.

No campo de bioma há repetição dentro do próprio valor, como "Amazonia, Amazonia" (75 registros) e "Cerrado, Cerrado" (22).

**Inconsistências de formato ou codificação.**
- O arquivo é UTF-8, mas o servidor não informa a codificação. Lido como Latin-1, "Imaruí" vira "ImaruÃ­".
- Datas vêm como texto (`DD/MM/AAAA HH:MM:SS`) e a área usa vírgula decimal.
- Sem instrução de tipo, o CPF/CNPJ é lido como número decimal. Isso apaga o zero à esquerda de 25.490 identificadores e quebra qualquer cruzamento sem aviso.

**Categorias ou nomes com grafias distintas.** O bioma é uma lista em texto livre, sem ordem e sem acento. São 39 valores distintos, que caem para 32 depois de remover repetições, ordenar e acentuar.

**Registros aparentemente incorretos.**
- 3.180 registros com coordenada (0, 0);
- 254 com coordenada fora do Brasil;
- 406 com área embargada zero ou negativa;
- 2 com CPF/CNPJ de tamanho inválido;
- um embargo datado de 25/09/2925.

**Campos relevantes que não estão disponíveis.**
- Não há código do CAR, que ligaria o embargo ao imóvel, e o SICAR não oferece download em massa.
- Nenhuma base informa a cultura do produtor.
- Não há como distinguir desmatamento autorizado de ilegal.

**Fontes complementares.** A Lista Suja, extraída do PDF, traz 44 linhas que repetem o cabeçalho da tabela e 88 sem CPF/CNPJ. Os alertas do DETER incluem degradação, corte seletivo e cicatriz de queimada, não só desmatamento.

## 4. Dicionário mínimo de dados

| Campo | Significado | Tipo | Exemplo | Observação / problema |
|---|---|---|---|---|
| `CPF_CNPJ_EMBARGADO` | Documento do responsável pelo embargo | texto | `01234567890` (fictício) | 10,1% ausente; ler como texto; dado pessoal |
| `COD_MUNICIPIO_TAD` | Código IBGE do município | inteiro (7) | `1505486` | Sempre preenchido; chave de junção com o INPE |
| `DAT_EMBARGO` | Data do termo de embargo | data (texto) | `15/09/2022 10:22:41` | Uma data em 2925 |
| `NUM_LATITUDE_TAD`, `NUM_LONGITUDE_TAD` | Coordenada do embargo | decimal | `-8.010556`, `-61.290278` | 3.180 em (0, 0); 254 fora do Brasil |
| `WKT_GEOM_AREA_EMBARGADA` | Polígono da área embargada | texto (WKT) | `POLYGON((…))` | 44,6% ausente |
| `QTD_AREA_EMBARGADA` | Área embargada, em hectares | decimal (texto) | `48,7716` | Vírgula decimal; 35,1% ausente; 406 ≤ 0 |
| `DES_TIPO_BIOMA` | Bioma | texto | `Mata Atlantica` | 38,1% ausente; 39 grafias |
| `NUM_TAD` + `SER_TAD` | Número e série do termo | texto | `650413` / `C` | Referência da evidência; não é único |
| `view_date` (DETER) | Data da imagem do alerta | data | `2026-09-04` | Permite aplicar o corte de 31/12/2020 |
| `classname` (DETER) | Tipo de alerta | texto | `DESMATAMENTO_CR` | Filtrar classes de desmatamento |
| `mun_geocod` (DETER) | Código IBGE do município | inteiro (7) | `1505486` | Junção com o IBAMA |
| `cpf_cnpj` (Lista Suja) | Documento do empregador | texto | `01234567890` (fictício) | 88 ausentes; dado pessoal |

## 5. Análise exploratória reproduzível

O notebook baixa a base, registra o hash e o cabeçalho HTTP do arquivo e reproduz todos os números deste documento. As instruções de ambiente estão no [README](../README.md). Ele está dividido em partes:

1. **Obtenção** da base do IBAMA.
2. **Leitura correta**: codificação e tipo do CPF/CNPJ.
3. **Dimensão e intervalo temporal**, com os embargos por ano.
4. **Valores ausentes** nos campos relevantes.
5. **Qualidade**: duplicidades, grafias, registros incorretos, cobertura geográfica e campos inexistentes.
6. **Estatísticas do domínio**: embargos após 31/12/2020 por UF, com área total e mediana.
7. **Fontes complementares**: contagem e junção com o DETER, camadas do PRODES, Lista Suja, preços CEPEA e teste de download do SICAR.
8. **Resumo** do que os dados permitem e das fraquezas a tratar.

Resultados que mais pesam para o projeto:
- 98% dos 500 alertas mais recentes do DETER ocorreram em municípios que também têm embargos na base do IBAMA.
- Pará e Amazonas concentram 39% dos embargos posteriores a 2020.
- 51% dos registros válidos da Lista Suja têm CNAE de agropecuária, produção florestal ou pesca.

## 6. Síntese técnica

**Os dados estão disponíveis?** Em grande parte, sim. Embargos do IBAMA, alertas do INPE, Lista Suja e preços do CEPEA são públicos, acessíveis sem autenticação e foram consultados de fato. A base principal é completa e atualizada continuamente. O que não está disponível é tratado a seguir.

**Principal problema da fonte.** O principal problema é a localização e a identificação dos registros. Na base inteira, 44,6% dos embargos não têm polígono e 15,3% não têm nem polígono nem coordenada válida. Soma-se a isso uma armadilha de leitura: o CPF/CNPJ interpretado como número perde o zero à esquerda e compromete o cruzamento sem aviso. Os registros posteriores a 2020, que são os que importam para a EUDR, estão bem mais completos.

**Informação necessária que não está disponível.**
- **Código do CAR:** não aparece nas bases e o SICAR não permite download em massa.
- **Cultura do produtor:** nenhuma base informa.
- **Autorização de supressão:** sem ela não dá para separar desmatamento legal de ilegal.
- **Lista de produtores atendidos:** não existe lista pública de produtores atendidos por técnicos ou cooperativas. A avaliação do sistema vai precisar de uma amostra simulada, declarada como tal.

**A caracterização exige mudança no problema, na hipótese ou no escopo?** Sim, em três pontos.
- **Pré-diagnóstico, não atestado.** Sem CAR e com parte dos registros sem localização, o sistema entrega um pré-diagnóstico com a evidência de cada pendência, e não um atestado de conformidade.
- **Embargo não basta.** A EUDR também veda desmatamento autorizado após 2020, que não gera embargo. Por isso os alertas do INPE, filtrados por classe e data, passam a ser parte central do cruzamento.
- **Geolocalização vira entrada obrigatória.** A localização da área tem de ser informada pelo produtor. Sem ela, o resultado deve ser marcado como inconclusivo.

O README foi atualizado com essas mudanças.

**Principal risco relacionado aos dados.** O risco é atribuir uma pendência ao produtor errado ou deixar de apontar uma pendência real. Isso decorre da falta de CAR, dos registros sem localização e dos identificadores mal lidos. A mitigação prevista:
- validar a leitura e os tipos no pipeline;
- nunca apresentar o resultado como atestado;
- citar a fonte de cada evidência;
- medir a taxa de erro contra uma amostra com gabarito.
