"""Energy-based voice-activity detection.

Light, dependency-free. Phase 4 can swap this for Silero VAD if we want
better noise rejection — the interface (`is_speech(frame)`) stays the same.
"""
from __future__ import annotations

import numpy as np


class EnergyVAD:
    """Simple RMS-threshold VAD with hysteresis."""

    def __init__(self, threshold: float = 350.0, hangover_frames: int = 12) -> None:
        self.threshold = threshold
        self.hangover_frames = hangover_frames
        self._silence_run = 0

    def is_speech(self, frame: np.ndarray) -> bool:
        # frame is int16; RMS in linear amplitude space
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2) + 1e-9))
        if rms >= self.threshold:
            self._silence_run = 0
            return True
        self._silence_run += 1
        # hangover: still consider it speech for N frames after last loud frame
        return self._silence_run < self.hangover_frames

    def reset(self) -> None:
        self._silence_run = 0
