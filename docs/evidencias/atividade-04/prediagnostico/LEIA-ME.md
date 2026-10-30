# Pré-diagnóstico: demonstração

Fichas geradas por `python -m pipeline.prediagnostico --demo` para os CARs de `config.CARS_DEMONSTRACAO`. São imóveis reais do recorte de café de MG. O documento do proprietário é um CPF fictício (`prediagnostico.DOCUMENTO_DEMONSTRACAO`), usado para mostrar a Lista Suja verificada sem expor dado pessoal. O CPF não aparece em nenhum arquivo.

| Arquivo | O que é |
|---|---|
| `index.html`, `index.png` | Página da demonstração, com um cartão por imóvel |
| `<CAR>.html` | Ficha do imóvel: resultado, mapa, critérios, evidências e procedência |
| `<CAR>.png` | Print da ficha (Chrome headless, 1200 px de largura) |
| `<CAR>.md` | A mesma ficha em Markdown |
| `<CAR>.json` | A ficha completa, com as evidências em registros (sem geometrias) |
| `01_demonstracao.py` | Gera tudo acima |

| CAR | Caso | Resultado |
|---|---|---|
| MG-3148103-6245AC9B… | Desmatamento após 2020 confirmado pelo PRODES | com pendência |
| MG-3166808-A726F93D… | Embargo e 8 alertas DETER de ago./set. 2025, aguardando o PRODES | com pendência (embargo) e indício |
| MG-3148103-627F1606… | Embargo e alerta sobre área já suprimida antes | com pendência (embargo) e indício |
| MG-3148103-A63D0A01… | CAR com notificação pendente, embargos e alerta confirmado | 2 pendências e 1 indício |
| MG-3148103-5527FB32… | CAR analisado, nada nas fontes verificadas | sem pendência nas fontes verificadas |

## Como regerar

```bash
.venv/bin/python docs/evidencias/atividade-04/prediagnostico/01_demonstracao.py
```

O script precisa dos parquets do lote (`python -m pipeline`) e de acesso ao SICAR e ao TerraBrasilis na primeira vez. Depois disso, as respostas ficam em cache em `data/raw/`. O print exige o Google Chrome; sem ele, o script gera só os HTML, MD e JSON.
