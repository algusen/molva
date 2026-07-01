"""Нарезка длинных WAV-файлов на интервалы речи по паузам.

Основной путь — silero-vad (легковесная ONNX/JIT-модель, не требует сети после
установки пакета). Если silero-vad недоступен (не установлен, модель не грузится),
используется fallback: нарезка фиксированными окнами с перекрытием.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass

SAMPLE_RATE = 16000

# Параметры fallback-нарезки.
FALLBACK_WINDOW_SEC = 20.0
FALLBACK_OVERLAP_SEC = 2.0

# Параметры silero-vad.
MIN_SPEECH_DURATION_MS = 250
MIN_SILENCE_DURATION_MS = 300
SPEECH_PAD_MS = 100

# GigaAM-v3 принимает короткие сегменты (~25с) через transcribe(); непрерывная
# речь без пауз может дать более длинный интервал VAD, поэтому такие интервалы
# дополнительно режутся с небольшим перекрытием.
MAX_INTERVAL_SEC = 20.0
INTERVAL_SPLIT_OVERLAP_SEC = 1.0


@dataclass(frozen=True)
class SpeechInterval:
    start: float
    end: float


def _wav_duration_sec(wav_path: str) -> float:
    with wave.open(wav_path, "rb") as wf:
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        return n_frames / float(rate) if rate else 0.0


def _detect_with_silero(wav_path: str) -> list[SpeechInterval] | None:
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except ImportError:
        return None

    try:
        model = load_silero_vad()
        wav = read_audio(wav_path, sampling_rate=SAMPLE_RATE)
        timestamps = get_speech_timestamps(
            wav,
            model,
            sampling_rate=SAMPLE_RATE,
            min_speech_duration_ms=MIN_SPEECH_DURATION_MS,
            min_silence_duration_ms=MIN_SILENCE_DURATION_MS,
            speech_pad_ms=SPEECH_PAD_MS,
            return_seconds=True,
        )
    except Exception:
        return None

    return [SpeechInterval(start=t["start"], end=t["end"]) for t in timestamps]


def _detect_with_fixed_windows(
    duration_sec: float,
    window_sec: float = FALLBACK_WINDOW_SEC,
    overlap_sec: float = FALLBACK_OVERLAP_SEC,
) -> list[SpeechInterval]:
    if duration_sec <= 0:
        return []

    intervals: list[SpeechInterval] = []
    start = 0.0
    step = max(window_sec - overlap_sec, 1.0)
    while start < duration_sec:
        end = min(start + window_sec, duration_sec)
        intervals.append(SpeechInterval(start=start, end=end))
        if end >= duration_sec:
            break
        start += step
    return intervals


def _split_long_interval(
    interval: SpeechInterval, max_len: float, overlap: float
) -> list[SpeechInterval]:
    splits: list[SpeechInterval] = []
    start = interval.start
    step = max(max_len - overlap, 1.0)
    while True:
        end = min(start + max_len, interval.end)
        splits.append(SpeechInterval(start=start, end=end))
        if end >= interval.end:
            break
        start += step
    return splits


def _cap_interval_lengths(
    intervals: list[SpeechInterval],
    max_len: float = MAX_INTERVAL_SEC,
    overlap: float = INTERVAL_SPLIT_OVERLAP_SEC,
) -> list[SpeechInterval]:
    capped: list[SpeechInterval] = []
    for interval in intervals:
        if interval.end - interval.start <= max_len:
            capped.append(interval)
        else:
            capped.extend(_split_long_interval(interval, max_len, overlap))
    return capped


def detect_speech_intervals(wav_path: str) -> list[SpeechInterval]:
    """Возвращает интервалы речи (в секундах) для 16кГц mono WAV.

    Пытается использовать silero-vad; при недоступности падает на нарезку
    фиксированными перекрывающимися окнами. В обоих случаях интервалы длиннее
    MAX_INTERVAL_SEC дополнительно дробятся — это нужно бэкенду GigaAM-v3,
    чей короткий transcribe() ограничен ~25 секундами.
    """
    duration = _wav_duration_sec(wav_path)
    if duration <= 0:
        return []

    intervals = _detect_with_silero(wav_path)
    if not intervals:
        intervals = _detect_with_fixed_windows(duration)

    return _cap_interval_lengths(intervals)
