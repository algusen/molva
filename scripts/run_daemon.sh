#!/bin/zsh
# Запускает демон Pisar в фоне через CLI-команду.
# Использование: ./scripts/run_daemon.sh [start|stop|status]
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
VENV="$SCRIPT_DIR/../.venv/bin"

ACTION="${1:-start}"
exec "$VENV/molva" daemon "$ACTION"
