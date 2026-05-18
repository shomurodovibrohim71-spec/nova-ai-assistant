# Nova — Setup Guide

## Quick start (first time)

```powershell
# 1. Run setup (creates venv, installs all deps, builds UI)
.\setup.ps1

# 2. Fill in your keys
notepad .env

# 3. Launch
.\start.ps1              # core + desktop UI
.\start.ps1 -Voice       # core + UI + voice (push-to-talk)
.\start.ps1 -CoreOnly    # API server only (no UI)
```

---

## Keys you need

### Anthropic (for conversation)
1. Go to https://console.anthropic.com/
2. Create API key
3. Add to `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

### Telegram (for sending files/messages to yourself)
1. Open Telegram, find **@BotFather**
2. Send `/newbot` → give it a name → copy the **token**
3. Open your new bot and send `/start`
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Find `"chat":{"id": 123456789}` — that's your chat_id
6. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456789:ABCdef...
   TELEGRAM_CHAT_ID=123456789
   ```

---

## What Nova can do

| Command (voice or text) | Result |
|---|---|
| "hello" / "hey" | Greeting |
| "system status" | CPU, RAM, disk |
| "open chrome" / "open notepad" | Launches app |
| "list files in Downloads" | Lists directory |
| "find *.pdf in Desktop" | Glob search |
| "read report.pdf" | Extracts text from PDF/Excel/Word/TXT |
| "create folder called Projects" | mkdir |
| "search for Claude API docs" | DuckDuckGo search |
| "fetch https://example.com" | Fetches page + extracts text |
| "send message 'Hello' to telegram" | Telegram message |
| "send report.pdf to telegram" | Telegram file upload |
| "remember that I like dark mode" | Stores fact in memory |
| "what do you remember about me?" | Recalls memory |
| "think hard about X" | Switches to Opus 4.7 |

---

## File structure

```
AI assistant project/
├── core/                  Python backend
│   ├── api/               FastAPI + WebSocket server
│   ├── llm/               Claude integration
│   ├── memory/            3-tier memory (SQLite + ChromaDB)
│   ├── orchestrator/      Event bus + intent router
│   ├── security/          Path sandboxing
│   ├── skills/builtins/   All skill modules
│   └── voice/             Mic → STT → TTS pipeline
├── desktop/               Electron + React UI
├── data/                  (auto-created) sqlite + chroma
├── prompts/system.md      Nova personality
├── .env                   Your keys (never commit this)
├── start.ps1              Main launcher
├── setup.ps1              First-time installer
└── requirements*.txt      Python deps
```

---

## Troubleshooting

**"core not connected" in UI** → Make sure Python core is running: `python -m core.api.main`

**"ANTHROPIC_API_KEY not set"** → Fill in `.env`

**"TELEGRAM_BOT_TOKEN not set"** → Follow Telegram setup above

**Voice not working** → Run `python -m core.voice.run --mode ptt` — first run downloads Whisper model (~75MB)

**Memory not persisting** → Check `data/nova.sqlite` exists. Runs automatically on first boot.
