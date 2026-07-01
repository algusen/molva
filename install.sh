#!/bin/zsh
# install.sh — установка Molva на macOS Apple Silicon.
# Идемпотентен: повторный запуск безопасен.
# Использование: ./install.sh [--no-model] [--no-daemon]
set -euo pipefail

# ── цвета ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo "${GREEN}✓${RESET} $*" }
info() { echo "${BOLD}→${RESET} $*" }
warn() { echo "${YELLOW}⚠${RESET}  $*" }
die()  { echo "${RED}✗ Ошибка:${RESET} $*" >&2; exit 1 }

# ── флаги ─────────────────────────────────────────────────────────────────────
OPT_NO_MODEL=0
OPT_NO_DAEMON=0
for arg in "$@"; do
  case "$arg" in
    --no-model)  OPT_NO_MODEL=1 ;;
    --no-daemon) OPT_NO_DAEMON=1 ;;
    --help|-h)
      echo "Использование: $0 [--no-model] [--no-daemon]"
      echo "  --no-model   пропустить загрузку модели GigaAM-v3"
      echo "  --no-daemon  пропустить установку launchd агента"
      exit 0 ;;
  esac
done

# ── пути ──────────────────────────────────────────────────────────────────────
PROJECT_DIR="${0:A:h}"   # абсолютный путь к папке скрипта
VENV_DIR="${PROJECT_DIR}/.venv"
MODEL_DIR="${PROJECT_DIR}/models/GigaAM-v3-e2e_rnnt"

echo ""
echo "${BOLD}Установка Molva${RESET}"
echo "Проект: ${PROJECT_DIR}"
echo ""

# ── 1. Проверка платформы ─────────────────────────────────────────────────────
info "Проверка платформы…"
[[ "$(uname -s)" == "Darwin" ]] || die "Molva работает только на macOS."
[[ "$(uname -m)" == "arm64"  ]] || warn "Рекомендуется Apple Silicon (arm64); на Intel MPS недоступен."
ok "macOS $(sw_vers -productVersion)"

# ── 2. Python 3.11+ ───────────────────────────────────────────────────────────
info "Проверка Python…"
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if cmd=$(command -v "$candidate" 2>/dev/null); then
    ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=${ver%%.*}; minor=${ver##*.}
    if (( major > 3 || (major == 3 && minor >= 11) )); then
      PYTHON="$cmd"
      break
    fi
  fi
done
[[ -n "$PYTHON" ]] || die "Требуется Python 3.11+. Установите: brew install python@3.12"
ok "Python $($PYTHON --version)"

# ── 3. ffmpeg ─────────────────────────────────────────────────────────────────
info "Проверка ffmpeg…"
if ! command -v ffmpeg &>/dev/null; then
  if command -v brew &>/dev/null; then
    info "Устанавливаю ffmpeg через brew…"
    brew install ffmpeg
  else
    die "ffmpeg не найден. Установите: brew install ffmpeg"
  fi
fi
ok "ffmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"

# ── 4. Виртуальное окружение ──────────────────────────────────────────────────
info "Настройка виртуального окружения…"
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON" -m venv "$VENV_DIR"
  ok "Создано: ${VENV_DIR}"
else
  ok "Уже существует: ${VENV_DIR}"
fi
VENV_BIN="${VENV_DIR}/bin"

# ── 5. Установка пакета ───────────────────────────────────────────────────────
info "Установка molva[gigaam]…"
"${VENV_BIN}/pip" install -q --upgrade pip
"${VENV_BIN}/pip" install -q -e "${PROJECT_DIR}[gigaam]"
ok "Пакет установлен: $("${VENV_BIN}/molva" --version 2>/dev/null || echo 'molva')"

# ── 6. Загрузка модели GigaAM-v3 ─────────────────────────────────────────────
if (( OPT_NO_MODEL )); then
  warn "Загрузка модели пропущена (--no-model)."
elif [[ -d "$MODEL_DIR" && -f "${MODEL_DIR}/config.json" ]]; then
  ok "Модель уже загружена: ${MODEL_DIR}"
else
  info "Загружаю GigaAM-v3 (ai-sage/GigaAM-v3, revision e2e_rnnt)…"
  info "Размер ~450 МБ, может занять несколько минут."
  mkdir -p "${PROJECT_DIR}/models"
  "${VENV_BIN}/python" - <<PYEOF
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="ai-sage/GigaAM-v3",
    revision="e2e_rnnt",
    local_dir="${MODEL_DIR}",
    local_dir_use_symlinks=False,
)
print("Модель загружена.")
PYEOF
  ok "Модель: ${MODEL_DIR}"
fi

# ── 7. Путь к molva в терминале ───────────────────────────────────────────────
info "Проверка PATH…"
if ! command -v molva &>/dev/null || [[ "$(command -v molva)" != "${VENV_BIN}/molva" ]]; then
  warn "'molva' не найдена в PATH. Добавьте в ~/.zshrc:"
  echo ""
  echo "    export PATH=\"${VENV_BIN}:\$PATH\""
  echo ""
fi

# ── 8. launchd агент ─────────────────────────────────────────────────────────
if (( OPT_NO_DAEMON )); then
  warn "Установка launchd агента пропущена (--no-daemon)."
else
  info "Устанавливаю launchd агент…"
  "${PROJECT_DIR}/scripts/launchd.sh" install
fi

# ── готово ────────────────────────────────────────────────────────────────────
echo ""
echo "${BOLD}${GREEN}Готово!${RESET} Molva установлена."
echo ""
echo "Использование:"
echo "  molva file.mp4            — транскрибировать файл"
echo "  molva --backend gigaam file.mp4  — форсировать модель (без демона)"
echo "  molva daemon status       — статус демона"
echo "  molva health              — проверить /health"
echo ""
echo "Логи демона: ~/Library/Logs/Molva/"
