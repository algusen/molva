"""GigaAMTranscriber — реализация Transcriber на базе ai-sage/GigaAM-v3 (revision e2e_rnnt).

Требует extra-зависимостей: pip install -e ".[gigaam]" (torch, torchaudio, transformers...).

Два источника модели:
  1. Локальная папка (model_path): models/GigaAM-v3-e2e_rnnt/ в корне проекта —
     скачивается один раз через `make download-model`, работает полностью офлайн.
  2. HuggingFace Hub (model_path=None): кэшируется в ~/.cache/huggingface/hub/,
     требует интернет при первом запуске.

pyannote-audio (нужна для transcribe_longform) не используется — сегментацию делает
silero-vad в service.py, поэтому transcribe() вызывается на VAD-отрезках ≤ 20 с.
"""

from __future__ import annotations

import wave
from pathlib import Path

from molva.transcriber.base import Segment

HF_MODEL_ID = "ai-sage/GigaAM-v3"
DEFAULT_REVISION = "e2e_rnnt"


class GigaAMTranscriber:
    def __init__(
        self,
        device: str | None = None,
        model_path: str | Path | None = None,
        revision: str = DEFAULT_REVISION,
    ) -> None:
        try:
            import torch
            from transformers import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "GigaAMTranscriber требует установки molva[gigaam]: "
                'pip install -e ".[gigaam]"  (torch, torchaudio, transformers)'
            ) from exc

        self._torch = torch
        self._device = device or self._pick_device(torch)

        source = str(model_path) if model_path else HF_MODEL_ID
        kwargs: dict = {"trust_remote_code": True}
        if not model_path:
            kwargs["revision"] = revision

        self._model = AutoModel.from_pretrained(source, **kwargs)
        self._model.to(self._device)
        self._model.eval()

    @staticmethod
    def _pick_device(torch_module) -> str:
        if torch_module.backends.mps.is_available():
            return "mps"
        if torch_module.cuda.is_available():
            return "cuda"
        return "cpu"

    def transcribe(self, wav_path: str, language: str) -> list[Segment]:
        del language  # модель обучена только на русском; параметр принят для соответствия протоколу

        with self._torch.inference_mode():
            try:
                text = self._model.transcribe(wav_path)
            except RuntimeError:
                if self._device != "cpu":
                    # MPS/CUDA может не поддерживать отдельные операции — откатываемся на CPU
                    self._model.to("cpu")
                    self._device = "cpu"
                    text = self._model.transcribe(wav_path)
                else:
                    raise

        text = text.strip() if text else ""
        if not text:
            return []

        duration = self._wav_duration_sec(wav_path)
        return [Segment(start=0.0, end=max(duration, 0.01), text=text)]

    @staticmethod
    def _wav_duration_sec(wav_path: str) -> float:
        with wave.open(wav_path, "rb") as wf:
            rate = wf.getframerate()
            return wf.getnframes() / float(rate) if rate else 0.0
