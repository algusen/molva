import wave
from pathlib import Path

import pytest


def _write_silence_wav(path: Path, duration_sec: float, rate: int = 16000) -> None:
    n_frames = int(duration_sec * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * n_frames)


@pytest.fixture
def make_wav(tmp_path):
    def _make(duration_sec: float, name: str = "test.wav") -> str:
        path = tmp_path / name
        _write_silence_wav(path, duration_sec)
        return str(path)

    return _make
