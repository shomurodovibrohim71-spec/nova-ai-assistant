"""Wake-word detection via openWakeWord (optional)."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class WakeWordDetector:
    """Wraps openWakeWord. Emits True once when wake-word confidence crosses threshold.

    Default model 'hey_jarvis' ships with the openWakeWord package — we use it
    until we train a dedicated 'hey_nova' model later.
    """

    def __init__(self, model_name: str = "hey_jarvis", threshold: float = 0.5) -> None:
        self.model_name = model_name
        self.threshold = threshold
        self._model: Any = None
        self._cooldown = 0

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        from openwakeword.model import Model  # lazy

        log.info("loading wake-word model %s", self.model_name)
        self._model = Model(wakeword_models=[self.model_name], inference_framework="onnx")

    def fire(self, frame: np.ndarray) -> bool:
        self._ensure_model()
        # openWakeWord expects int16 PCM at 16kHz, ~80ms chunks. Caller feeds frames.
        scores: dict[str, float] = self._model.predict(frame)  # type: ignore[assignment]
        score = max(scores.values()) if scores else 0.0
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        if score >= self.threshold:
            self._cooldown = 50  # ~1.5s of frames before we can fire again
            log.info("wake-word fired (score=%.2f)", score)
            return True
        return False
