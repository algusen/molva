"""Препроцессинг аудио/видео через ffmpeg: проверка входа и приведение к 16кГц mono WAV.

Контракт ошибок (см. CONTRACT.md):
- FfmpegNotFoundError  -> 422/500 уровень сервиса должен трактовать как preprocessing_failed
- UnsupportedMediaError -> 415 unsupported_media
- PreprocessingError    -> 422 preprocessing_failed
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

TARGET_RATE = 16000
TARGET_CHANNELS = 1


class FfmpegNotFoundError(RuntimeError):
    """ffmpeg/ffprobe не найдены в PATH."""


class UnsupportedMediaError(RuntimeError):
    """Файл не распознан как аудио/видео (нет аудиодорожки или формат не читается)."""


class PreprocessingError(RuntimeError):
    """ffmpeg запустился, но завершился с ошибкой при конвертации."""


@dataclass(frozen=True)
class ProbeResult:
    duration_sec: float
    has_audio: bool
    codec: str | None


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FfmpegNotFoundError(f"'{name}' не найден в PATH — установите ffmpeg")
    return path


def probe(input_path: str) -> ProbeResult:
    """Определяет длительность и наличие аудиодорожки через ffprobe."""
    ffprobe = _require_binary("ffprobe")
    if not Path(input_path).is_file():
        raise FileNotFoundError(input_path)

    cmd = [
        ffprobe,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        input_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise UnsupportedMediaError(f"ffprobe не смог прочитать файл: {proc.stderr.strip()}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise UnsupportedMediaError("ffprobe вернул нечитаемый вывод") from exc

    streams = data.get("streams", [])
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not audio_streams:
        raise UnsupportedMediaError("во входном файле не найдена аудиодорожка")

    fmt = data.get("format", {})
    duration_raw = fmt.get("duration")
    try:
        duration = float(duration_raw) if duration_raw is not None else 0.0
    except ValueError:
        duration = 0.0

    return ProbeResult(
        duration_sec=duration,
        has_audio=True,
        codec=audio_streams[0].get("codec_name"),
    )


def to_wav16k_mono(input_path: str, out_dir: str | None = None) -> str:
    """Конвертирует вход в 16кГц mono WAV во временном (или указанном) каталоге.

    Возвращает путь к созданному WAV-файлу. Вызывающий отвечает за удаление.
    """
    ffmpeg = _require_binary("ffmpeg")
    if not Path(input_path).is_file():
        raise FileNotFoundError(input_path)

    probe(input_path)  # бросит UnsupportedMediaError, если нет аудио

    target_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="molva-"))
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / (Path(input_path).stem + ".wav")

    cmd = [
        ffmpeg,
        "-y",
        "-i", input_path,
        "-ac", str(TARGET_CHANNELS),
        "-ar", str(TARGET_RATE),
        "-vn",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise PreprocessingError(f"ffmpeg завершился с ошибкой: {proc.stderr.strip()}")

    return str(out_path)


def extract_wav_segment(
    wav_path: str, start_sec: float, end_sec: float, out_dir: str | None = None
) -> str:
    """Вырезает фрагмент [start_sec, end_sec) из уже готового 16кГц mono WAV.

    Работает напрямую через stdlib wave (без повторного вызова ffmpeg), т.к. вход
    уже приведён к целевому формату через to_wav16k_mono().
    """
    target_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="molva-seg-"))
    target_dir.mkdir(parents=True, exist_ok=True)

    with wave.open(wav_path, "rb") as src:
        rate = src.getframerate()
        n_channels = src.getnchannels()
        sampwidth = src.getsampwidth()
        n_frames = src.getnframes()
        start_frame = max(int(start_sec * rate), 0)
        end_frame = min(int(end_sec * rate), n_frames)
        src.setpos(min(start_frame, n_frames))
        data = src.readframes(max(end_frame - start_frame, 0))

    out_path = target_dir / f"{Path(wav_path).stem}_{start_frame}_{end_frame}.wav"
    with wave.open(str(out_path), "wb") as dst:
        dst.setnchannels(n_channels)
        dst.setsampwidth(sampwidth)
        dst.setframerate(rate)
        dst.writeframes(data)

    return str(out_path)
