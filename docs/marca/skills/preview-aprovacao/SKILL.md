---
name: preview-aprovacao
description: Gera um HTML único, offline e fora do git, que mostra ao dono do AgroValid o que a entrega muda ou quais opções de design existem. Simplificado (padrão) — "como era → como fica", 3 casos e critérios, sem subir o console; completo — antes × depois com screenshots reais do console local e demo clicável; opções — prancha com 3 alternativas por item (botão, movimento, número, mapa…) para o dono escolher. Use antes do "aprovado merge" de toda tela, e quando o dono pedir "preview com opções".
---

# Preview para aprovação (só olhar e decidir)

Trazida do CarroAberto (Tentativa01) em 23/11/2026 e adaptada. O dono decide **sem rodar nada**: um arquivo, abre no navegador e no celular.

## 0. Onde e quando
- **Preview de entrega:** `.claude/preview/<N>-<slug>.html` (fora do git: `.claude/` é ignorada). Gere antes do portão final da `next-task-full`/`next-wave` (§9). "Ajustes" → refaça; "aprovado merge" → `rm -f .claude/preview/<N>-*.html`.
- **Prancha de opções de design:** `docs/marca/design-system/preview-console.html` (versionada, como o `docs/marca/preview.html`). É a fonte de decisão do `DESIGN.md`; a escolha vira `decisoes.md` + `DESIGN.md` no mesmo PR, e a alternativa rejeitada continua na prancha.

## 1. Nível
| Nível | Quando | O que tem |
|---|---|---|
| **Simplificado** (padrão) | toda tela ou mudança visível | modelo `references/preview-simples.html`: como era → como fica desenhado em HTML/CSS só do pedaço que muda, 3 casos (comum, borda, erro), critérios × feito, gate e riscos. Sem JS, sem base64. ≤ 80 linhas |
| **Completo** | pedido ("preview completo") | screenshots 390 e 1280 do console (`ui-verify`), embutidos em base64 por script no scratchpad; demo clicável em JS puro com um dos casos da cooperativa de demonstração |
| **Opções** | "3 opções", "quero ir decidindo", item sem padrão no `DESIGN.md` | por item: 3 alternativas lado a lado (A, B, C), cada uma funcionando (hover, clique, movimento), com 1 linha de trade-off e a recomendada marcada. Alternador claro/escuro e 390/1280. Regras que nenhuma opção quebra no topo |

## 2. Regras de conteúdo (todas)
- Tokens do `DESIGN.md` em `:root`; Zilla Slab nos títulos e números, Source Sans 3 no texto, com fallback do sistema (funciona offline).
- Situação **sempre** com ícone + nome (v3 do semáforo). Nunca a palavra "conforme"; "sem pendência nas fontes verificadas".
- Dados: só os 17 CARs da demonstração e a cooperativa fictícia (selo "dados de demonstração"). **Nenhum CPF/CNPJ**, nem fictício por extenso: mostre `documento_hash` encurtado (`a3f9…`).
- Sem CDN de JS. Fonte do Google com fallback é a única rede permitida.
- Proibido: número inventado como se fosse medido, promessa que o código não cumpre, "conforme".

## 3. Entregar
- Local: `open <arquivo>`. Linha no resumo da `ship`: `**Preview:** <caminho> (simplificado|completo|opções)` ou `Preview: n.a. (<motivo>)`.
- Checagem antes de commit: `git diff --cached --name-only | grep -q '^\.claude/preview/' && echo "ERRO: preview no commit"`.
