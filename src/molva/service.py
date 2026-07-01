"""Сборка пайплайна: препроцессинг -> VAD -> транскрайбер -> сегменты -> sidecar-файлы.

Инференс сериализуется глобальным локом сервиса (один процесс держит одну модель,
параллельные запросы ждут своей очереди, не получают ошибку).
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from molva import audio, output, vad
from molva.transcriber.base import Segment, Transcriber

SUPPORTED_FORMATS = {"txt", "srt", "vtt"}
SUPPORTED_LANGUAGES = {"ru"}


class BadRequestError(ValueError):
    """Невалидные параметры запроса: путь, formats или language."""


class NotReadyError(RuntimeError):
    """Модель ещё не загружена (см. /health)."""


@dataclass(frozen=True)
class TranscribeResult:
    source: str
    outputs: list[str]
    duration_sec: float
    segments: list[Segment]


@dataclass(frozen=True)
class HealthStatus:
    status: str
    backend: str
    model_loaded: bool
    version: str


class MolvaService:
    def __init__(
        self,
        transcriber: Transcriber,
        backend: str,
        version: str = "0.1.0",
        notify: bool = True,
        clipboard: bool = False,
    ) -> None:
        self._transcriber = transcriber
        self._backend = backend
        self._version = version
        self._notify = notify
        self._clipboard = clipboard
        self._lock = threading.Lock()
        self._ready = True
        self._error: str | None = None

    def health(self) -> HealthStatus:
        if self._error is not None:
            status = "error"
        elif self._ready:
            status = "ready"
        else:
            status = "loading"
        return HealthStatus(
            status=status,
            backend=self._backend,
            model_loaded=self._ready,
            version=self._version,
        )

    def transcribe(
        self, path: str, formats: list[str], language: str, *, overwrite: bool = False
    ) -> TranscribeResult:
        self._validate_request(path, formats, language)
        if not self._ready:
            raise NotReadyError("модель ещё не загружена")

        probe_result = audio.probe(path)  # FileNotFoundError / UnsupportedMediaError

        with self._lock:
            tmp_dir = tempfile.mkdtemp(prefix="molva-req-")
            try:
                wav_path = audio.to_wav16k_mono(path, out_dir=tmp_dir)
                intervals = vad.detect_speech_intervals(wav_path)
                segments = self._transcribe_intervals(wav_path, intervals, language, tmp_dir)
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        outputs = output.write_sidecars(path, segments, formats, overwrite=overwrite) if segments else []

        if self._notify:
            output.notify("Molva", f"Готово: {Path(path).name}")
        if self._clipboard and segments:
            output.copy_to_clipboard(output.render_txt(segments))

        return TranscribeResult(
            source=path,
            outputs=outputs,
            duration_sec=probe_result.duration_sec,
            segments=segments,
        )

    def _transcribe_intervals(
        self,
        wav_path: str,
        intervals: list[vad.SpeechInterval],
        language: str,
        tmp_dir: str,
    ) -> list[Segment]:
        segments: list[Segment] = []
        for interval in intervals:
            sub_wav = audio.extract_wav_segment(
                wav_path, interval.start, interval.end, out_dir=tmp_dir
            )
            for seg in self._transcriber.transcribe(sub_wav, language):
                segments.append(
                    Segment(
                        start=seg.start + interval.start,
                        end=seg.end + interval.start,
                        text=seg.text,
                    )
                )
        segments.sort(key=lambda s: s.start)
        return segments

    @staticmethod
    def _validate_request(path: str, formats: list[str], language: str) -> None:
        if not Path(path).is_absolute():
            raise BadRequestError("path должен быть абсолютным")
        if not formats:
            raise BadRequestError("formats не может быть пустым")
        unsupported = set(formats) - SUPPORTED_FORMATS
        if unsupported:
            raise BadRequestError(f"неподдерживаемые formats: {sorted(unsupported)}")
        if language not in SUPPORTED_LANGUAGES:
            raise BadRequestError(f"неподдерживаемый language: {language}")
