# Rotina mensal

[`rotina_mensal.sh`](rotina_mensal.sh) atualiza as fontes em lote e roda a demonstração como teste de regressão. Cada etapa roda mesmo se a anterior falhar, e o log fica em `data/logs/agendamento/rotina_AAAAMMDD_HHMMSS.log`.

| Etapa | Comando | O que faz |
|---|---|---|
| 1 | `python -m pipeline --fontes prodes --verificar-prodes` | Consulta o catálogo do TerraBrasilis e baixa só o bioma com versão nova (ADR 0015) |
| 2 | `python -m pipeline --fontes ibama lista_suja terras_indigenas unidades_conservacao quilombolas --atualizar` | Baixa de novo as fontes nacionais, que mudam sem aviso |
| 3 | `python -m pipeline --fontes deter --atualizar` | DETER da Amazônia e do Cerrado pelo WFS e do Pantanal pelo arquivo |
| 4 | `python -m pipeline.prediagnostico --demo --sem-baixar-prodes` | Os 17 imóveis da demonstração; a página diz se algum mudou de resultado |

## Instalar (macOS, launchd)

O launchd roda a execução perdida quando o Mac acorda; o `cron` a perderia. Por isso o agendamento usa o launchd.

```bash
RAIZ="$(pwd)"   # na raiz do projeto
sed "s#RAIZ_DO_PROJETO#$RAIZ#g" agendamento/br.ufba.siod.rotina-mensal.plist \
  > ~/Library/LaunchAgents/br.ufba.siod.rotina-mensal.plist
launchctl load ~/Library/LaunchAgents/br.ufba.siod.rotina-mensal.plist
launchctl list | grep siod          # confere que entrou
launchctl start br.ufba.siod.rotina-mensal   # roda agora, para testar
```

**Projeto dentro de `~/Documents`, `~/Desktop` ou `~/Downloads`:** a proteção de privacidade do macOS (TCC) impede o processo iniciado pelo launchd de ler essas pastas. Em 02/11/2026, a primeira execução falhou com `can't open input file` (código 127, em `data/logs/agendamento/launchd.err`). Há duas saídas:
* dar acesso a `/bin/zsh` em Ajustes do Sistema → Privacidade e Segurança → Acesso Total ao Disco (botão +, ⌘⇧G, `/bin/zsh`). O acesso vale para qualquer script zsh, por isso a decisão é do dono da máquina;
* mover o projeto para fora dessas pastas (ex.: `~/projetos/`) e reinstalar o plist.

Depois, `launchctl kickstart gui/$(id -u)/br.ufba.siod.rotina-mensal` roda na hora. Confira com `launchctl print gui/$(id -u)/br.ufba.siod.rotina-mensal | grep "last exit"`: deve dar 0, ou 1 se alguma fonte falhar (detalhe no log da rotina).

Para remover: `launchctl unload ~/Library/LaunchAgents/br.ufba.siod.rotina-mensal.plist` e apagar o arquivo.

Em Linux, a linha equivalente do `crontab -e` é `0 3 2 * * /bin/zsh /caminho/do/projeto/agendamento/rotina_mensal.sh`. Num servidor sempre ligado, o `cron` basta.

## Quando a máquina não fica ligada

A rotina não precisa de servidor. Ela roda quando o computador estiver ligado no dia 2, ou na primeira vez que acordar depois disso. Se passar mais de um mês sem rodar, nada se perde: o PRODES compara a versão, e as outras fontes são baixadas de novo inteiras. Para um serviço com técnicos usando ao mesmo tempo, o passo é o servidor do ADR 0011.
