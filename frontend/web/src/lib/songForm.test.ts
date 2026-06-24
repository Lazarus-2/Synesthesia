import { describe, it, expect } from "vitest";
import { analyzeForm } from "./songForm";

describe("analyzeForm", () => {
  it("compresses consecutive duplicate sections into a sequence", () => {
    const r = analyzeForm([{ name: "Intro" }, { name: "Verse" }, { name: "Verse" }, { name: "Chorus" }]);
    expect(r.sequence).toEqual(["Intro", "Verse", "Chorus"]);
  });
  it("labels verse-chorus form", () => {
    const r = analyzeForm([{ name: "Intro" }, { name: "Verse" }, { name: "Chorus" }, { name: "Verse" }, { name: "Chorus" }, { name: "Outro" }]);
    expect(r.label).toBe("Verse–Chorus");
  });
  it("labels verse-chorus with bridge", () => {
    const r = analyzeForm([{ name: "Verse" }, { name: "Chorus" }, { name: "Bridge" }, { name: "Chorus" }]);
    expect(r.label).toBe("Verse–Chorus (with bridge)");
  });
  it("labels AABA (verse/bridge, no chorus)", () => {
    const r = analyzeForm([{ name: "Verse" }, { name: "Verse" }, { name: "Bridge" }, { name: "Verse" }]);
    expect(r.label).toBe("AABA");
  });
  it("labels strophic for a single repeated section", () => {
    const r = analyzeForm([{ name: "Verse" }, { name: "Verse" }, { name: "Verse" }]);
    expect(r.label).toBe("Strophic");
  });
  it("handles empty", () => {
    expect(analyzeForm([]).label).toBe("Unknown");
    expect(analyzeForm([]).sequence).toEqual([]);
  });
});
