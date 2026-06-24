import { describe, it, expect } from "vitest";
import { compareAnalyses, keyRelationship, type ComparableAnalysis } from "./compare";

function mk(over: Partial<ComparableAnalysis>): ComparableAnalysis {
  return { key: "C major", tempo: 120, ...over };
}

describe("keyRelationship", () => {
  it("same key + mode", () => {
    expect(keyRelationship("C major", "C major")).toBe("same");
  });
  it("parallel (same tonic, different mode)", () => {
    expect(keyRelationship("C major", "C minor")).toBe("parallel");
  });
  it("relative (C major / A minor)", () => {
    expect(keyRelationship("C major", "A minor")).toBe("relative");
    expect(keyRelationship("A minor", "C major")).toBe("relative");
  });
  it("different keys", () => {
    expect(keyRelationship("C major", "G major")).toBe("different");
  });
  it("unparseable falls back to string compare", () => {
    expect(keyRelationship("???", "???")).toBe("same");
    expect(keyRelationship("???", "!!!")).toBe("different");
  });
});

describe("compareAnalyses", () => {
  it("computes tempoDelta (b - a, rounded)", () => {
    const r = compareAnalyses(mk({ tempo: 120 }), mk({ tempo: 134.4 }));
    expect(r.tempoDelta).toBe(14);
  });

  it("detects shared chords as a sorted intersection", () => {
    const a = mk({ chords: [{ chord: "C" }, { chord: "G" }, { chord: "Am" }] });
    const b = mk({ chords: [{ chord: "G" }, { chord: "C" }, { chord: "F" }] });
    expect(compareAnalyses(a, b).sharedChords).toEqual(["C", "G"]);
  });

  it("detects shared roman numerals as a sorted intersection", () => {
    const a = mk({ roman: { summary_progression: ["I", "V", "vi"] } });
    const b = mk({ roman: { summary_progression: ["vi", "I", "IV"] } });
    expect(compareAnalyses(a, b).sharedNumerals).toEqual(["I", "vi"]);
  });

  it("reads numerals from entries when summary_progression absent", () => {
    const a = mk({ roman: { entries: [{ numeral: "ii" }, { numeral: "V" }] } });
    const b = mk({ roman: { entries: [{ numeral: "V" }, { numeral: "I" }] } });
    expect(compareAnalyses(a, b).sharedNumerals).toEqual(["V"]);
  });

  it("compares meter (defaults to 4/4)", () => {
    expect(compareAnalyses(mk({}), mk({})).sameMeter).toBe(true);
    expect(
      compareAnalyses(mk({ time_signature: "3/4" }), mk({ time_signature: "4/4" })).sameMeter,
    ).toBe(false);
  });

  it("labels both forms via analyzeForm", () => {
    const a = mk({ sections: [{ name: "Verse" }, { name: "Verse" }, { name: "Verse" }] });
    const b = mk({ sections: [{ name: "Verse" }, { name: "Chorus" }, { name: "Verse" }, { name: "Chorus" }] });
    const r = compareAnalyses(a, b);
    expect(r.formA).toBe("Strophic");
    expect(r.formB).toBe("Verse–Chorus");
  });

  it("carries the keyRelationship", () => {
    expect(compareAnalyses(mk({ key: "C major" }), mk({ key: "A minor" })).keyRelationship).toBe(
      "relative",
    );
  });

  it("handles missing chords / roman gracefully", () => {
    const r = compareAnalyses(mk({}), mk({}));
    expect(r.sharedChords).toEqual([]);
    expect(r.sharedNumerals).toEqual([]);
    expect(r.formA).toBe("Unknown");
  });
});
