"""Управление жизненным циклом демона Molva (PID-файл, запуск, остановка)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

MOLVA_DIR = Path.home() / ".molva"
PID_FILE = MOLVA_DIR / "daemon.pid"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def is_running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    if not _process_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        return False
    return True


def base_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}"


def start(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    """Запускает molva-daemon в фоне, возвращает PID."""
    if is_running():
        pid = _read_pid()
        raise RuntimeError(f"демон уже запущен (PID {pid})")

    MOLVA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = MOLVA_DIR / "daemon.log"
    daemon_bin = Path(sys.executable).parent / "molva-daemon"

    with log_path.open("a") as log:
        proc = subprocess.Popen(
            [str(daemon_bin)],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    PID_FILE.write_text(str(proc.pid))
    return proc.pid


def stop() -> int:
    """Останавливает демон через SIGTERM, возвращает PID."""
    pid = _read_pid()
    if pid is None or not _process_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        raise RuntimeError("демон не запущен")

    os.kill(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    return pid


def status() -> str:
    return "running" if is_running() else "stopped"


def wait_ready(url: str, timeout: float = 60.0, poll: float = 1.0) -> bool:
    """Ждёт, пока /health вернёт status=ready. Возвращает True при успехе."""
    import json
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2.0) as resp:
                data = json.loads(resp.read())
                if data.get("status") == "ready":
                    return True
        except Exception:
            pass
        time.sleep(poll)
    return False
