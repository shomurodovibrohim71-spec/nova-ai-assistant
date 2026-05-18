import { useState, type KeyboardEvent } from "react";

export function Input({ onSend, disabled }: { onSend: (t: string) => void; disabled?: boolean }) {
  const [value, setValue] = useState("");

  function send() {
    const t = value.trim();
    if (!t) return;
    onSend(t);
    setValue("");
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="glass rounded-xl px-4 py-3 flex items-center gap-3">
      <span className="text-cyan-300/70 font-mono text-xs">›</span>
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKey}
        rows={1}
        spellCheck={false}
        placeholder={disabled ? "core offline..." : "speak to Jarves... (Enter to send)"}
        disabled={disabled}
        className="flex-1 bg-transparent text-slate-100 placeholder-slate-500 outline-none resize-none font-mono text-sm select-text"
      />
      <button
        onClick={send}
        disabled={disabled}
        className="px-3 py-1 text-xs uppercase tracking-widest border border-cyan-400/30 rounded-md text-cyan-200 hover:bg-cyan-400/10 disabled:opacity-30"
      >
        send
      </button>
    </div>
  );
}
