---
name: ui-verify
description: Abre o CarroAberto no Chrome real via Chrome DevTools MCP e confere o que o agente fez — screenshots mobile/desktop, erros de console, rede, acessibilidade e performance (LCP no Passaporte). Use depois de mudar qualquer tela ou para depurar bug visual.
---

# Verificar no navegador de verdade

Pré-requisito: app rodando (`npm run dev` → `http://localhost:3000`, ou `npm run build && npx next start -p 3100`). Banco semeado (`npm run db:seed`).

## Login (rotas `/app/*`)
Navegue para `/login` e preencha `dono@demo.com.br` / `carroaberto` (outros papéis: `gerente@`, `vendedor@`, `patio@`). Teste com o papel mais restrito que usa a tela.

## Roteiro por rota (Chrome DevTools MCP)
1. `new_page` / `navigate_page` na rota.
2. `emulate` → viewport **390×844** (mobile) → `take_screenshot`. Depois **1280×800** → `take_screenshot`. Salve em `.claude/screenshots/<rota>-<largura>.png` (ignorado pelo git).
3. `list_console_messages` — qualquer erro = **Quebrado**.
4. `list_network_requests` — 4xx/5xx inesperado = **Quebrado**.
5. `take_snapshot` (árvore de acessibilidade): botões sem nome, inputs sem label, ordem de foco.
6. Passaporte (`/v/demo-onix`) e TV: `performance_start_trace` com reload → LCP < 2,5 s em rede "Fast 4G" (`emulate` network). Acima disso = polimento com prioridade.
7. Interaja com o fluxo principal da mudança (clicar, preencher) e repita 2–3 nas telas resultantes.

## Economia de tokens
- Prefira `take_snapshot` (texto) para checar estrutura; screenshot só nas larguras acima.
- Não despeje a lista inteira de rede: filtre por status ≥ 400.

## Saída
Quebrado (bloqueia) · Polimento (≤ 5) · caminhos dos screenshots.
