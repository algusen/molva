"""StubTranscriber — заглушка движка для тестов без реальной модели.

Читает длительность WAV через стандартный модуль wave (не зависит от ffmpeg/torch)
и нарезает её на фиксированные сегменты с предсказуемым текстом.
"""

from __future__ import annotations

import wave

from molva.transcriber.base import Segment

DEFAULT_SEGMENT_LEN = 5.0


class StubTranscriber:
    def __init__(self, segment_len: float = DEFAULT_SEGMENT_LEN) -> None:
        self.segment_len = segment_len

    def transcribe(self, wav_path: str, language: str) -> list[Segment]:
        duration = self._duration_sec(wav_path)
        if duration <= 0:
            return []

        segments: list[Segment] = []
        start = 0.0
        index = 1
        while start < duration:
            end = min(start + self.segment_len, duration)
            segments.append(
                Segment(start=start, end=end, text=f"Тестовый сегмент {index} ({language}).")
            )
            start = end
            index += 1
        return segments

    @staticmethod
    def _duration_sec(wav_path: str) -> float:
        with wave.open(wav_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate) if rate else 0.0
