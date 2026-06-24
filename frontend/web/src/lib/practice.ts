// Pure, framework-free practice-tool logic. Everything here is deterministic
// and unit-tested in practice.test.ts — keep it free of React/DOM/Zustand.

export interface RampConfig {
  startPct: number; // e.g. 60
  targetPct: number; // e.g. 100
  stepPct: number; // e.g. 5
  loopsPerStep: number; // e.g. 2
}

/**
 * The playback rate (as a fraction, e.g. 0.75) for a given 0-indexed loop pass.
 * Defensive so the ramp ALWAYS terminates: jumps to target when step <= 0, and
 * returns target immediately when target <= start.
 */
export function nextRampRate(pass: number, c: RampConfig): number {
  const start = c.startPct;
  const target = c.targetPct;
  if (target <= start) return target / 100;
  if (c.stepPct <= 0) return target / 100;
  const step = c.stepPct;
  const perStep = Math.max(1, Math.floor(c.loopsPerStep));
  const steps = Math.floor(Math.max(0, pass) / perStep);
  const pct = Math.min(target, start + steps * step);
  return pct / 100;
}
