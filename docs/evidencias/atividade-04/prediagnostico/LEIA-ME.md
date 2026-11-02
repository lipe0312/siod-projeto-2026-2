# Pré-diagnóstico: demonstração

Fichas geradas por `python -m pipeline.prediagnostico --demo` para os 17 CARs de `config.CARS_DEMONSTRACAO`, todos imóveis reais:
- 6 do café de MG;
- 1 por bioma no resto do país;
- 4 com sobreposição a área protegida.

O documento do proprietário é um CPF fictício (`prediagnostico.DOCUMENTO_DEMONSTRACAO`). Ele serve para mostrar a Lista Suja verificada sem expor dado pessoal, e não aparece em nenhum arquivo.

| Arquivo | O que é |
|---|---|
| `index.html`, `index.png` | Página da demonstração: avaliação (esperado x obtido por critério), situação do PRODES em lote por UF e um cartão por imóvel |
| `<CAR>.html` | Ficha do imóvel: resultado, como ele se formou, mapa (com terras indígenas, quilombolas e unidades de conservação), linha do tempo diante da data de corte, critérios, evidências e procedência |
| `<CAR>.png` | Print da ficha (Chrome headless, 1200 px de largura) |
| `<CAR>.md` | A mesma ficha em Markdown |
| `<CAR>.json` | A ficha completa, com as evidências em registros (sem geometrias) |
| `01_demonstracao.py` | Gera tudo acima |

## Resultado em 02/11/2026: 17 de 17 conferem

Com as 8 UFs dos imóveis no lote do PRODES (637.429 polígonos).

| CAR | Caso | Resultado |
|---|---|---|
| MG-3148103-6245AC9B… | Desmatamento após 2020 confirmado pelo PRODES | com pendência |
| MG-3166808-A726F93D… | Embargo e 8 alertas DETER de ago./set. 2025, confirmados pelo PRODES Cerrado 2026 | com pendência (embargo e desmatamento) |
| MG-3148103-A0B17B31… | 3 alertas DETER de 21/08/2026, depois do último PRODES publicado | com indício |
| MG-3148103-627F1606… | Embargo e alerta sobre área já suprimida antes | com pendência (embargo) e indício |
| MG-3148103-A63D0A01… | CAR com notificação pendente, embargos e alerta confirmado | 2 pendências e 1 indício |
| MG-3148103-5527FB32… | CAR analisado, nada nas fontes verificadas | sem pendência nas fontes verificadas |
| PA-1505502-D0CAA14A… | Paragominas, Amazônia: polígono PRODES 2021 (imagem de 02/08/2021; a supressão pode ser de antes do corte) | com indício |
| MT-5107925-7B986980… | Sorriso, Cerrado | sem pendência nas fontes verificadas |
| BA-2918407-16899931… | Juazeiro, Caatinga | sem pendência nas fontes verificadas, com aviso "Caatinga sem DETER: sem cobertura de 19/12/2025 até hoje" |
| RS-4317103-9D7ED9AE… | Rosário do Sul, Pampa | sem pendência nas fontes verificadas, com aviso "Pampa sem DETER: sem cobertura de 19/12/2025 até hoje" |
| MS-5003207-620BD0D0… | Corumbá, Pantanal: 4 polígonos PRODES de 2021 a 2025, 342 ha no imóvel | com pendência, com aviso de Pantanal sem DETER desde 12/08/2025 |
| SP-3543402-0381059F… | Ribeirão Preto, Cerrado e Mata Atlântica | sem pendência nas fontes verificadas, com aviso de Mata Atlântica sem DETER desde 14/09/2025 |
| PR-4104808-358E3C8A… | Cascavel, Mata Atlântica, CAR com notificação | com indício (CAR) |
| MS-5006358-72D1C0B4… | Paranhos: CAR inteiro dentro da TI Ypoi/Triunfo (declarada) e de APA | com pendência (terra indígena); APA e CAR como indício |
| PA-1506807-C4579B9B… | Santarém: CAR inteiro dentro do território quilombola Saracura (portaria) | com pendência (quilombola); CAR como indício |
| MG-3164100-799AE47F… | São Pedro do Suaçuí: CAR dentro de APA e com 1,3 ha de PRODES após 2020 | com pendência (desmatamento); APA como indício |
| MG-3160207-F518ED7F… | Santo Antônio do Itambé: CAR dentro do Parque Estadual Pico do Itambé e de APA | com pendência (unidade de conservação) |

O resultado esperado de cada caso está em `config.CARS_DEMONSTRACAO`. Ele foi escrito depois de conferir a evidência de cada ficha: é teste de regressão, não gabarito ([ADR 0012](../../../arquitetura/adr/0012-conferir-o-prediagnostico-com-o-relatorio-ab-s-do-imovel.md)).

O aviso de cobertura usa a última imagem PRODES do bioma **na UF do imóvel**, lida da partição. Exemplo da Mata Atlântica 2025: 16/10 em MG, 14/09 em SP, 29/08 no PR.

Histórico:
- **30/10/2026, Serra do Salitre:** com o PRODES fixo em 2025, os 8 alertas apareciam como "aguardando consolidação" (indício). A verificação mensal achou o Cerrado 2026 publicado, que os confirmou (pendência).
- **31/10/2026, sem baixar UF nova:** com o TerraBrasilis fora do ar, a demonstração rodou com `--sem-baixar-prodes`. Os 9 imóveis de fora de MG saíram com desmatamento inconclusivo ("UF ainda não carregada no lote do PRODES"), nunca "sem ocorrência".
- **01/11/2026:** com as UFs no lote, o desmatamento desses imóveis entrou no esperado.
- **02/11/2026:** depois da correção da classe em minúsculas da Amazônia (PA e MT ganharam 58.099 polígonos, quase todos de 2019 e 2020), o resultado não mudou.

## Como regerar

```bash
.venv/bin/python docs/evidencias/atividade-04/prediagnostico/01_demonstracao.py                       # baixa a UF que faltar
.venv/bin/python docs/evidencias/atividade-04/prediagnostico/01_demonstracao.py --sem-baixar-prodes   # só o que já está no lote
```

O script precisa:
- dos parquets do lote (`python -m pipeline`, com todas as fontes);
- de acesso ao SICAR na primeira vez (depois, as respostas ficam em cache em `data/raw/`);
- sem `--sem-baixar-prodes`, de acesso ao TerraBrasilis para cada UF que ainda não está no lote.

O print exige o Google Chrome; sem ele, o script gera só os HTML, MD e JSON.
