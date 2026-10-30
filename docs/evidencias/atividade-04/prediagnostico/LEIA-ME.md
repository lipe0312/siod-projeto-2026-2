# Pré-diagnóstico: demonstração

Fichas geradas por `python -m pipeline.prediagnostico --demo` para os CARs de `config.CARS_DEMONSTRACAO`. São imóveis reais do recorte de café de MG. O documento do proprietário é um CPF fictício (`prediagnostico.DOCUMENTO_DEMONSTRACAO`), usado para mostrar a Lista Suja verificada sem expor dado pessoal. O CPF não aparece em nenhum arquivo.

| Arquivo | O que é |
|---|---|
| `index.html`, `index.png` | Página da demonstração: avaliação (esperado x obtido por critério), situação do PRODES em lote e um cartão por imóvel |
| `<CAR>.html` | Ficha do imóvel: resultado, como ele se formou, mapa, linha do tempo diante da data de corte, critérios, evidências e procedência |
| `<CAR>.png` | Print da ficha (Chrome headless, 1200 px de largura) |
| `<CAR>.md` | A mesma ficha em Markdown |
| `<CAR>.json` | A ficha completa, com as evidências em registros (sem geometrias) |
| `01_demonstracao.py` | Gera tudo acima |

| CAR | Caso | Resultado |
|---|---|---|
| MG-3148103-6245AC9B… | Desmatamento após 2020 confirmado pelo PRODES | com pendência |
| MG-3166808-A726F93D… | Embargo e 8 alertas DETER de ago./set. 2025, confirmados pelo PRODES Cerrado 2026 | com pendência (embargo e desmatamento) |
| MG-3148103-A0B17B31… | 3 alertas DETER de 21/08/2026, depois do último PRODES publicado | com indício |
| MG-3148103-627F1606… | Embargo e alerta sobre área já suprimida antes | com pendência (embargo) e indício |
| MG-3148103-A63D0A01… | CAR com notificação pendente, embargos e alerta confirmado | 2 pendências e 1 indício |
| MG-3148103-5527FB32… | CAR analisado, nada nas fontes verificadas | sem pendência nas fontes verificadas |

O resultado esperado de cada caso está em `config.CARS_DEMONSTRACAO`, e a página índice mostra se o obtido confere (6 de 6 em 30/10/2026). O caso de Serra do Salitre mudou nessa data: com o PRODES fixo em 2025, os 8 alertas apareciam como "aguardando consolidação" (indício); a verificação mensal achou o Cerrado 2026 publicado, que os confirmou (pendência). O caso de agosto de 2026 entrou para manter um exemplo de alerta que aguarda o PRODES.

## Como regerar

```bash
.venv/bin/python docs/evidencias/atividade-04/prediagnostico/01_demonstracao.py
```

O script precisa dos parquets do lote (`python -m pipeline`, com o PRODES) e de acesso ao SICAR na primeira vez. Depois disso, as respostas ficam em cache em `data/raw/`. O print exige o Google Chrome; sem ele, o script gera só os HTML, MD e JSON.
