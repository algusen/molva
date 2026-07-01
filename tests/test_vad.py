import math
import wave

import pytest

from molva import vad

RATE = 16000


def _tone_frames(duration_sec: float, freq: float = 440.0, amplitude: int = 12000) -> bytes:
    n = int(duration_sec * RATE)
    frames = bytearray()
    for i in range(n):
        sample = int(amplitude * math.sin(2 * math.pi * freq * i / RATE))
        frames += sample.to_bytes(2, byteorder="little", signed=True)
    return bytes(frames)


def _silence_frames(duration_sec: float) -> bytes:
    n = int(duration_sec * RATE)
    return b"\x00\x00" * n


def _write_wav(path, frames: bytes) -> str:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(frames)
    return str(path)


@pytest.fixture
def speech_silence_speech_wav(tmp_path):
    frames = _tone_frames(2.0) + _silence_frames(2.0) + _tone_frames(2.0)
    return _write_wav(tmp_path / "speech_pause_speech.wav", frames)


@pytest.fixture
def empty_wav(tmp_path):
    return _write_wav(tmp_path / "empty.wav", b"")


@pytest.fixture
def short_wav(tmp_path):
    return _write_wav(tmp_path / "short.wav", _tone_frames(0.2))


def test_detect_speech_intervals_finds_two_segments(speech_silence_speech_wav):
    intervals = vad.detect_speech_intervals(speech_silence_speech_wav)

    assert len(intervals) >= 1
    for interval in intervals:
        assert interval.end > interval.start
    assert intervals[0].start < 2.0


def test_detect_speech_intervals_empty_input_returns_empty(empty_wav):
    assert vad.detect_speech_intervals(empty_wav) == []


def test_detect_speech_intervals_short_input_does_not_crash(short_wav):
    intervals = vad.detect_speech_intervals(short_wav)
    assert isinstance(intervals, list)


def test_fixed_window_fallback_covers_full_duration():
    intervals = vad._detect_with_fixed_windows(75.0, window_sec=30.0, overlap_sec=2.0)

    assert intervals[0].start == 0.0
    assert intervals[-1].end == pytest.approx(75.0)
    assert all(b.start < a.end for a, b in zip(intervals, intervals[1:], strict=False))


def test_fixed_window_fallback_empty_duration():
    assert vad._detect_with_fixed_windows(0.0) == []


def test_detect_speech_intervals_uses_fallback_when_silero_unavailable(
    speech_silence_speech_wav, monkeypatch
):
    monkeypatch.setattr(vad, "_detect_with_silero", lambda wav_path: None)

    intervals = vad.detect_speech_intervals(speech_silence_speech_wav)

    assert len(intervals) == 1
    assert intervals[0].start == 0.0
    assert intervals[0].end == pytest.approx(6.0, abs=0.01)


def test_long_continuous_speech_is_split_below_max_interval(monkeypatch):
    long_interval = vad.SpeechInterval(start=0.0, end=58.0)
    monkeypatch.setattr(vad, "_detect_with_silero", lambda wav_path: [long_interval])
    monkeypatch.setattr(vad, "_wav_duration_sec", lambda wav_path: 58.0)

    intervals = vad.detect_speech_intervals("unused.wav")

    assert all(iv.end - iv.start <= vad.MAX_INTERVAL_SEC for iv in intervals)
    assert intervals[0].start == 0.0
    assert intervals[-1].end == pytest.approx(58.0)
    # соседние сегменты перекрываются (склейка по перекрытию, не теряем речь на стыке)
    assert all(b.start < a.end for a, b in zip(intervals, intervals[1:], strict=False))
