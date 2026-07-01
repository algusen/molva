#!/bin/zsh
# Установка / удаление Finder Quick Action «Molva — транскрибировать».
# Использование:
#   ./scripts/quickaction.sh install
#   ./scripts/quickaction.sh uninstall
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
WORKFLOW_SRC="${SCRIPT_DIR}/../packaging/Molva.workflow"
SERVICES_DIR="$HOME/Library/Services"
WORKFLOW_DST="${SERVICES_DIR}/Molva.workflow"
VENV_BIN=$(cd "${SCRIPT_DIR}/../.venv/bin" 2>/dev/null && pwd -P) \
    || { echo "Ошибка: .venv не найден. Запустите install.sh сначала." >&2; exit 1; }

LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister

_reload_services() {
    # Регистрируем только наш бандл, затем перезагружаем сервисы
    "$LSREGISTER" -f "$WORKFLOW_DST" 2>/dev/null || true
    "$LSREGISTER" -r -domain user 2>/dev/null || true
    killall -HUP Finder 2>/dev/null || true
}

cmd_install() {
    echo "→ Устанавливаю Quick Action…"
    mkdir -p "$SERVICES_DIR"

    # Копируем бандл из packaging/
    rm -rf "$WORKFLOW_DST"
    cp -R "$WORKFLOW_SRC" "$WORKFLOW_DST"

    # Подставляем реальный путь к venv
    sed -i '' "s|__VENV_BIN__|${VENV_BIN}|g" \
        "${WORKFLOW_DST}/Contents/document.wflow"

    _reload_services
    echo "✓ Quick Action установлен: ${WORKFLOW_DST}"
    echo "  Finder перезагружен. Откройте аудио/видео файл → ПКМ → Быстрые действия → «Molva — транскрибировать»"
}

cmd_uninstall() {
    if [[ -d "$WORKFLOW_DST" ]]; then
        rm -rf "$WORKFLOW_DST"
        _reload_services
        echo "✓ Quick Action удалён."
    else
        echo "Quick Action не установлен."
    fi
}

case "${1:-}" in
    install)   cmd_install ;;
    uninstall) cmd_uninstall ;;
    *)
        echo "Использование: $0 install|uninstall" >&2
        exit 1 ;;
esac
