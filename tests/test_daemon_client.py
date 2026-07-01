"""Тесты daemon.py и client.py — без реального запуска процессов."""

from __future__ import annotations

import json
import math
import threading
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from molva import daemon, client as pisar_client
from molva.api import create_app
from molva.service import MolvaService
from molva.transcriber.stub import StubTranscriber

RATE = 16000


def _tone_wav(path, duration_sec=2.0) -> str:
    n = int(duration_sec * RATE)
    frames = bytearray()
    for i in range(n):
        sample = int(12000 * math.sin(2 * math.pi * 440 * i / RATE))
        frames += sample.to_bytes(2, byteorder="little", signed=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(bytes(frames))
    return str(path)


# ── daemon.py — PID-файл ──────────────────────────────────────────────────────

def test_is_running_false_when_no_pid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "PID_FILE", tmp_path / "daemon.pid")
    assert daemon.is_running() is False


def test_is_running_false_when_pid_file_stale(tmp_path, monkeypatch):
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("999999999")  # несуществующий PID
    monkeypatch.setattr(daemon, "PID_FILE", pid_file)
    assert daemon.is_running() is False
    assert not pid_file.exists()  # файл убран автоматически


def test_is_running_true_for_own_pid(tmp_path, monkeypatch):
    import os
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text(str(os.getpid()))
    monkeypatch.setattr(daemon, "PID_FILE", pid_file)
    assert daemon.is_running() is True


def test_status_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "PID_FILE", tmp_path / "daemon.pid")
    assert daemon.status() == "stopped"


def test_base_url_format():
    assert daemon.base_url("127.0.0.1", 8765) == "http://127.0.0.1:8765"


# ── client.py — через реальный TestClient-сервер в треде ─────────────────────

@pytest.fixture
def live_server(tmp_path):
    """Запускает FastAPI-приложение на случайном порту в фоновом потоке."""
    import socket
    import uvicorn

    service = MolvaService(transcriber=StubTranscriber(), backend="stub", notify=False)
    app = create_app(service)

    # Находим свободный порт.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Ждём готовности.
    import time
    for _ in range(50):
        try:
            pisar_client.health(f"http://127.0.0.1:{port}", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)

    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def test_client_health(live_server):
    data = pisar_client.health(live_server)
    assert data["status"] == "ready"
    assert data["backend"] == "stub"


def test_client_transcribe(live_server, tmp_path):
    wav = _tone_wav(tmp_path / "clip.wav")
    result = pisar_client.transcribe(live_server, wav, ["txt"], "ru")
    assert result.source == wav
    assert result.duration_sec > 0
    assert len(result.segments) >= 1
    assert (tmp_path / "clip.txt").exists()


def test_client_health_unreachable():
    with pytest.raises(pisar_client.DaemonError):
        pisar_client.health("http://127.0.0.1:1", timeout=0.5)


def test_client_transcribe_missing_file(live_server, tmp_path):
    with pytest.raises(pisar_client.DaemonError):
        pisar_client.transcribe(live_server, "/no/such/file.wav", ["txt"], "ru")
