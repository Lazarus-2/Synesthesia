import { create } from "zustand";
import { nextRampRate, type RampConfig } from "../lib/practice";

// Kept separate from usePracticeStore: the per-pass churn (currentPass/currentPct)
// would otherwise re-render every practice-control consumer on each loop wrap.
interface SpeedTrainerState extends RampConfig {
  enabled: boolean;
  currentPass: number;
  currentPct: number;
  toggle: () => void;
  setConfig: (c: Partial<RampConfig>) => void;
  /** Call on each loop wrap. Advances the pass counter and returns the new
   *  playback rate (fraction) if it changed this wrap, else the current rate.
   *  Returns null when disabled (caller should no-op). */
  registerLoopWrap: () => number | null;
  reset: () => void;
}

export const useSpeedTrainerStore = create<SpeedTrainerState>((set, get) => ({
  enabled: false,
  startPct: 60,
  targetPct: 100,
  stepPct: 5,
  loopsPerStep: 2,
  currentPass: 0,
  currentPct: 60,

  toggle: () =>
    set((s) => ({
      enabled: !s.enabled,
      currentPass: 0,
      currentPct: s.startPct,
    })),

  setConfig: (c) =>
    set((s) => {
      const startPct = c.startPct ?? s.startPct;
      const targetPct = Math.max(startPct, c.targetPct ?? s.targetPct);
      const stepPct = Math.max(1, c.stepPct ?? s.stepPct);
      const loopsPerStep = Math.max(1, Math.floor(c.loopsPerStep ?? s.loopsPerStep));
      return { startPct, targetPct, stepPct, loopsPerStep, currentPct: startPct, currentPass: 0 };
    }),

  registerLoopWrap: () => {
    const s = get();
    if (!s.enabled) return null;
    const pass = s.currentPass + 1;
    const rate = nextRampRate(pass, s);
    set({ currentPass: pass, currentPct: Math.round(rate * 100) });
    return rate;
  },

  reset: () => set((s) => ({ currentPass: 0, currentPct: s.startPct })),
}));
