---
name: ui-design-references
description: Busca referências de design limpo e templates prontos (getdesign.md, shadcn blocks, Vercel templates, galerias curadas) e converte em decisões no DESIGN.md do CarroAberto, evitando a "cara de IA". Use ao criar tela/seção nova sem padrão no DESIGN.md, landing page ou redesign.
---

# Referências que tiram a cara de IA

## Onde procurar (em ordem — grátis primeiro)
| Fonte | Serve para | Custo |
|---|---|---|
| `DESIGN.md` do projeto | Sempre primeiro | — |
| **getdesign.md** / github.com/VoltAgent/awesome-design-md | DESIGN.md prontos de marcas reais (Linear, Stripe, Vercel, Notion…) — copie *princípios*, não a marca | grátis, MIT |
| **ui.shadcn.com/blocks** + shadcn MCP | Blocos prontos (dashboard, login, tabelas, sidebar) | grátis |
| **vercel.com/templates** (Next.js) | Templates completos de SaaS/landing | grátis |
| **tailark.com**, **shadcnblocks.com** (parte grátis) | Seções de marketing em shadcn | grátis/pago |
| **Untitled UI** (Figma free) | Sistema completo, sóbrio, muito usado em SaaS B2B | grátis/pago |
| **land-book.com**, **saaspo.com**, **lapa.ninja**, **godly.website** | Inspiração de landing por categoria | grátis |
| **mobbin.com**, **refero.design** | Telas reais de apps (fluxos mobile, onboarding, formulários) | pago (free limitado) |
| **21st.dev** | Componentes da comunidade — filtre os sóbrios | grátis/cota |

Busque com WebFetch na página específica (não na home). Traga no máximo 3 referências.

## Anti-padrões de "cara de IA" (reprovar)
- Gradiente roxo/azul em hero, blobs, glassmorphism, glow
- Emoji como ícone de feature; ícones genéricos em círculo colorido em grade de 3
- "Hero centralizado + 3 cards + depoimentos + CTA" sem razão
- Tudo `rounded-2xl` + `shadow-xl`; cinza-azulado sem contraste
- Frases vazias: "Revolucione", "Potencialize", "Solução completa", "Seamless"
- Números/depoimentos inventados

## O que dá cara de produto real
- **Dados reais na tela** (placa mascarada, km, R$, dias de pátio) em vez de ilustração
- Tipografia com hierarquia forte e números tabulares (`tabular-nums`) em valores
- Densidade adequada à persona (backoffice denso; Passaporte espaçado)
- Uma cor de marca + semânticas (verde/âmbar/vermelho = margem/SLA). Neutros quentes (`#f7f7f5`)
- Fotos do próprio carro e do pátio > qualquer ilustração

## Saída
1. 3 referências: link · o que copiar (princípio) · o que NÃO copiar.
2. Diff proposto para o `DESIGN.md` (tokens, componente, regra). O humano aprova mudanças no `DESIGN.md`.
