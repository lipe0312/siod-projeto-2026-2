# Persistir o PRODES em lote e verificar a publicação todo mês

> Atualização de 30/10/2026: o recorte só de MG (regra 1), o filtro pelo campo `state` e a consulta sob demanda fora do recorte (regra 6) foram substituídos pelo [ADR 0013](0013-cobrir-o-brasil-inteiro-sem-aceitar-dado-incompleto-como-limpo.md), que leva o lote ao Brasil inteiro e atribui a UF pelo contorno. O lugar do lote passa a ser o banco do [ADR 0011](0011-persistir-em-parquet-por-uf-e-adiar-o-postgis.md). A verificação mensal (regras 2 a 5) continua valendo.

## Context and Problem Statement

Na Atividade 03, o PRODES era consultado sob demanda, no retângulo de cada imóvel. O último ano publicado, que separa alerta DETER "não confirmado" de "aguardando consolidação" (ADR 0009, regra 2), ficava numa constante (`PRODES_ULTIMO_ANO_PUBLICADO = 2025`), conferida à mão em 14/10/2026. Isso contrariava a regra 5 do ADR 0009: a data de publicação deve vir do próprio serviço.

O PRODES sai uma vez por ano, em data que o INPE não fixa, e um ano já publicado pode ser revisado. Em 30/10/2026, o Cerrado já tinha o ano 2026 publicado (52.934 polígonos no Brasil, 6.220 em MG) e a constante ainda dizia 2025.

## Considered Options

* Manter a consulta sob demanda e atualizar a constante à mão
* Consultar o serviço a cada pré-diagnóstico (contagem por ano) para descobrir o último ano
* Persistir o PRODES do recorte num parquet e verificar a publicação a cada 30 dias, baixando só o que mudou

## Decision Outcome

Chosen option: "Persistir o PRODES do recorte num parquet e verificar a publicação a cada 30 dias", because a fonte fica limpa, validada e com procedência como as outras do lote, e a data de publicação passa a vir do serviço sem custo por consulta.

Regras:
1. Recorte por UF (então `config.PRODES_UFS_LOTE`, só MG; hoje `PRODES_UFS_INICIAIS` mais as UFs que entram, ADR 0013) e anos desde 2019. O Brasil inteiro passa de 50 mil polígonos por ano e bioma; outras UFs entram pela configuração.
2. O último ano publicado de cada bioma é o maior ano com polígono no Brasil, pela contagem do serviço (`resultType=hits`).
3. Dentro de 30 dias da última verificação, a execução não vai à rede. Fora disso, compara a contagem de cada ano e UF com a do manifesto e baixa de novo o ano que mudou, o ano novo e sempre o último ano publicado.
4. A mudança de conteúdo é medida pelo SHA-256 das feições ordenadas pelo `uuid`. O hash da resposta inteira não serve: o GeoServer grava `timeStamp` em cada resposta.
5. Ano consolidado alterado é alerta e fica no histórico. Último ano que recua é erro: o parquet anterior não é substituído.
6. O pré-diagnóstico lê o parquet quando a UF do imóvel está no recorte. Fora dele, consulta sob demanda e descobre o último ano pela contagem. Com dois biomas em volta do imóvel, vale o menor último ano.

### Consequences

* Good, because a primeira verificação já achou o Cerrado 2026, que confirmou 8 alertas de 2025 do caso de Serra do Salitre, antes exibidos como "aguardando consolidação".
* Good, because o pré-diagnóstico não depende mais de rede nem de cache para o PRODES do recorte.
* Good, because cada verificação deixa registro: datas, contagens, datas de imagem por ano e histórico de mudanças.
* Bad, because o parquet do recorte de MG ocupa cerca de 25 MB e cresce com cada UF incluída.
* Bad, because o filtro por UF usa o campo `state` do polígono: um polígono gravado com a UF vizinha, junto à divisa, fica de fora do lote.
* Bad, because uma revisão do INPE pode levar até 30 dias para ser vista. `--verificar-prodes` força a verificação antes disso.
