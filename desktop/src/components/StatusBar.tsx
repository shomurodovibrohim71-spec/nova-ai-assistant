import type { OrbState } from "../state";

const labels: Record<OrbState, string> = {
  offline: "core offline",
  idle: "online",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
  error: "error",
};

const dotColors: Record<OrbState, string> = {
  offline: "bg-slate-500",
  idle: "bg-emerald-400",
  listening: "bg-cyan-300",
  thinking: "bg-violet-300",
  speaking: "bg-cyan-200",
  error: "bg-rose-400",
};

export function StatusBar({
  state,
  skillCount,
  factCount,
}: {
  state: OrbState;
  skillCount: number;
  factCount: number;
}) {
  return (
    <div className="titlebar flex items-center justify-between px-4 text-[11px] uppercase tracking-[0.25em] text-slate-400/80">
      <div className="flex items-center gap-3">
        <span className="font-mono text-cyan-300 glow-text">JARVES</span>
        <span className="text-slate-600">v0.1</span>
      </div>
      <div className="flex items-center gap-5">
        <span>{skillCount} skills</span>
        <span>{factCount} memories</span>
        <span className="flex items-center gap-2">
          <span
            className={`inline-block w-2 h-2 rounded-full ${dotColors[state]} ${
              state !== "offline" ? "animate-pulse" : ""
            }`}
          />
          {labels[state]}
        </span>
        <button
          onClick={() => window.close()}
          className="text-slate-500 hover:text-rose-300 px-2"
          title="close"
        >
          ×
        </button>
      </div>
    </div>
  );
}
