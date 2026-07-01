import math
import threading
import time
import wave

import pytest
from fastapi.testclient import TestClient

from molva.api import create_app
from molva.service import MolvaService
from molva.transcriber.base import Segment
from molva.transcriber.stub import StubTranscriber

RATE = 16000


def _tone_wav(path, duration_sec=3.0, freq=440.0, amplitude=12000) -> str:
    n = int(duration_sec * RATE)
    frames = bytearray()
    for i in range(n):
        sample = int(amplitude * math.sin(2 * math.pi * freq * i / RATE))
        frames += sample.to_bytes(2, byteorder="little", signed=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(bytes(frames))
    return str(path)


class TrackingStubTranscriber:
    """Считает максимальное число одновременных вызовов transcribe()."""

    def __init__(self, delay: float = 0.1) -> None:
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def transcribe(self, wav_path: str, language: str) -> list[Segment]:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(self.delay)
        with self._lock:
            self.active -= 1
        return [Segment(start=0.0, end=1.0, text="тест")]


@pytest.fixture
def client():
    service = MolvaService(transcriber=StubTranscriber(), backend="stub")
    return TestClient(create_app(service))


@pytest.fixture
def tone_path(tmp_path):
    return _tone_wav(tmp_path / "tone.wav")


def test_health_reports_ready_with_stub_backend(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["backend"] == "stub"
    assert body["model_loaded"] is True


def test_transcribe_returns_segments_for_valid_file(client, tone_path):
    resp = client.post("/transcribe", json={"path": tone_path, "formats": ["txt", "srt"]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["source"] == tone_path
    assert body["duration_sec"] == pytest.approx(3.0, abs=0.2)
    assert len(body["segments"]) >= 1
    assert body["segments"][0]["text"]
    assert body["outputs"] == [
        tone_path.rsplit(".", 1)[0] + ".txt",
        tone_path.rsplit(".", 1)[0] + ".srt",
    ]
    for out_path in body["outputs"]:
        assert out_path.endswith(".txt") or out_path.endswith(".srt")


def test_transcribe_relative_path_returns_400(client):
    resp = client.post("/transcribe", json={"path": "relative/path.wav"})

    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_request"


def test_transcribe_missing_file_returns_404(client):
    resp = client.post("/transcribe", json={"path": "/no/such/file.wav"})

    assert resp.status_code == 404
    assert resp.json()["error"] == "file_not_found"


def test_transcribe_unsupported_language_returns_400(client, tone_path):
    resp = client.post("/transcribe", json={"path": tone_path, "language": "en"})

    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_request"


def test_transcribe_empty_formats_returns_400(client, tone_path):
    resp = client.post("/transcribe", json={"path": tone_path, "formats": []})

    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_request"


def test_concurrent_transcribe_requests_are_serialized(tone_path, tmp_path):
    tracker = TrackingStubTranscriber(delay=0.15)
    service = MolvaService(transcriber=tracker, backend="stub")
    client = TestClient(create_app(service))

    second_tone = _tone_wav(tmp_path / "tone2.wav")
    results = []

    def call(path):
        results.append(client.post("/transcribe", json={"path": path}).status_code)

    t1 = threading.Thread(target=call, args=(tone_path,))
    t2 = threading.Thread(target=call, args=(second_tone,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results == [200, 200]
    assert tracker.max_active == 1
