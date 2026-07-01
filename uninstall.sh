#!/bin/zsh
# uninstall.sh — удаление Molva с macOS.
# Использование: ./uninstall.sh [--keep-model] [--keep-venv]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo "${GREEN}✓${RESET} $*" }
info() { echo "${BOLD}→${RESET} $*" }
warn() { echo "${YELLOW}⚠${RESET}  $*" }

OPT_KEEP_MODEL=0
OPT_KEEP_VENV=0
for arg in "$@"; do
  case "$arg" in
    --keep-model) OPT_KEEP_MODEL=1 ;;
    --keep-venv)  OPT_KEEP_VENV=1 ;;
    --help|-h)
      echo "Использование: $0 [--keep-model] [--keep-venv]"
      exit 0 ;;
  esac
done

PROJECT_DIR="${0:A:h}"

echo ""
echo "${BOLD}Удаление Molva${RESET}"
echo ""

# ── 1. Остановить и удалить launchd агент ────────────────────────────────────
info "Удаляю launchd агент…"
"${PROJECT_DIR}/scripts/launchd.sh" uninstall

# ── 2. Удалить Quick Action ───────────────────────────────────────────────────
WORKFLOW="$HOME/Library/Services/Molva.workflow"
if [[ -d "$WORKFLOW" ]]; then
  info "Удаляю Quick Action…"
  rm -rf "$WORKFLOW"
  ok "Удалён: ${WORKFLOW}"
fi

# ── 3. Удалить venv ───────────────────────────────────────────────────────────
if (( OPT_KEEP_VENV )); then
  warn "Виртуальное окружение сохранено (--keep-venv)."
elif [[ -d "${PROJECT_DIR}/.venv" ]]; then
  info "Удаляю виртуальное окружение…"
  rm -rf "${PROJECT_DIR}/.venv"
  ok "Удалено: ${PROJECT_DIR}/.venv"
fi

# ── 4. Удалить модель ─────────────────────────────────────────────────────────
if (( OPT_KEEP_MODEL )); then
  warn "Модель сохранена (--keep-model)."
elif [[ -d "${PROJECT_DIR}/models" ]]; then
  info "Удаляю модель GigaAM-v3 (~450 МБ)…"
  rm -rf "${PROJECT_DIR}/models"
  ok "Удалено: ${PROJECT_DIR}/models"
fi

# ── 5. Удалить ~/.molva ───────────────────────────────────────────────────────
if [[ -d "$HOME/.molva" ]]; then
  info "Удаляю ~/.molva (PID-файл, конфиг)…"
  rm -rf "$HOME/.molva"
  ok "Удалено: ~/.molva"
fi

echo ""
echo "${BOLD}${GREEN}Готово.${RESET} Molva удалена."
echo "Логи сохранены в ~/Library/Logs/Molva/ — удалите вручную если нужно."
