# Marca e design system do AgroValid

Situação em 03/11/2026: direção C (Marca de ferro) aprovada como base; situações em semáforo (v3) aprovadas até aqui. Tudo pode mudar.

## O que tem aqui

| Arquivo | O que é |
|---|---|
| `preview.html` | **Depois.** Prévia atual do design system: painel da carteira, situações, componentes, fundamentos. Abre no navegador, funciona offline (as fontes caem para a do sistema sem rede) |
| `preview-direcoes.html` | **Antes.** As três direções da primeira rodada (A Curva de nível, B Grão, C Marca de ferro), com as cores de situação da v1 |
| `design-system/decisoes.md` | Regras, tokens, situações e o que falta para virar padrão. As versões rejeitadas ficam descritas lá |
| `design-system/canvas/` | Código das quatro pranchas do canvas (Fundamentos, Componentes, Carteira, Celular), formato `.dc.html` |
| `design-system/situacoes.json` | Cores de situação v3 com as medidas |
| `status.json` | Cores de situação v1 das três direções, com as medidas |
| `agrovalid/` | Pasta de trabalho da skill brand-identity: brief, `sets.json`, paleta, logos (SVG e PNG), cards e board de cada direção |
| `favicons/` | Favicon de cada direção, com troca automática claro/escuro |
| `gerar/` | Scripts que montaram as direções, as cores de situação e o preview antigo |
| `skills/` | Cópia das skills de UI trazidas do projeto CarroAberto (a pasta `.claude` não é versionada) |

Para voltar a uma ideia anterior: as três direções estão em `preview-direcoes.html` e em `agrovalid/sets/A|B|C`; a v2 das situações (legenda de campo, só forma e cor) se regenera com `gerar/status_c.py`.

## Como instanciar cada skill

Os comandos rodam da raiz do repositório. `S` é a pasta de scripts da brand-identity:

```bash
S=~/.claude/plugins/cache/brand-identity-skill/brand-identity/1.1.1/skills/brand-identity/scripts
```

### brand-identity (plugin `brand-identity-skill`)
Gera as direções de marca (logo, tipo, paleta), mede contraste, daltonismo e logo em 16/32 px.
- No Claude Code: `/brand-identity` ou peça "identidade visual" (a skill lê o `SKILL.md` e segue o método).
- Na mão:
  ```bash
  python3 $S/brand.py check
  python3 $S/brand.py init "AgroValid" --root docs/marca --sets 3 --langs pt --doc-lang pt --numbers --sector "…" --audience "…" --attributes "sóbrio,confiável,técnico,raiz no campo"
  python3 docs/marca/gerar/make_sets.py docs/marca/agrovalid/sets.json   # escreve as 3 direções
  python3 $S/brand.py logos docs/marca/agrovalid                          # folha de contato dos logos
  python3 $S/brand.py build docs/marca/agrovalid                          # paleta, auditoria, cards, board
  python3 $S/brand.py kit docs/marca/agrovalid/sets/C                     # kit de marca da escolhida (ainda não rodado)
  ```
- Rede: baixa fontes OFL de `raw.githubusercontent.com/google/fonts` para `~/.cache/brand-identity`.

### Cores de situação (scripts deste repositório, usam o `colorlib` da brand-identity)
```bash
python3 docs/marca/gerar/status.py   $S docs/marca/agrovalid docs/marca/status.json          # v1, três direções
python3 docs/marca/gerar/status_c.py $S /tmp/situacoes-v2.json                               # v2, legenda de campo
python3 docs/marca/gerar/status_v3.py $S docs/marca/design-system/situacoes.json             # v3, semáforo (vigente)
.venv/bin/python -I docs/marca/gerar/preview.py $S docs/marca                                # refaz preview-direcoes.html
```
O `preview.html` atual é escrito à mão; os números nele vêm do `situacoes.json`.

### ui-ux-pro-max (skill global em `~/.claude/skills/ui-ux-pro-max`)
Busca de padrões de UX e checklist de entrega.
```bash
python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py "agriculture compliance dashboard data table status B2B" --design-system -p AgroValid
python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py "animation accessibility" --domain ux
```
A paleta que ela sugeriu (azul de fintech) foi descartada; usamos só o checklist.

### frontend-design (plugin oficial `claude-plugins-official`)
Direção visual e lista de "cara de IA" a evitar. No Claude Code: `/frontend-design` ou peça uma tela nova.

### ui-build, ui-design-references, ui-verify, web-design-guidelines (cópias em `skills/`)
Vieram do projeto CarroAberto e ainda citam o CarroAberto no texto. Para usar aqui:
```bash
mkdir -p .claude/skills && cp -R docs/marca/skills/* .claude/skills/
```
Depois, no Claude Code: `/ui-build` (pipeline de tela), `/ui-design-references` (referências sem cara de IA), `/ui-verify` (conferência no Chrome) e `/web-design-guidelines <arquivo>` (revisão pelas Web Interface Guidelines da Vercel; baixa as regras de `raw.githubusercontent.com/vercel-labs/web-interface-guidelines`).
O MCP do shadcn citado na `ui-build` não está configurado neste projeto; o shadcn serviu só de referência de estrutura.

### Canvas (Claude Design)
`/design` no Claude Code cria o canvas no claude.ai. O canvas deste design system é privado: https://claude.ai/artifact/3uvs5nSpdHyP7pn5HFqa55. Os arquivos-fonte estão em `design-system/canvas/`.
