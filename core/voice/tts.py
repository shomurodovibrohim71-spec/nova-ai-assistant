"""Text-to-speech via pyttsx3 (Windows SAPI under the hood, zero downloads)."""
from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger(__name__)


class SapiTTS:
    """Synchronous TTS wrapper.

    pyttsx3 has known re-entrancy issues on Windows; we lock around runAndWait
    and re-init the engine if it gets wedged.
    """

    def __init__(self, rate: int = 180, voice_hint: str | None = None) -> None:
        self._rate = rate
        self._voice_hint = voice_hint
        self._lock = threading.Lock()
        self._engine: Any = None

    def _init_engine(self) -> Any:
        import pyttsx3  # lazy

        eng = pyttsx3.init()
        eng.setProperty("rate", self._rate)
        if self._voice_hint:
            for v in eng.getProperty("voices"):
                if self._voice_hint.lower() in (v.name or "").lower():
                    eng.setProperty("voice", v.id)
                    break
        return eng

    def speak(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            try:
                if self._engine is None:
                    self._engine = self._init_engine()
                self._engine.say(text)
                self._engine.runAndWait()
            except RuntimeError:
                log.warning("pyttsx3 wedged — reinitializing")
                self._engine = self._init_engine()
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception:
                log.exception("TTS failed")
