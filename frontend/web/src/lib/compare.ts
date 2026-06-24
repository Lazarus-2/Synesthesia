import { NOTES, FLAT_TO_SHARP } from "./music";
import { analyzeForm } from "./songForm";

export interface ComparableAnalysis {
  key: string; tempo: number; time_signature?: string;
  chords?: { chord: string }[];
  roman?: { summary_progression?: string[]; progression?: string[]; entries?: { numeral: string }[] } | null;
  sections?: { name: string }[];
}
export type KeyRelationship = "same" | "relative" | "parallel" | "different";
export interface ComparisonResult {
  keyRelationship: KeyRelationship;
  tempoDelta: number;        // b.tempo - a.tempo, rounded
  sameMeter: boolean;
  sharedChords: string[];    // distinct chord symbols present in both, sorted
  sharedNumerals: string[];  // distinct roman numerals present in both, sorted
  formA: string; formB: string;
}

function tonicPc(key: string): number | null {
  const m = (key || "").trim().match(/^([A-G][b#]?)/);
  if (!m) return null;
  let root = m[1];
  if (root.length === 2 && root[1] === "b" && FLAT_TO_SHARP[root]) root = FLAT_TO_SHARP[root];
  const i = NOTES.indexOf(root);
  return i === -1 ? null : i;
}
function mode(key: string): "major" | "minor" | null {
  const l = (key || "").toLowerCase();
  if (l.includes("minor") || /\bm\b/.test(l)) return "minor";
  if (l.includes("major")) return "major";
  return null;
}
function numerals(a: ComparableAnalysis): string[] {
  const r = a.roman;
  if (!r) return [];
  if (r.summary_progression?.length) return r.summary_progression;
  if (r.entries?.length) return r.entries.map((e) => e.numeral);
  return r.progression ?? [];
}

export function keyRelationship(keyA: string, keyB: string): KeyRelationship {
  const pa = tonicPc(keyA), pb = tonicPc(keyB), ma = mode(keyA), mb = mode(keyB);
  if (pa === null || pb === null) return keyA.trim() === keyB.trim() ? "same" : "different";
  if (pa === pb && ma === mb) return "same";
  if (pa === pb && ma !== mb) return "parallel";
  // relative: major tonic is 3 semitones above its relative minor tonic.
  if (ma && mb && ma !== mb) {
    const majPc = ma === "major" ? pa : pb;
    const minPc = ma === "minor" ? pa : pb;
    if ((minPc + 3) % 12 === majPc) return "relative";
  }
  return "different";
}

export function compareAnalyses(a: ComparableAnalysis, b: ComparableAnalysis): ComparisonResult {
  const setA = new Set((a.chords ?? []).map((c) => c.chord));
  const setB = new Set((b.chords ?? []).map((c) => c.chord));
  const sharedChords = [...setA].filter((c) => setB.has(c)).sort();
  const nA = new Set(numerals(a)); const nB = new Set(numerals(b));
  const sharedNumerals = [...nA].filter((n) => nB.has(n)).sort();
  return {
    keyRelationship: keyRelationship(a.key, b.key),
    tempoDelta: Math.round((b.tempo ?? 0) - (a.tempo ?? 0)),
    sameMeter: (a.time_signature ?? "4/4") === (b.time_signature ?? "4/4"),
    sharedChords, sharedNumerals,
    formA: analyzeForm(a.sections ?? []).label,
    formB: analyzeForm(b.sections ?? []).label,
  };
}
