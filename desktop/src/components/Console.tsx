import { useEffect, useRef } from "react";
import type { ConsoleEntry } from "../state";

const colors: Record<ConsoleEntry["kind"], string> = {
  user: "text-cyan-200",
  assistant: "text-violet-200",
  tool: "text-amber-200/80",
  system: "text-slate-400",
  error: "text-red-300",
};

const prefix: Record<ConsoleEntry["kind"], string> = {
  user: "you  ›",
  assistant: "jrvs ›",
  tool: "tool ›",
  system: "sys  ›",
  error: "err  ›",
};

export function Console({ entries }: { entries: ConsoleEntry[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [entries]);

  return (
    <div
      ref={ref}
      className="console-scroll glass rounded-xl px-4 py-3 h-full overflow-y-auto font-mono text-[12.5px] leading-relaxed"
    >
      {entries.length === 0 && (
        <div className="text-slate-500 italic">awaiting input...</div>
      )}
      {entries.map((e) => (
        <div key={e.id} className={`flex gap-3 ${colors[e.kind]}`}>
          <span className="text-slate-500 select-text">{prefix[e.kind]}</span>
          <span className="whitespace-pre-wrap break-words select-text">{e.text}</span>
        </div>
      ))}
    </div>
  );
}
