---
name: ui-build
description: OBRIGATÓRIA para qualquer tela, componente ou mudança visível ao usuário no CarroAberto (backoffice, Passaporte, TV, landing). Orquestra DESIGN.md → componentes existentes (shadcn MCP / src/components) → frontend-design → 21st Magic → verificação no Chrome → web-design-guidelines.
---

# Construir UI (pipeline obrigatório)

Pule um passo só se ele não se aplica, e diga qual e por quê.

## 1. Contexto de design (≤ 2 min)
- Leia `DESIGN.md` (raiz). É a fonte de tokens, tom e anti-padrões. Se a tela pedir algo que ele não cobre → skill `ui-design-references` antes de inventar.
- Identifique a superfície: **Passaporte** (mobile, sol, 4G, comprador leigo) · **Backoffice** (denso, gerente) · **Pátio** (celular, 1 mão, < 15 s) · **TV** (distância 3 m) · **Landing** (conversão).

- Confira a escolha vigente em `docs/brand/design-system/decisoes.md` (e veja funcionando no `preview.html`). **Obrigatório:** se a tela trouxer ideia nova de UI, componente, animação ou peça de marca, ou mudar uma escolha, atualize `decisoes.md` + `preview.html` no mesmo PR, antes do código. A escolha antiga vira alternativa, nunca é apagada.

## 2. Reusar antes de criar
1. `src/components/ui.tsx` + classes `.btn`, `.input`, `.label` em `src/app/globals.css` — o que existe hoje.
2. **shadcn MCP** (sempre): liste/busque no registry o componente equivalente e leia o exemplo de uso.
   - Sem `components.json` no projeto (ADR-0006 ainda proposto) → use o shadcn como **referência de estrutura e acessibilidade**, implemente com Tailwind + tokens do `DESIGN.md`. Não rode `npx shadcn init/add` sem o ADR aceito.
   - Com `components.json` → `npx shadcn add <componente>` (pede aprovação) e adapte aos tokens.
3. **21st Magic MCP** (`/ui …`): só para peça que não existe em 1 nem 2 (ex.: comparador antes/depois). Gasta cota — 1 geração por peça; reescreva o resultado com nossos tokens.

## 3. Direção visual
Aplique a skill **frontend-design** (plugin oficial) com as restrições do `DESIGN.md`: ela dá a intenção (tipografia, hierarquia, composição); o `DESIGN.md` vence em conflito. Nada de gradiente roxo, glassmorphism, emoji como ícone, sombra pesada, texto centralizado em tudo.

## 4. Implementar
- Server Component por padrão; `"use client"` só para interação. Dados de runtime dentro de `<Suspense>` com `Skeleton`.
- Textos pt-BR; texto ao comprador passa pela skill `mkt-copy`.
- Mobile first (390 px). Alvo de toque ≥ 44 px. Contraste AA mínimo; Passaporte busca AAA no texto principal (uso sob sol).
- Estado vazio, carregando e erro — os três.

## 5. Ver de verdade
Delegue ao subagente `ui-reviewer` (Chrome DevTools MCP + skill `ui-verify`) com as rotas tocadas. Corrija tudo que ele marcar como **Quebrado**.

## 6. Conferência final
Rode a skill **web-design-guidelines** nos arquivos tocados. Corrija acessibilidade e foco; o resto vai para "polimento" no PR.

Entrega: screenshots antes/depois no resumo da skill `ship`.
