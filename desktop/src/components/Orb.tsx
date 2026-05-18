import { motion } from "framer-motion";
import type { OrbState } from "../state";

const palette: Record<OrbState, { core: string; halo: string; ring: string; speed: number }> = {
  offline: { core: "#3a4258", halo: "#1a2238", ring: "#2a3550", speed: 6 },
  idle: { core: "#7afcff", halo: "#5b8dff", ring: "#7afcff", speed: 4 },
  listening: { core: "#a6ffea", halo: "#5b8dff", ring: "#a6ffea", speed: 1.6 },
  thinking: { core: "#9d6bff", halo: "#5b8dff", ring: "#9d6bff", speed: 2.2 },
  speaking: { core: "#7afcff", halo: "#9d6bff", ring: "#7afcff", speed: 1.2 },
  error: { core: "#ff6b6b", halo: "#7a1f1f", ring: "#ff8080", speed: 5 },
};

export function Orb({ state }: { state: OrbState }) {
  const c = palette[state];
  return (
    <div className="relative grid place-items-center">
      <motion.div
        aria-hidden
        className="absolute rounded-full"
        style={{
          width: 280,
          height: 280,
          background: `radial-gradient(circle, ${c.halo}55 0%, transparent 65%)`,
          filter: "blur(20px)",
        }}
        animate={{ scale: [1, 1.08, 1], opacity: [0.7, 0.95, 0.7] }}
        transition={{ duration: c.speed, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute rounded-full border"
        style={{
          width: 200,
          height: 200,
          borderColor: `${c.ring}55`,
          boxShadow: `0 0 40px ${c.ring}55, inset 0 0 30px ${c.ring}33`,
        }}
        animate={{ rotate: 360 }}
        transition={{ duration: c.speed * 6, repeat: Infinity, ease: "linear" }}
      />
      <motion.div
        className="rounded-full"
        style={{
          width: 120,
          height: 120,
          background: `radial-gradient(circle at 30% 30%, ${c.core}, ${c.halo} 60%, ${c.halo}aa 100%)`,
          boxShadow: `0 0 50px ${c.core}88, inset 0 0 30px ${c.halo}80`,
        }}
        animate={{ scale: [1, 1.06, 1] }}
        transition={{ duration: c.speed * 0.6, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="absolute -bottom-10 text-xs uppercase tracking-[0.3em] text-slate-300/70">
        {state}
      </div>
    </div>
  );
}
