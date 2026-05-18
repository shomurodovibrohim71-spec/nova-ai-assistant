# Nova

Voice-first AI assistant inspired by JARVIS from Iron Man.
Modular, async, local-first, Claude-powered.

## Status

**Phase 5 — Real skills (current).** File operations (list/find/move/copy/delete with safety guards) and web research (search + fetch + main-text extraction) are now first-class skills, exposed both via regex fast path and as Claude tools. Path operations are sandboxed to `NOVA_FILE_ROOT` (your home dir by default); deletion requires explicit `confirm=true`.
Plus Phases 1–4: Core API, voice loop, Claude tool-use with streaming TTS, three-tier memory.

UI and mobile come in later phases — see [Roadmap](#roadmap).

### Set your API key

```powershell
# Get one at https://console.anthropic.com/, then:
notepad .env        # set ANTHROPIC_API_KEY=sk-ant-...
```

Without an API key, the regex fast path still works; conversational queries fall back to a "brain offline" message.

## Architecture

```
Client (WS/REST)
        │
   Orchestrator ── Event Bus
        │
   Skill Registry ── { ping, open_app, system_info, ... }
```

The Orchestrator does deterministic regex routing today (the "fast path").
Phase 3 adds an LLM-backed intent classifier as a fallback.

Full design lives in this repo's conversation history; key decisions:
- **Python + asyncio** core
- **Local-first voice** (faster-whisper STT + Piper TTS + openWakeWord)
- **3-tier memory**: Redis (working) + SQLite (structured) + ChromaDB (semantic)
- **Claude API** (Sonnet 4.6 default, Opus 4.7 for hard reasoning) with prompt caching

## Quickstart

```powershell
# 1. Create venv (Python 3.11+)
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install
pip install -r requirements.txt

# 3. Configure
copy .env.example .env

# 4. Smoke test (no server)
python scripts\smoke_test.py

# 5. Run the API
python -m core.api.main
# or, after `pip install -e .`:
nova
```

Server listens on `http://127.0.0.1:8765` by default.

### Try it

```powershell
# Health
curl http://127.0.0.1:8765/health

# List loaded skills
curl http://127.0.0.1:8765/skills

# Send a command
curl -X POST http://127.0.0.1:8765/command `
     -H "Content-Type: application/json" `
     -d '{\"text\":\"system status\"}'
```

WebSocket clients connect to `ws://127.0.0.1:8765/ws` and send:

```json
{ "type": "command", "id": "1", "payload": { "text": "open notepad" } }
```

## Voice mode

```powershell
# Install voice dependencies (one-time, ~300MB incl. ONNX runtime)
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt

# Push-to-talk (recommended first run — no wake-word model download)
python -m core.voice.run --mode ptt

# Single-shot capture (great for quick testing)
python -m core.voice.run --mode once

# Wake-word ("Hey Jarvis"). First run downloads the openWakeWord model.
python -m core.voice.run --mode wake
```

The first run of any voice mode downloads the faster-whisper `tiny.en` model (~75MB)
into `%USERPROFILE%\.cache\huggingface`. Subsequent launches are fast.

## Adding a skill

1. Subclass `core.skills.base.Skill` in `core/skills/builtins/`.
2. Declare `name`, `description`, `patterns` (regexes), implement `async run`.
3. Register it in `core/skills/builtins/__init__.py`.

## Roadmap

| Phase | Scope |
|------:|-------|
| 1 | Core scaffold + skill registry |
| 2 | Voice loop: wake word → STT → TTS |
| 3 | Claude integration: streaming + tool use |
| 4 | 3-tier memory + prompt caching + Opus escalation |
| 5 | Real skills: files, web search, web fetch **← you are here** |
| 6 | Desktop UI (Electron + React, animated orb) |
| 7 | Security layer (confirmations, allowlists) |
| 8 | Proactive daemon + behavior learning |
| 9 | Mobile companion (React Native + Expo) |
| 10 | Advanced skills (multi-step workflows, doc analysis) |

## Layout

```
core/
  api/             FastAPI + WebSocket server (+ /memory endpoints)
  orchestrator/    Event bus + intent router (fast-path + LLM fallback)
  skills/          Skill ABC, registry, builtins/ (apps, system, files, web, memory)
  llm/             Claude client, tools bridge, sentence streamer, agentic loop
  memory/          3-tier memory: working / structured (SQLite) / semantic (Chroma)
  security/        Path-safety helpers (sandbox file ops to NOVA_FILE_ROOT)
  voice/           Mic, VAD, STT, TTS, wake, pipeline, CLI runner
  config.py        Pydantic settings
data/              (gitignored) nova.sqlite, chroma/
prompts/
  system.md        Nova persona + safety rules
scripts/
  smoke_test.py    Offline orchestrator test
```
