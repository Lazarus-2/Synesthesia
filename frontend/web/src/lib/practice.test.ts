import { describe, it, expect } from "vitest";
import { nextRampRate, type RampConfig } from "./practice";
import { addLoop, removeLoop, renameLoop, loopsFor, type SavedLoop, type LoopMap } from "./practice";

const base: RampConfig = { startPct: 60, targetPct: 100, stepPct: 10, loopsPerStep: 1 };

describe("nextRampRate", () => {
  it("returns the start rate on pass 0", () => {
    expect(nextRampRate(0, base)).toBeCloseTo(0.6);
  });

  it("advances one step per pass when loopsPerStep is 1", () => {
    expect(nextRampRate(1, base)).toBeCloseTo(0.7);
    expect(nextRampRate(2, base)).toBeCloseTo(0.8);
  });

  it("clamps at target and never exceeds it", () => {
    expect(nextRampRate(99, base)).toBeCloseTo(1.0);
  });

  it("holds the rate for loopsPerStep passes", () => {
    const c = { ...base, loopsPerStep: 2 };
    expect(nextRampRate(0, c)).toBeCloseTo(0.6);
    expect(nextRampRate(1, c)).toBeCloseTo(0.6);
    expect(nextRampRate(2, c)).toBeCloseTo(0.7);
    expect(nextRampRate(3, c)).toBeCloseTo(0.7);
  });

  it("jumps to target if step is non-positive (always terminates)", () => {
    expect(nextRampRate(0, { ...base, stepPct: 0 })).toBeCloseTo(1.0);
  });

  it("returns target if target <= start", () => {
    expect(nextRampRate(0, { startPct: 100, targetPct: 80, stepPct: 5, loopsPerStep: 1 })).toBeCloseTo(0.8);
  });
});

describe("saved-loop CRUD", () => {
  const loopA: SavedLoop = { id: "1", name: "Solo", start: 10, end: 20 };
  const loopB: SavedLoop = { id: "2", name: "Chorus", start: 30, end: 45 };

  it("adds loops per jobId without cross-contamination", () => {
    let m: LoopMap = {};
    m = addLoop(m, "jobX", loopA);
    m = addLoop(m, "jobY", loopB);
    expect(loopsFor(m, "jobX")).toEqual([loopA]);
    expect(loopsFor(m, "jobY")).toEqual([loopB]);
  });

  it("removes by id", () => {
    let m: LoopMap = addLoop(addLoop({}, "j", loopA), "j", loopB);
    m = removeLoop(m, "j", "1");
    expect(loopsFor(m, "j")).toEqual([loopB]);
  });

  it("renames by id", () => {
    let m: LoopMap = addLoop({}, "j", loopA);
    m = renameLoop(m, "j", "1", "Intro");
    expect(loopsFor(m, "j")[0].name).toBe("Intro");
  });

  it("loopsFor returns [] for unknown jobId", () => {
    expect(loopsFor({}, "nope")).toEqual([]);
  });
});
