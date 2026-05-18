"""Speech-to-text via faster-whisper."""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class WhisperSTT:
    """Lazy-loaded faster-whisper.

    model_size="tiny"    → multilingual, ~75MB, works for Uzbek/Russian/English
    model_size="tiny.en" → English-only, slightly faster
    """

    def __init__(self, model_size: str = "tiny", device: str = "cpu", compute_type: str = "int8") -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Any = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        log.info("loading whisper model %s (device=%s)", self.model_size, self.device)
        t0 = time.time()
        self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        log.info("whisper ready in %.1fs", time.time() - t0)

    def transcribe(self, audio: np.ndarray, samplerate: int = 16_000) -> str:
        if audio.size == 0:
            return ""
        self._ensure_model()
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(
            audio,
            language=None,          # auto-detect: Uzbek, Russian, English all work
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    def transcribe_file(self, path: str, language: str | None = None) -> tuple[str, str]:
        """Transcribe a file. Returns (text, detected_language_code).

        language=None → auto-detect.
        language="uz"  → force Uzbek.
        language="en"  → force English.
        """
        self._ensure_model()
        segments, info = self._model.transcribe(
            path,
            language=language,
            beam_size=5,
            best_of=5,
            vad_filter=True,
            condition_on_previous_text=True,
            initial_prompt="Nova AI assistant. Uzbek yoki ingliz tilida buyruq.",
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        detected = info.language or "en"
        log.info("transcribed %s | lang=%s | duration=%.1fs | text=%r",
                 path, detected, info.duration, text[:80])
        return text, detected
