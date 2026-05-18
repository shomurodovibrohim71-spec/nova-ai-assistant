import { Console } from "./components/Console";
import { Input } from "./components/Input";
import { MemoryPanel } from "./components/MemoryPanel";
import { Orb } from "./components/Orb";
import { StatusBar } from "./components/StatusBar";
import { useJarvesWS } from "./useJarvesWS";

export default function App() {
  const { status, entries, skills, facts, send } = useJarvesWS();

  return (
    <div className="h-full flex flex-col">
      <StatusBar state={status} skillCount={skills.length} factCount={facts.length} />
      <main className="flex-1 grid grid-cols-[280px_1fr_280px] gap-4 px-4 pb-4 min-h-0">
        <aside className="flex flex-col">
          <MemoryPanel facts={facts} />
        </aside>
        <section className="flex flex-col items-center justify-between gap-4 min-h-0">
          <div className="flex-1 grid place-items-center w-full">
            <Orb state={status} />
          </div>
          <div className="w-full max-w-2xl">
            <Input onSend={send} disabled={status === "offline"} />
          </div>
        </section>
        <aside className="flex flex-col">
          <Console entries={entries} />
        </aside>
      </main>
    </div>
  );
}
