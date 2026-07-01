"""Запись sidecar-файлов (.txt/.srt/.vtt) рядом с исходником + уведомления/буфер обмена.

Форматы и правило именования зафиксированы в CONTRACT.md. Уведомления и копирование
в буфер — no-op вне macOS (используются в тестах на Linux), реальные хуки на macOS
через terminal-notifier/osascript и pbcopy.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from molva.transcriber.base import Segment

SUPPORTED_FORMATS = ("txt", "srt", "vtt")


def _format_timestamp(seconds: float, *, decimal_sep: str) -> str:
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal_sep}{ms:03d}"


def render_txt(segments: list[Segment]) -> str:
    return "\n\n".join(s.text for s in segments)


def render_srt(segments: list[Segment]) -> str:
    blocks = []
    for i, s in enumerate(segments, start=1):
        start_ts = _format_timestamp(s.start, decimal_sep=",")
        end_ts = _format_timestamp(s.end, decimal_sep=",")
        blocks.append(f"{i}\n{start_ts} --> {end_ts}\n{s.text}")
    return "\n\n".join(blocks)


def render_vtt(segments: list[Segment]) -> str:
    blocks = ["WEBVTT"]
    for s in segments:
        start_ts = _format_timestamp(s.start, decimal_sep=".")
        end_ts = _format_timestamp(s.end, decimal_sep=".")
        blocks.append(f"{start_ts} --> {end_ts}\n{s.text}")
    return "\n\n".join(blocks)


_RENDERERS = {
    "txt": render_txt,
    "srt": render_srt,
    "vtt": render_vtt,
}


def resolve_output_path(source_path: str, fmt: str) -> Path:
    """Находит первый свободный путь <name>.<fmt>, <name> (1).<fmt>, ... ."""
    source = Path(source_path)
    candidate = source.with_suffix(f".{fmt}")
    if not candidate.exists():
        return candidate

    n = 1
    while True:
        candidate = source.with_name(f"{source.stem} ({n}).{fmt}")
        if not candidate.exists():
            return candidate
        n += 1


def write_sidecars(
    source_path: str,
    segments: list[Segment],
    formats: list[str],
    *,
    overwrite: bool = False,
) -> list[str]:
    """Пишет sidecar-файлы рядом с исходником для каждого формата, возвращает пути."""
    written: list[str] = []
    for fmt in formats:
        if fmt not in _RENDERERS:
            raise ValueError(f"неизвестный формат вывода: {fmt}")
        content = _RENDERERS[fmt](segments)
        if overwrite:
            out_path = Path(source_path).with_suffix(f".{fmt}")
        else:
            out_path = resolve_output_path(source_path, fmt)
        out_path.write_text(content, encoding="utf-8")
        written.append(str(out_path))
    return written


def notify(title: str, message: str) -> None:
    """Системное уведомление. No-op вне macOS или если нет terminal-notifier/osascript."""
    if sys.platform != "darwin":
        return

    if shutil.which("terminal-notifier"):
        subprocess.run(
            ["terminal-notifier", "-title", title, "-message", message],
            capture_output=True,
            check=False,
        )
        return

    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, check=False)


def copy_to_clipboard(text: str) -> None:
    """Копирует текст в буфер обмена. No-op вне macOS."""
    if sys.platform != "darwin":
        return
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False)
