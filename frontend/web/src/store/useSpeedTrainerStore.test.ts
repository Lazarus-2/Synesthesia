import { describe, it, expect, beforeEach } from "vitest";
import { useSpeedTrainerStore } from "./useSpeedTrainerStore";

beforeEach(() => {
  useSpeedTrainerStore.setState({
    enabled: false,
    startPct: 60,
    targetPct: 100,
    stepPct: 5,
    loopsPerStep: 2,
    currentPass: 0,
    currentPct: 60,
  });
});

describe("useSpeedTrainerStore", () => {
  it("toggles enabled and seeds currentPct to startPct on enable", () => {
    useSpeedTrainerStore.getState().toggle();
    const s = useSpeedTrainerStore.getState();
    expect(s.enabled).toBe(true);
    expect(s.currentPass).toBe(0);
    expect(s.currentPct).toBe(60);
  });

  it("registerLoopWrap advances pass and returns next rate when due", () => {
    useSpeedTrainerStore.setState({ enabled: true, stepPct: 10, loopsPerStep: 1 });
    const rate1 = useSpeedTrainerStore.getState().registerLoopWrap();
    expect(rate1).toBeCloseTo(0.7); // pass 1 with start 60, step 10
    expect(useSpeedTrainerStore.getState().currentPct).toBe(70);
  });

  it("registerLoopWrap returns null when disabled", () => {
    expect(useSpeedTrainerStore.getState().registerLoopWrap()).toBeNull();
  });

  it("setConfig validates: targetPct >= startPct, stepPct >= 1, loopsPerStep >= 1", () => {
    useSpeedTrainerStore.getState().setConfig({ startPct: 90, targetPct: 50, stepPct: 0, loopsPerStep: 0 });
    const s = useSpeedTrainerStore.getState();
    expect(s.targetPct).toBeGreaterThanOrEqual(s.startPct);
    expect(s.stepPct).toBeGreaterThanOrEqual(1);
    expect(s.loopsPerStep).toBeGreaterThanOrEqual(1);
  });
});
