export interface FormResult { sequence: string[]; label: string; }

/** Deterministic song-form labelling from already-detected section names
 *  (Intro/Verse/Chorus/Bridge/Outro). Pure — no network, no LLM. */
export function analyzeForm(sections: { name: string }[]): FormResult {
  if (!sections || sections.length === 0) return { sequence: [], label: "Unknown" };
  // Compress consecutive duplicates.
  const sequence: string[] = [];
  for (const s of sections) {
    const name = s.name;
    if (sequence.length === 0 || sequence[sequence.length - 1] !== name) sequence.push(name);
  }
  // Core = drop a leading Intro and trailing Outro for shape analysis.
  const core = sequence.filter((n) => {
    const l = n.toLowerCase();
    return l !== "intro" && l !== "outro";
  });
  const has = (kw: string) => core.some((n) => n.toLowerCase().includes(kw));
  const distinct = new Set(core.map((n) => n.toLowerCase()));
  let label: string;
  if (core.length === 0) label = "Unknown";
  else if (distinct.size === 1) label = "Strophic";
  else if (has("chorus") && has("bridge")) label = "Verse–Chorus (with bridge)";
  else if (has("chorus")) label = "Verse–Chorus";
  else if (has("bridge") && has("verse")) label = "AABA";
  else label = "Through-composed";
  return { sequence, label };
}
