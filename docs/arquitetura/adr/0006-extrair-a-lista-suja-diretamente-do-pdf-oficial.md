# Extrair a Lista Suja diretamente do PDF oficial

## Context and Problem Statement

O Cadastro de Empregadores é publicado só em PDF, com uma tabela que continua por dezenas de páginas e repete, em cada página, dois títulos e o cabeçalho. Na Atividade 01 a leitura foi feita com a biblioteca `agrobr`, que devolveu linhas de cabeçalho como se fossem dados e linhas sem documento, porque só ignora o cabeçalho da primeira página e não reconhece os títulos.

## Considered Options

* Continuar usando a extração da `agrobr` e limpar o resultado depois
* Extrair a tabela diretamente do PDF com `pdfplumber`, classificando cada linha
* Converter o PDF manualmente para planilha a cada atualização

## Decision Outcome

Chosen option: "Extrair a tabela diretamente do PDF com `pdfplumber`, classificando cada linha", because permite identificar com certeza o que é cabeçalho, título de página e registro. Com isso o resultado passou de 711 linhas ambíguas para 579 registros, sem nenhuma linha descartada.

Limpar a saída da `agrobr` depois não recupera a estrutura original das linhas. A conversão manual não é reprodutível. O pipeline também confere se o cabeçalho de cada página continua igual ao esperado, e interrompe a fonte se o layout mudar.

### Consequences

* Good, because a extração fica transparente, testada e independente do parser de terceiros.
* Good, because a data de atualização do cadastro é lida do próprio documento.
* Bad, because uma mudança no layout do PDF exige ajustar o código, e isso será detectado pela validação `LS_CABECALHO_INESPERADO`.
