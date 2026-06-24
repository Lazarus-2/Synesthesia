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

export interface SavedLoop {
  id: string;
  name: string;
  start: number;
  end: number;
}

/** jobId -> saved loops. Immutable helpers (return a new map). */
export type LoopMap = Record<string, SavedLoop[]>;

export function loopsFor(map: LoopMap, jobId: string): SavedLoop[] {
  return map[jobId] ?? [];
}

export function addLoop(map: LoopMap, jobId: string, loop: SavedLoop): LoopMap {
  return { ...map, [jobId]: [...loopsFor(map, jobId), loop] };
}

export function removeLoop(map: LoopMap, jobId: string, id: string): LoopMap {
  return { ...map, [jobId]: loopsFor(map, jobId).filter((l) => l.id !== id) };
}

export function renameLoop(map: LoopMap, jobId: string, id: string, name: string): LoopMap {
  return {
    ...map,
    [jobId]: loopsFor(map, jobId).map((l) => (l.id === id ? { ...l, name } : l)),
  };
}
