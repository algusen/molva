#!/bin/zsh
# Управление launchd LaunchAgent для molva-daemon.
# Использование:
#   ./scripts/launchd.sh install   — установить и запустить агент
#   ./scripts/launchd.sh uninstall — остановить и удалить агент
#   ./scripts/launchd.sh status    — проверить статус
set -euo pipefail

LABEL="com.algusen.molva"
PLIST_SRC="${0:A:h}/../packaging/${LABEL}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
AGENTS_DIR="$HOME/Library/LaunchAgents"

# Определяем пути автоматически
SCRIPT_DIR="${0:A:h}"
VENV_BIN="${SCRIPT_DIR}/../.venv/bin"
VENV_BIN=$(cd "$VENV_BIN" && pwd -P)   # абсолютный путь

# Путь к модели (если есть рядом с проектом)
PROJECT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd -P)
MODEL_PATH="${PROJECT_DIR}/models/GigaAM-v3-e2e_rnnt"

LOG_DIR="$HOME/Library/Logs/Molva"

# ── install ───────────────────────────────────────────────────────────────────
cmd_install() {
    echo "→ Устанавливаю LaunchAgent ${LABEL}…"

    # Создаём нужные директории
    mkdir -p "$AGENTS_DIR" "$LOG_DIR"

    # Генерируем plist из шаблона
    sed \
        -e "s|__VENV_BIN__|${VENV_BIN}|g" \
        -e "s|__MODEL_PATH__|${MODEL_PATH}|g" \
        -e "s|__LOG_DIR__|${LOG_DIR}|g" \
        "$PLIST_SRC" > "$PLIST_DST"

    echo "  Plist: ${PLIST_DST}"

    # Выгружаем старую версию если была
    launchctl unload "$PLIST_DST" 2>/dev/null || true

    # Загружаем агент
    launchctl load -w "$PLIST_DST"
    echo "  Агент загружен. Демон запускается…"

    # Ждём старта и проверяем /health
    sleep 3
    "${VENV_BIN}/molva" health 2>/dev/null && echo "  Демон готов ✓" \
        || echo "  Демон ещё стартует. Проверьте: molva health"
}

# ── uninstall ─────────────────────────────────────────────────────────────────
cmd_uninstall() {
    echo "→ Удаляю LaunchAgent ${LABEL}…"
    if [[ -f "$PLIST_DST" ]]; then
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        rm -f "$PLIST_DST"
        echo "  Удалён: ${PLIST_DST}"
    else
        echo "  Агент не установлен."
    fi
}

# ── status ────────────────────────────────────────────────────────────────────
cmd_status() {
    if launchctl list "$LABEL" &>/dev/null; then
        echo "Агент загружен (launchctl list ${LABEL}):"
        launchctl list "$LABEL"
    else
        echo "Агент не загружен."
    fi
    echo ""
    echo "PID-файл: $(cat ~/.molva/daemon.pid 2>/dev/null || echo '(нет)')"
    echo "Логи: ${LOG_DIR}/"
}

# ── dispatch ──────────────────────────────────────────────────────────────────
case "${1:-}" in
    install)   cmd_install ;;
    uninstall) cmd_uninstall ;;
    status)    cmd_status ;;
    *)
        echo "Использование: $0 install|uninstall|status" >&2
        exit 1
        ;;
esac
