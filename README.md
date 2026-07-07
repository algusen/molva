# Molva

Локальный транскрибатор аудио и видео для macOS Apple Silicon на базе модели [GigaAM-v3](https://huggingface.co/ai-sage/GigaAM-v3).

Работает полностью офлайн. Оптимизирован для русской речи.

## Возможности

- Транскрибация аудио и видео файлов (WAV, MP3, MP4, MOV, MKV и др.)
- Вывод в форматах TXT, SRT, VTT, JSON (sidecar рядом с файлом)
- Правый клик в Finder → Quick Actions → «Molva transcriber» + уведомление о готовности
- Тёплый демон — модель загружается один раз, повторные запросы выполняются быстро
- Автозапуск демона через launchd

## Требования

- macOS 12+ (Apple Silicon, arm64)
- Python 3.11+
- [Homebrew](https://brew.sh)

## Установка

```zsh
git clone https://github.com/algusen/molva.git
cd molva
./install.sh
```

Скрипт установит зависимости (ffmpeg, terminal-notifier), создаст виртуальное окружение, загрузит модель (~450 МБ), настроит launchd агент и Quick Action для Finder.

### Опции установки

```zsh
./install.sh --no-model    # пропустить загрузку модели
./install.sh --no-daemon   # пропустить установку launchd агента
```

### Добавить molva в PATH

После установки добавьте в `~/.zshrc`:

```zsh
export PATH="/путь/к/molva/.venv/bin:$PATH"
```

## Использование

### CLI

```zsh
# Транскрибировать файл (sidecar .txt рядом с оригиналом)
molva file.mp4

# Форматы вывода
molva file.mp4 -f srt -f vtt

# Вывод в stdout (для pipe)
molva --stdout file.wav

# Несколько файлов
molva *.mp4 -f srt

# Перезаписать существующие sidecar
molva --overwrite file.mp4

# Форсировать модель без демона
molva --backend gigaam --no-daemon file.mp4
```

### Finder

Правый клик по аудио или видео файлу → **Quick Actions → Molva transcriber**

При запуске появится уведомление «Транскрибирую…», по завершении — «Готово».
Логи: `~/Library/Logs/Molva/quickaction.log`

### Демон

```zsh
molva daemon start    # запустить демон
molva daemon stop     # остановить
molva daemon status   # статус
molva health          # проверить /health
```

Демон автоматически запускается при входе в систему через launchd.
Логи демона: `~/Library/Logs/Molva/daemon.log`

## Форматы вывода

| Формат | Описание |
|--------|----------|
| `txt`  | Чистый текст (по умолчанию) |
| `srt`  | Субтитры с таймингами |
| `vtt`  | WebVTT субтитры |
| `json` | Машиночитаемый (сегменты + тайминги + язык) |

Файлы создаются рядом с исходником: `video.mp4` → `video.txt`, `video.srt` и т.д.

## Диагностика

```zsh
# Проверить что демон работает
molva health

# Посмотреть логи демона
tail -f ~/Library/Logs/Molva/daemon.log

# Посмотреть логи Quick Action
tail -f ~/Library/Logs/Molva/quickaction.log

# Перезапустить launchd агент
./scripts/launchd.sh uninstall && ./scripts/launchd.sh install

# Переустановить Quick Action
./scripts/quickaction.sh uninstall && ./scripts/quickaction.sh install
```

## Удаление

```zsh
./uninstall.sh
```

Скрипт удалит launchd агент, Quick Action, виртуальное окружение (опционально) и модель (опционально).

## Архитектура

```
molva/
├── src/molva/
│   ├── cli.py          # CLI (molva, molva daemon)
│   ├── service.py      # Ядро пайплайна
│   ├── api.py          # FastAPI демон
│   ├── daemon.py       # Управление процессом демона
│   ├── client.py       # HTTP клиент к демону
│   ├── audio.py        # ffmpeg препроцессинг
│   ├── vad.py          # Silero VAD (нарезка по тишине)
│   ├── output.py       # Форматы вывода
│   └── transcriber/
│       ├── base.py     # Интерфейс Transcriber
│       ├── gigaam.py   # GigaAM-v3 транскрайбер
│       └── stub.py     # Заглушка для тестов
├── packaging/
│   ├── com.algusen.molva.plist         # launchd шаблон
│   └── Molva transcriber.workflow/     # Finder Quick Action
├── scripts/
│   ├── launchd.sh      # install/uninstall/status launchd агента
│   └── quickaction.sh  # install/uninstall Quick Action
├── install.sh
└── uninstall.sh
```

**Модель**: [ai-sage/GigaAM-v3](https://huggingface.co/ai-sage/GigaAM-v3), revision `e2e_rnnt`  
**VAD**: silero-vad 5.1+ (автоматическая нарезка длинных файлов по тишине)  
**Демон**: FastAPI + uvicorn, слушает только `127.0.0.1:18080`

## Добавление новых моделей

Molva поддерживает подключение дополнительных транскрайберов через интерфейс `Transcriber` в [`src/molva/transcriber/base.py`](src/molva/transcriber/base.py).

### Шаги

**1. Реализуйте класс транскрайбера:**

```python
# src/molva/transcriber/mymodel.py
from .base import Transcriber, Segment

class MyModelTranscriber(Transcriber):
    def __init__(self, model_path: str, device: str = "mps"):
        # загрузка модели
        ...

    def transcribe(self, audio: "np.ndarray", sample_rate: int, language: str) -> list[Segment]:
        # возвращает список Segment(start, end, text)
        ...
```

**2. Зарегистрируйте бэкенд в фабрике** (`src/molva/api.py`, функция `_make_transcriber`):

```python
elif cfg.backend == "mymodel":
    from .transcriber.mymodel import MyModelTranscriber
    return MyModelTranscriber(cfg.model_path, cfg.device)
```

**3. Скачайте веса модели** в `models/` (путь задаётся через `--model-path` или конфиг).

**4. Запустите с новым бэкендом:**

```zsh
molva --backend mymodel --no-daemon file.mp4
```

### Встроенные бэкенды

| Бэкенд | Описание |
|--------|----------|
| `gigaam` | GigaAM-v3 (русский, Apple Silicon MPS) |
| `stub` | Заглушка для тестов, не требует модели |
