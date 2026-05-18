import type { JarvesAPI } from "../useJarvesWS";

export function MemoryPanel({ facts }: { facts: JarvesAPI["facts"] }) {
  return (
    <div className="glass rounded-xl p-3 h-full overflow-y-auto console-scroll">
      <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-2">
        memory · {facts.length}
      </div>
      {facts.length === 0 && (
        <div className="text-slate-500 italic text-xs">empty — say "remember that ..."</div>
      )}
      <ul className="space-y-1.5 text-[12px]">
        {facts.map((f) => (
          <li key={f.id} className="text-slate-200 leading-snug">
            <span className="text-violet-300/80 font-mono mr-2">[{f.category}]</span>
            {f.content}
          </li>
        ))}
      </ul>
    </div>
  );
}
