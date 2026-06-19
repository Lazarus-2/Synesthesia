export const NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
export const FLAT_TO_SHARP: Record<string, string> = {
  "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"
};

function shiftRoot(root: string, semitones: number): string | null {
  let r = root;
  if (r.endsWith("b") && FLAT_TO_SHARP[r]) r = FLAT_TO_SHARP[r];
  const idx = NOTES.indexOf(r.toUpperCase());
  if (idx === -1) return null;
  const newIdx = (idx + semitones + 12 * 12) % 12;
  return NOTES[newIdx];
}

export function transposeChord(chord: string, semitones: number): string {
  if (!chord || semitones === 0) return chord;
  if (chord === "N.C." || chord === "N") return chord;

  // Handle slash chords (e.g. "G/B") by transposing both root and bass.
  const slashIdx = chord.indexOf("/");
  if (slashIdx !== -1) {
    const left = transposeChord(chord.slice(0, slashIdx), semitones);
    const right = transposeChord(chord.slice(slashIdx + 1), semitones);
    return `${left}/${right}`;
  }

  const match = chord.match(/^([A-G][b#]?)(.*)$/);
  if (!match) return chord;

  const newRoot = shiftRoot(match[1], semitones);
  if (newRoot === null) return chord;

  return newRoot + match[2];
}

// Scriabin Color Mapping
export const SCRIABIN_COLORS: Record<string, string> = {
  "C": "#FF0000", "G": "#FF7F00", "D": "#FFFF00", "A": "#00FF00",
  "E": "#00BFFF", "B": "#0000FF", "F#": "#4B0082", "C#": "#8B00FF",
  "G#": "#D8BFD8", "D#": "#FFC0CB", "A#": "#708090", "F": "#8B0000"
};

export function getChordColor(chord: string): string {
  if (!chord || chord === "N.C.") return "#1A1A1A";
  const match = chord.match(/^([A-G][b#]?)/);
  if (!match) return "#8B5CF6";
  let root = match[1];
  if (root.endsWith("b") && FLAT_TO_SHARP[root]) root = FLAT_TO_SHARP[root];
  return SCRIABIN_COLORS[root] || "#8B5CF6";
}

// NOTE: chord-voicing tables (guitar/ukulele/bass/piano) + keyboard maps used
// to live here but were never imported — diagrams come from the backend
// (tools/voicings.py) and PianoDiagram computes its own. Removed as dead code.
