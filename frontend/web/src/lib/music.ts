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

// Fretboard and Piano Voicings Database
export interface GuitarShape {
  frets: number[];
  fingers: number[];
}

export const GUITAR_VOICINGS: Record<string, GuitarShape> = {
  "C":   { frets: [-1, 3, 2, 0, 1, 0], fingers: [0, 3, 2, 0, 1, 0] },
  "G":   { frets: [3, 2, 0, 0, 0, 3],  fingers: [3, 2, 0, 0, 0, 4] },
  "D":   { frets: [-1, -1, 0, 2, 3, 2], fingers: [0, 0, 0, 1, 3, 2] },
  "Em":  { frets: [0, 2, 2, 0, 0, 0],  fingers: [0, 2, 3, 0, 0, 0] },
  "Am":  { frets: [-1, 0, 2, 2, 1, 0], fingers: [0, 0, 2, 3, 1, 0] },
  "F":   { frets: [1, 3, 3, 2, 1, 1],  fingers: [1, 3, 4, 2, 1, 1] },
  "Bm":  { frets: [-1, 2, 4, 4, 3, 2], fingers: [0, 1, 3, 4, 2, 1] },
  "B":   { frets: [-1, 2, 4, 4, 4, 2], fingers: [0, 1, 2, 3, 4, 1] },
  "Cm":  { frets: [-1, 3, 5, 5, 4, 3], fingers: [0, 1, 3, 4, 2, 1] },
  "Em7": { frets: [0, 2, 2, 0, 3, 3],  fingers: [0, 1, 2, 0, 3, 4] },
  "A7":  { frets: [-1, 0, 2, 0, 2, 0], fingers: [0, 0, 1, 0, 2, 0] },
  "Am7": { frets: [-1, 0, 2, 0, 1, 0], fingers: [0, 0, 2, 0, 1, 0] },
  "G/B": { frets: [-1, 2, 0, 0, 3, 3], fingers: [0, 1, 0, 0, 3, 4] },
  "E":   { frets: [0, 2, 2, 1, 0, 0],  fingers: [0, 2, 3, 1, 0, 0] },
  "A":   { frets: [-1, 0, 2, 2, 2, 0], fingers: [0, 0, 1, 2, 3, 0] },
  "Dm":  { frets: [-1, -1, 0, 2, 3, 1], fingers: [0, 0, 0, 2, 3, 1] }
};

export const UKULELE_VOICINGS: Record<string, number[]> = {
  "C":   [0, 0, 0, 3],
  "G":   [0, 2, 3, 2],
  "D":   [2, 2, 2, 0],
  "Em":  [0, 4, 3, 2],
  "Am":  [2, 0, 0, 0],
  "F":   [2, 0, 1, 0],
  "Bm":  [4, 2, 2, 2],
  "B":   [4, 3, 2, 2],
  "Cm":  [0, 3, 3, 3],
  "A":   [2, 1, 0, 0],
  "E":   [4, 4, 4, 2]
};

export const BASS_VOICINGS: Record<string, number[]> = {
  "C":   [-1, 3, 2, 0],
  "G":   [3, 2, 0, 0],
  "D":   [-1, -1, 0, 2],
  "Em":  [0, 2, 2, 0],
  "Am":  [-1, 0, 2, 2],
  "F":   [1, 3, 3, 2],
  "Bm":  [-1, 2, 4, 4],
  "B":   [-1, 2, 4, 4],
  "Cm":  [-1, 3, 5, 5],
  "A":   [-1, 0, 2, 2],
  "E":   [0, 2, 2, -1]
};

export const PIANO_VOICINGS: Record<string, string[]> = {
  "C":   ["C4", "E4", "G4"],
  "G":   ["G3", "B3", "D4"],
  "D":   ["D4", "F#4", "A4"],
  "Em":  ["E4", "G4", "B4"],
  "Am":  ["A3", "C4", "E4"],
  "F":   ["F4", "A4", "C5"],
  "Bm":  ["B3", "D4", "F#4"],
  "B":   ["B3", "D#4", "F#4"],
  "Cm":  ["C4", "Eb4", "G4"],
  "Em7": ["E4", "G4", "B4", "D5"],
  "A7":  ["A3", "C#4", "E4", "G4"],
  "Am7": ["A3", "C4", "E4", "G4"],
  "G/B": ["B3", "D4", "G4"],
  "E":   ["E4", "G#4", "B4"],
  "A":   ["A3", "C#4", "E4"]
};

// Standard MIDI frequencies/keys map for visual keyboard highlighting
export const WHITE_KEYS = ["C", "D", "E", "F", "G", "A", "B"];
export const BLACK_KEYS_MAP: Record<string, string> = {
  "C#": "C", "D#": "D", "F#": "F", "G#": "G", "A#": "A"
};
