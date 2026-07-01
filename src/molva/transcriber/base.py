"""Протокол Transcriber и модель Segment — контракт между движком и пайплайном.

Формат Segment зафиксирован в CONTRACT.md: start/end в секундах от начала
исходного файла, text непустой и без ведущих/конечных пробелов.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be > start ({self.start})")
        if self.text != self.text.strip() or not self.text:
            raise ValueError("text must be non-empty and have no leading/trailing whitespace")


class Transcriber(Protocol):
    def transcribe(self, wav_path: str, language: str) -> list[Segment]:
        """Транскрибирует WAV-файл (16кГц, mono) и возвращает сегменты по порядку start."""
        ...
