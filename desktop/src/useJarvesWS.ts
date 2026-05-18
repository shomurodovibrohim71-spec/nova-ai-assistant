import { useCallback, useEffect, useRef, useState } from "react";
import { newId, type ConsoleEntry, type OrbState } from "./state";

const WS_URL = "ws://127.0.0.1:8765/ws";
const HTTP_BASE = "http://127.0.0.1:8765";

export type Skill = { name: string; description: string };

export type JarvesAPI = {
  status: OrbState;
  entries: ConsoleEntry[];
  skills: Skill[];
  facts: { id: number; category: string; content: string; ts: string }[];
  send: (text: string) => void;
  refreshMemory: () => Promise<void>;
};

export function useJarvesWS(): JarvesAPI {
  const [status, setStatus] = useState<OrbState>("offline");
  const [entries, setEntries] = useState<ConsoleEntry[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [facts, setFacts] = useState<JarvesAPI["facts"]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);

  const append = useCallback((kind: ConsoleEntry["kind"], text: string) => {
    setEntries((prev) => [...prev.slice(-199), { id: newId(), ts: Date.now(), kind, text }]);
  }, []);

  const refreshMemory = useCallback(async () => {
    try {
      const r = await fetch(`${HTTP_BASE}/memory/facts`);
      if (r.ok) setFacts(await r.json());
    } catch {
      /* core offline */
    }
  }, []);

  const refreshSkills = useCallback(async () => {
    try {
      const r = await fetch(`${HTTP_BASE}/skills`);
      if (r.ok) setSkills(await r.json());
    } catch {
      /* core offline */
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return;
    setStatus("offline");
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("idle");
      append("system", "connected to jarves core");
      refreshSkills();
      refreshMemory();
    };

    ws.onmessage = (ev) => {
      let msg: any;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "event" && msg.payload) {
        const ev = msg.payload;
        if (ev.type === "text") {
          /* token-level — we draw whole sentences instead */
        } else if (ev.type === "sentence") {
          append("assistant", ev.text);
          setStatus("speaking");
        } else if (ev.type === "tool_use") {
          append(
            "tool",
            `${ev.name}(${JSON.stringify(ev.input).slice(0, 80)})`,
          );
        } else if (ev.type === "tool_result") {
          append("tool", `↳ ${ev.ok ? "ok" : "fail"}: ${ev.data?.reply ?? ""}`);
        } else if (ev.type === "memory_recalled") {
          append("system", `recalled ${ev.items?.length ?? 0} memory item(s)`);
        } else if (ev.type === "memory_written") {
          append("system", "memory updated");
          refreshMemory();
        } else if (ev.type === "final") {
          if (ev.text) append("assistant", ev.text);
          setStatus("idle");
        } else if (ev.type === "error") {
          append("error", ev.message);
          setStatus("error");
        }
      } else if (msg.type === "reply" && msg.payload) {
        if (msg.payload.reply) append("assistant", msg.payload.reply);
        setStatus("idle");
      } else if (msg.type === "error") {
        append("error", msg.payload?.error ?? "unknown error");
        setStatus("error");
      }
    };

    ws.onerror = () => {
      append("error", "websocket error");
      setStatus("error");
    };

    ws.onclose = () => {
      setStatus("offline");
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      reconnectTimer.current = window.setTimeout(connect, 1500);
    };
  }, [append, refreshMemory, refreshSkills]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback(
    (text: string) => {
      if (!text.trim()) return;
      const ws = wsRef.current;
      if (!ws || ws.readyState !== 1) {
        append("error", "core not connected");
        return;
      }
      append("user", text);
      setStatus("thinking");
      ws.send(
        JSON.stringify({
          type: "command",
          id: String(newId()),
          payload: { text },
        }),
      );
    },
    [append],
  );

  return { status, entries, skills, facts, send, refreshMemory };
}
