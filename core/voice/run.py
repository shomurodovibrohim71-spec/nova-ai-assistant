"""CLI entry point: python -m core.voice.run [--mode ptt|wake|once]"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running as a script (python core/voice/run.py)
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.config import settings
from core.llm import LLMRouter
from core.logging_setup import setup_logging
from core.memory import MemoryService
from core.orchestrator import EventBus, Orchestrator
from core.skills import SkillRegistry
from core.skills.builtins import load_builtin_skills
from core.voice.pipeline import VoiceConfig, VoicePipeline


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Nova voice loop")
    p.add_argument("--mode", choices=["ptt", "wake", "once"], default="ptt")
    p.add_argument("--stt-model", default="tiny.en", help="faster-whisper model size")
    p.add_argument("--wake-model", default="hey_jarvis")
    p.add_argument("--wake-threshold", type=float, default=0.5)
    p.add_argument("--tts-rate", type=int, default=180)
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    setup_logging()

    bus = EventBus()
    registry = SkillRegistry()
    memory = MemoryService(settings)
    load_builtin_skills(registry, memory=memory)
    llm = LLMRouter(registry, bus, memory=memory)
    orch = Orchestrator(registry, bus, llm=llm, memory=memory)

    cfg = VoiceConfig(
        mode=args.mode,
        stt_model=args.stt_model,
        wake_model=args.wake_model,
        wake_threshold=args.wake_threshold,
        tts_rate=args.tts_rate,
    )
    pipeline = VoicePipeline(orch, cfg)

    logging.getLogger("nova.voice").info("starting voice pipeline mode=%s", cfg.mode)
    try:
        await pipeline.run()
    except KeyboardInterrupt:
        print("\n  goodbye, sir.")


if __name__ == "__main__":
    asyncio.run(main())
