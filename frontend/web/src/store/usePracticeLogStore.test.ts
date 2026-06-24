import { describe, it, expect, beforeEach } from "vitest";
import { usePracticeLogStore } from "./usePracticeLogStore";

beforeEach(() => {
  localStorage.clear();
  usePracticeLogStore.setState({ perSong: {}, streak: { streakDays: 0, lastActiveDate: null } });
});

describe("usePracticeLogStore", () => {
  it("accumulates practiced seconds per song", () => {
    usePracticeLogStore.getState().addTime("job1", 30, "2026-06-24");
    usePracticeLogStore.getState().addTime("job1", 15, "2026-06-24");
    expect(usePracticeLogStore.getState().perSong["job1"].secondsPracticed).toBe(45);
  });
  it("updates the streak on practice", () => {
    usePracticeLogStore.getState().addTime("job1", 10, "2026-06-24");
    expect(usePracticeLogStore.getState().streak.streakDays).toBe(1);
  });
  it("persists under synesthesia.practiceLog", () => {
    usePracticeLogStore.getState().addTime("job1", 10, "2026-06-24");
    expect(localStorage.getItem("synesthesia.practiceLog")).toContain("job1");
  });
});
