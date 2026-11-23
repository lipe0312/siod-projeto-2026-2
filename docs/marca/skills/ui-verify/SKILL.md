---
name: ui-verify
description: Abre o console local do AgroValid (ou um HTML gerado — ficha, carteira, dossiê, preview) no Chrome real e confere o que o agente fez — screenshots 390/1280, erros de console, rede, acessibilidade e impressão. Use depois de mudar qualquer tela ou para depurar bug visual.
---

# Verificar no navegador de verdade (AgroValid)

Pré-requisito: console rodando (`.venv/bin/python -m console` → `http://127.0.0.1:8765`) ou o arquivo HTML gerado (`file://…`). Dados: só a cooperativa de demonstração.

## Ferramenta
Chrome real pelo **claude-in-chrome** (skill `claude-in-chrome`; carregue as ferramentas numa só chamada ToolSearch). Sem ele, Chrome headless: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --screenshot=<png> --window-size=1280,900 <url>`.

## Roteiro por tela
1. Abra a tela numa aba nova.
2. Screenshot em **390×844** e **1280×800**. Salve em `.claude/screenshots/<tela>-<largura>.png` (fora do git).
3. Console do navegador: qualquer erro = **Quebrado**.
4. Rede: 4xx/5xx inesperado = **Quebrado**. Nenhuma requisição pode levar CPF/CNPJ na URL.
5. Árvore de acessibilidade: botão sem nome, campo sem rótulo, ordem de foco, situação só por cor.
6. Fluxo principal: consultar um CAR da demonstração → ver as etapas → abrir a ficha → abrir um cartão do plano de ação. Repita na tela de destino.
7. Impressão da ficha (emule `print`): legível em preto e branco, sem cortar o cartão.
8. `prefers-reduced-motion`: tudo chega no estado final sem animar.

## Economia
Prefira a árvore de acessibilidade (texto) para estrutura; screenshot só nas duas larguras. Filtre a rede por status ≥ 400.

## Saída
Quebrado (bloqueia) · Polimento (≤ 5) · caminhos dos screenshots.
