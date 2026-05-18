export type OrbState = "offline" | "idle" | "listening" | "thinking" | "speaking" | "error";

export type ConsoleEntry = {
  id: number;
  ts: number;
  kind: "user" | "assistant" | "tool" | "system" | "error";
  text: string;
};

let nextId = 1;
export const newId = () => nextId++;
