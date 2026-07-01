"""HTTP-клиент для общения с работающим демоном Molva."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from molva.service import TranscribeResult
from molva.transcriber.base import Segment


class DaemonError(RuntimeError):
    """Ошибка при запросе к демону (HTTP 4xx/5xx или сеть)."""


def health(url: str, timeout: float = 2.0) -> dict:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise DaemonError(f"демон недоступен: {exc.reason}") from exc


def transcribe(
    url: str,
    path: str,
    formats: list[str],
    language: str,
    timeout: float = 600.0,
) -> TranscribeResult:
    payload = json.dumps({"path": path, "formats": formats, "language": language}).encode()
    req = urllib.request.Request(
        f"{url}/transcribe",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read())
        raise DaemonError(body.get("detail", str(exc))) from exc
    except urllib.error.URLError as exc:
        raise DaemonError(f"демон недоступен: {exc.reason}") from exc

    return TranscribeResult(
        source=data["source"],
        outputs=data["outputs"],
        duration_sec=data["duration_sec"],
        segments=[Segment(s["start"], s["end"], s["text"]) for s in data["segments"]],
    )
