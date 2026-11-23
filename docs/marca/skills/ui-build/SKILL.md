---
name: ui-build
description: OBRIGATÓRIA para qualquer tela, componente ou mudança visível no AgroValid (console local do técnico, ficha HTML, carteira HTML, dossiê EUDR, preview). Orquestra DESIGN.md → componentes que já existem → referências (shadcn MCP, ui-design-references) → frontend-design → verificação no Chrome (ui-verify) → web-design-guidelines → preview-aprovacao.
---

# Construir UI no AgroValid (pipeline obrigatório)

Pule um passo só se não se aplica, e diga qual e por quê. Adaptada do CarroAberto em 23/11/2026.

## 1. Contexto de design
- Leia `DESIGN.md` (raiz): tokens, tom, situações, anti-padrões. A escolha vigente de cada item está em `docs/marca/design-system/decisoes.md`; as opções, em `docs/marca/design-system/preview-console.html`.
- Superfície: **Console** (técnico na mesa, projetor na apresentação, 1280) · **Ficha impressa** (preto e branco, A4) · **Celular** (técnico em campo, 390, sol) · **Dossiê** (comprador europeu, leitura formal).
- Ideia nova de UI, componente ou movimento → atualize `decisoes.md` + `preview-console.html` no mesmo PR, antes do código. A escolha antiga vira alternativa.

## 2. Reusar antes de criar
1. O que existe: `pipeline/ficha_html.py` (selos, mapa SVG, linha do tempo, tabelas), CSS do console em `console/estatico/` (quando existir).
2. **shadcn MCP** (`claude mcp add shadcn -s local -- npx -y shadcn@latest mcp`, já configurado neste checkout): busque o bloco ou componente equivalente e leia a **estrutura e a acessibilidade** (roles, aria, teclado). O console **não tem React nem Tailwind**: reimplemente em HTML + CSS com os tokens do `DESIGN.md` e JS puro. Nunca `npx shadcn add` aqui.
3. Sem equivalente → skill `ui-design-references` (até 3 referências) antes de inventar.

## 3. Direção visual
Skill **frontend-design** com as restrições do `DESIGN.md` (ele vence). Nada de folha, gradiente, verde vivo, azul de banco, glassmorphism, emoji como ícone, quatro cartões de KPI iguais, caixa alta espaçada, animação ao rolar.

## 4. Implementar
- HTML gerado no servidor (strings com `html.escape`, como o `ficha_html.py`); JS puro só para interação; sem dependência nova (regra 8).
- pt-BR, linguagem de técnico de campo. Situação sempre com ícone + nome. Nunca "conforme".
- Estados: vazio, carregando (etapas do cruzamento), erro (fonte fora do ar = inconclusivo com motivo) — os três.
- Contraste AA mínimo, AAA no texto principal (projetor). Foco visível. `prefers-reduced-motion`. Impressão legível em preto e branco.
- Nenhum CPF/CNPJ na tela, na URL ou no log; documento só por POST.

## 5. Ver de verdade
Skill `ui-verify` nas telas tocadas (Chrome). Corrija tudo que sair como **Quebrado**.

## 6. Conferência final
Skill `web-design-guidelines` nos arquivos tocados; acessibilidade e foco se corrigem, o resto vira "polimento" no PR. Depois, `preview-aprovacao` (simplificado) para o portão.
