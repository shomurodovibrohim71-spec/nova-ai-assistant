"""Voice pipeline orchestration.

Modes
-----
- ptt   : press Enter to start talking, press Enter again (or auto via VAD silence) to stop.
- wake  : continuous listen for "Hey Nova" wake word, then capture utterance.
- once  : capture one utterance immediately, transcribe, reply, exit.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Literal

import numpy as np

from ..orchestrator import Orchestrator
from .audio import FRAME_SAMPLES, SAMPLE_RATE, frames_to_float32, open_microphone
from .stt import WhisperSTT
from .tts import SapiTTS
from .vad import EnergyVAD

log = logging.getLogger(__name__)
Mode = Literal["ptt", "wake", "once"]

MAX_UTTERANCE_S = 12
SILENCE_END_MS = 700  # close recording after this much trailing silence


@dataclass
class VoiceConfig:
    mode: Mode = "ptt"
    stt_model: str = "tiny.en"
    wake_model: str = "hey_jarvis"
    wake_threshold: float = 0.5
    tts_rate: int = 180


class VoicePipeline:
    def __init__(self, orchestrator: Orchestrator, cfg: VoiceConfig) -> None:
        self.orchestrator = orchestrator
        self.cfg = cfg
        self.stt = WhisperSTT(model_size=cfg.stt_model)
        self.tts = SapiTTS(rate=cfg.tts_rate)
        self.vad = EnergyVAD()

    # ---------- public entry points ----------

    async def run(self) -> None:
        if self.cfg.mode == "wake":
            await self._run_wake()
        elif self.cfg.mode == "once":
            await self._run_once()
        else:
            await self._run_ptt()

    # ---------- modes ----------

    async def _run_once(self) -> None:
        print("Listening once... speak now.")
        utterance = await self._capture_until_silence()
        await self._handle(utterance)

    async def _run_ptt(self) -> None:
        print("\n  Push-to-talk mode.  Press [Enter] to speak, then stop talking.")
        print("  Ctrl+C to quit.\n")
        loop = asyncio.get_running_loop()
        while True:
            try:
                await loop.run_in_executor(None, input, ">> press Enter to talk: ")
            except (EOFError, KeyboardInterrupt):
                return
            print("  recording... (auto-stops on silence)")
            utterance = await self._capture_until_silence()
            await self._handle(utterance)

    async def _run_wake(self) -> None:
        from .wake import WakeWordDetector

        detector = WakeWordDetector(self.cfg.wake_model, self.cfg.wake_threshold)
        print(f"\n  Wake-word mode — say '{self.cfg.wake_model.replace('_', ' ')}'.  Ctrl+C to quit.\n")

        with open_microphone() as mic:
            while True:
                frame = await asyncio.get_running_loop().run_in_executor(None, mic.get)
                # openWakeWord buffers internally; feed it every frame
                if detector.fire(frame):
                    self.tts.speak("Yes?")
                    utterance = await self._capture_until_silence(mic=mic)
                    await self._handle(utterance)

    # ---------- shared capture ----------

    async def _capture_until_silence(self, mic: queue.Queue | None = None) -> np.ndarray:
        """Record until trailing silence or hard timeout."""
        loop = asyncio.get_running_loop()
        owns_mic = mic is None
        ctx = open_microphone() if owns_mic else _NullCtx(mic)
        with ctx as q:
            self.vad.reset()
            frames: list[np.ndarray] = []
            start = time.time()
            silence_frames = 0
            silence_limit = SILENCE_END_MS // 30  # 30ms per frame
            saw_speech = False

            while True:
                frame = await loop.run_in_executor(None, q.get)
                frames.append(frame)
                speaking = self.vad.is_speech(frame)
                if speaking:
                    saw_speech = True
                    silence_frames = 0
                else:
                    silence_frames += 1

                if saw_speech and silence_frames >= silence_limit:
                    break
                if time.time() - start > MAX_UTTERANCE_S:
                    log.warning("utterance hit max duration")
                    break

        return frames_to_float32(frames)

    # ---------- handle one utterance ----------

    async def _handle(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        loop = asyncio.get_running_loop()
        t0 = time.time()
        text = await loop.run_in_executor(None, self.stt.transcribe, audio)
        log.info("STT (%.2fs): %r", time.time() - t0, text)
        if not text:
            return
        print(f"  you: {text}")

        spoke_streaming = False

        async def on_event(ev: dict) -> None:
            nonlocal spoke_streaming
            if ev["type"] == "sentence":
                spoke_streaming = True
                # speak each completed sentence in the background as it arrives
                asyncio.create_task(loop.run_in_executor(None, self.tts.speak, ev["text"]))
            elif ev["type"] == "tool_use":
                print(f"  [tool] {ev['name']}({ev['input']})")

        result = await self.orchestrator.handle_text(text, source="voice", on_event=on_event)
        reply = result.get("reply", "")
        print(f"  nova: {reply}\n")
        # If nothing streamed (regex skill, or LLM unavailable), speak the whole reply now.
        if not spoke_streaming and reply:
            await loop.run_in_executor(None, self.tts.speak, reply)


class _NullCtx:
    """Pass-through context manager for an already-open mic queue."""

    def __init__(self, q: queue.Queue) -> None:
        self.q = q

    def __enter__(self) -> queue.Queue:
        return self.q

    def __exit__(self, *_: object) -> None:
        return None
