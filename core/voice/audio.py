"""Microphone capture utilities. Yields int16 PCM frames."""
from __future__ import annotations

import logging
import queue
from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480 samples per 30ms frame


@contextmanager
def open_microphone(samplerate: int = SAMPLE_RATE, frame_samples: int = FRAME_SAMPLES) -> Iterator[queue.Queue[np.ndarray]]:
    """Context manager yielding a queue of int16 PCM mono frames."""
    import sounddevice as sd  # lazy: only required for voice mode

    q: queue.Queue[np.ndarray] = queue.Queue()

    def _callback(indata, frames, time_info, status) -> None:
        if status:
            log.debug("mic status: %s", status)
        q.put(indata.copy().reshape(-1))

    stream = sd.InputStream(
        samplerate=samplerate,
        channels=1,
        dtype="int16",
        blocksize=frame_samples,
        callback=_callback,
    )
    stream.start()
    log.info("microphone open  (%d Hz, %d-sample frames)", samplerate, frame_samples)
    try:
        yield q
    finally:
        stream.stop()
        stream.close()
        log.info("microphone closed")


def frames_to_float32(frames: list[np.ndarray]) -> np.ndarray:
    """Concatenate int16 frames into a normalized float32 array suitable for Whisper."""
    if not frames:
        return np.zeros(0, dtype=np.float32)
    pcm = np.concatenate(frames).astype(np.float32) / 32768.0
    return pcm
