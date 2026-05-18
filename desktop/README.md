# Nova Desktop

Electron + React + Tailwind UI for Nova. Connects to the Python core
over `ws://127.0.0.1:8765/ws` and `http://127.0.0.1:8765`.

## Development

```powershell
# 1. Start the Python core in a separate terminal:
#    (from project root)
#    python -m core.api.main

# 2. From this folder:
npm install
npm run dev
```

Vite serves the renderer on :5173; Electron launches as soon as it's up
and connects to the running core. The orb pulses by state, the right column
streams every event from the core (sentences, tool calls, memory writes),
the left column shows your structured memory facts live.

## Build

```powershell
npm run build
```

Outputs to `dist-renderer/` (HTML/JS) and `dist-electron/` (main + preload).

## Components

```
src/
  App.tsx              Top-level layout
  state.ts             Shared types
  useNovaWS.ts       WebSocket + REST client (single hook)
  components/
    Orb.tsx            Animated state orb (Framer Motion)
    Console.tsx        Live event log
    Input.tsx          Text input
    StatusBar.tsx      Title bar + status indicators
    MemoryPanel.tsx    Live structured-memory list
electron/
  main.ts              Electron main process (frameless transparent window)
  preload.ts           Context-isolated preload
```
