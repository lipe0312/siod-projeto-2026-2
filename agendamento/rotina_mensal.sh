#!/bin/zsh
# Rotina mensal do pipeline (próximo passo 5; ADR 0011 e 0015). Agendada pelo launchd (agendamento/LEIA-ME.md).
# Cada etapa roda mesmo se a anterior falhar; o código de saída é o da pior etapa. Log em data/logs/agendamento/.
set -u
RAIZ="${0:A:h:h}"
cd "$RAIZ" || exit 1
PY="$RAIZ/.venv/bin/python"
LOGS="$RAIZ/data/logs/agendamento"
mkdir -p "$LOGS"
CARIMBO=$(date +%Y%m%d_%H%M%S)
# Variáveis locais (ex.: AGROVALID_DATABASE_URL), em .env na raiz, que não é versionado.
[[ -f "$RAIZ/.env" ]] && { set -a; source "$RAIZ/.env"; set +a; }
SAIDA=0

etapa() {
  local nome=$1; shift
  echo "[$(date '+%F %T')] início: $nome" >> "$LOGS/rotina_$CARIMBO.log"
  "$@" >> "$LOGS/rotina_$CARIMBO.log" 2>&1
  local codigo=$?
  echo "[$(date '+%F %T')] fim: $nome (código $codigo)" >> "$LOGS/rotina_$CARIMBO.log"
  (( codigo > SAIDA )) && SAIDA=$codigo
}

# 1. PRODES: uma consulta ao catálogo do TerraBrasilis; só o bioma com versão nova é baixado e tratado (minutos).
etapa "PRODES (versão dos arquivos)" "$PY" -m pipeline --fontes prodes --verificar-prodes
# 2. Fontes nacionais que mudam sem aviso: baixadas de novo e comparadas pela validação.
etapa "IBAMA, Lista Suja, FUNAI, CNUC, quilombolas" "$PY" -m pipeline \
  --fontes ibama lista_suja terras_indigenas unidades_conservacao quilombolas --atualizar
# 3. DETER: Amazônia e Cerrado pelo WFS (partições mensais) e Pantanal pelo arquivo diário.
etapa "DETER" "$PY" -m pipeline --fontes deter --atualizar
# 4. Regressão: os 17 imóveis da demonstração; a página diz quais mudaram de resultado, e diag guarda a execução.
etapa "demonstração" "$PY" -m pipeline.prediagnostico --demo --sem-baixar-prodes

# 5. Banco (opcional): recarrega o perfil lite a partir do lago, só com AGROVALID_DATABASE_URL definida (ADR 0017).
if [[ -n "${AGROVALID_DATABASE_URL:-}" ]]; then
  etapa "banco (perfil lite)" "$PY" -m pipeline.armazenamento.banco --perfil lite --migrar
fi

echo "[$(date '+%F %T')] rotina terminada com código $SAIDA" >> "$LOGS/rotina_$CARIMBO.log"
exit $SAIDA
