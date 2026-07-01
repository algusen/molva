import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import pytest
from click.testing import CliRunner

from molva import daemon
from molva.cli import main

RATE = 16000
MOLVA_BIN = str(Path(sys.executable).parent / "molva")


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


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tone(tmp_path):
    return _tone_wav(tmp_path / "clip.wav")


@pytest.fixture(autouse=True)
def no_daemon(monkeypatch):
    """Изолирует CLI-тесты от реального демона."""
    monkeypatch.setattr(daemon, "is_running", lambda: False)


# ── 2.1 — разбор аргументов ──────────────────────────────────────────────────

def test_help_shows_flags(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--backend" in result.output
    assert "--stdout" in result.output
    assert "--json" in result.output


def test_no_args_prints_help(runner):
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "molva" in result.output.lower()


def test_missing_file_exits_2(runner):
    result = runner.invoke(main, ["--backend", "stub", "/no/such/file.wav"])
    assert result.exit_code == 2


def test_unsupported_language_exits_2(runner, tone):
    result = runner.invoke(main, ["--backend", "stub", "--lang", "en", tone])
    assert result.exit_code == 2


# ── 2.2 — CLI → service (standalone) ─────────────────────────────────────────

def test_stdout_mode_prints_text(runner, tone):
    result = runner.invoke(main, ["--backend", "stub", "--stdout", tone])
    assert result.exit_code == 0
    assert result.output.strip()


def test_json_mode_valid_json(runner, tone):
    result = runner.invoke(main, ["--backend", "stub", "--json", tone])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "segments" in data
    assert "duration_sec" in data
    assert data["source"] == tone


def test_sidecar_written_for_default_mode(runner, tone, tmp_path):
    result = runner.invoke(main, ["--backend", "stub", "-f", "srt", tone])
    assert result.exit_code == 0
    assert (tmp_path / "clip.srt").exists()


def test_srt_content_is_valid(runner, tone, tmp_path):
    runner.invoke(main, ["--backend", "stub", "-f", "srt", tone])
    srt = (tmp_path / "clip.srt").read_text(encoding="utf-8")
    assert "-->" in srt
    lines = srt.strip().splitlines()
    assert lines[0].strip().isdigit()


def test_subprocess_stdout(tone):
    """e2e: настоящий процесс molva, не CliRunner."""
    result = subprocess.run(
        [MOLVA_BIN, "--no-daemon", "--backend", "stub", "--stdout", tone],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip()


def test_subprocess_json(tone):
    result = subprocess.run(
        [MOLVA_BIN, "--no-daemon", "--backend", "stub", "--json", tone],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "segments" in data
    assert data["source"] == tone


# ── 2.3 — батч и устойчивость ────────────────────────────────────────────────

def test_batch_all_succeed(runner, tmp_path):
    f1 = _tone_wav(tmp_path / "a.wav")
    f2 = _tone_wav(tmp_path / "b.wav")
    result = runner.invoke(main, ["--backend", "stub", "-f", "txt", f1, f2])
    assert result.exit_code == 0
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").exists()


def test_batch_partial_error_exits_2(runner, tmp_path):
    good = _tone_wav(tmp_path / "good.wav")
    result = runner.invoke(main, ["--backend", "stub", "-f", "txt", good, "/no/such/file.wav"])
    assert result.exit_code == 2
    assert (tmp_path / "good.txt").exists()


def test_sidecar_not_overwritten_without_flag(runner, tone, tmp_path):
    runner.invoke(main, ["--backend", "stub", "-f", "txt", tone])
    runner.invoke(main, ["--backend", "stub", "-f", "txt", tone])
    assert (tmp_path / "clip.txt").exists()
    assert (tmp_path / "clip (1).txt").exists()


def test_overwrite_replaces_sidecar(runner, tone, tmp_path):
    runner.invoke(main, ["--backend", "stub", "-f", "txt", tone])
    result = runner.invoke(main, ["--backend", "stub", "-f", "txt", "--overwrite", tone])
    assert result.exit_code == 0
    assert (tmp_path / "clip.txt").exists()
    assert not (tmp_path / "clip (1).txt").exists()


# ── 4.2 — подкоманды daemon/health ───────────────────────────────────────────

def test_daemon_start_success(runner, monkeypatch):
    monkeypatch.setattr(daemon, "is_running", lambda: False)
    monkeypatch.setattr(daemon, "start", lambda host, port: 12345)
    monkeypatch.setattr(daemon, "wait_ready", lambda url, timeout: True)
    result = runner.invoke(main, ["daemon", "start"])
    assert result.exit_code == 0
    assert "12345" in result.output or "готов" in result.output.lower()


def test_daemon_stop_not_running(runner, monkeypatch):
    monkeypatch.setattr(daemon, "is_running", lambda: False)
    monkeypatch.setattr(daemon, "stop", lambda: (_ for _ in ()).throw(RuntimeError("не запущен")))
    result = runner.invoke(main, ["daemon", "stop"])
    assert result.exit_code == 1


def test_daemon_status_stopped(runner, monkeypatch):
    monkeypatch.setattr(daemon, "is_running", lambda: False)
    monkeypatch.setattr(daemon, "status", lambda: "stopped")
    result = runner.invoke(main, ["daemon", "status"])
    assert result.exit_code == 1
    assert "stopped" in result.output


def test_daemon_status_running(runner, monkeypatch):
    from molva import client as pisar_client
    monkeypatch.setattr(daemon, "is_running", lambda: True)
    monkeypatch.setattr(daemon, "status", lambda: "running")
    monkeypatch.setattr(pisar_client, "health", lambda url, **kw: {"status": "ready", "backend": "stub"})
    result = runner.invoke(main, ["daemon", "status"])
    assert result.exit_code == 0
    assert "running" in result.output


def test_health_exits_1_when_unreachable(runner, monkeypatch):
    from molva import client as pisar_client
    monkeypatch.setattr(
        pisar_client, "health",
        lambda url, **kw: (_ for _ in ()).throw(pisar_client.DaemonError("недоступен"))
    )
    result = runner.invoke(main, ["health"])
    assert result.exit_code == 1


def test_health_exits_0_when_ready(runner, monkeypatch):
    from molva import client as pisar_client
    monkeypatch.setattr(
        pisar_client, "health",
        lambda url, **kw: {"status": "ready", "backend": "stub", "model_loaded": True, "version": "0.1.0"}
    )
    result = runner.invoke(main, ["health"])
    assert result.exit_code == 0
