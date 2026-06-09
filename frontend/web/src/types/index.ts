export interface ChordEvent {
  start: number;
  end: number;
  chord: string;
  confidence: number;
  color: string;
}

export interface SongSection {
  name: string;
  start: number;
  end: number;
}

export interface RomanEntry {
  chord: string;
  numeral: string;
  function: "tonic" | "dominant" | "subdominant" | "submediant" | "borrowed" | "secondary" | string;
  inversion?: number;       // 0=root, 1=1st, 2=2nd (int from backend)
  is_secondary?: boolean;   // V/V, V/IV etc.
  is_borrowed?: boolean;    // modal mixture
  cadence?: "PAC" | "IAC" | "half" | "deceptive" | "plagal" | null;
  start: number;
  end: number;
}

export interface RomanCadence {
  type: "PAC" | "IAC" | "half" | "deceptive" | "plagal";
  index: number;            // chord index in progression (from backend)
}

export interface RomanModulation {
  to_key: string;
  at_index: number;         // chord index where modulation begins (from backend)
}

export interface RomanAnalysis {
  key: string;
  progression: string[];    // kept for legacy fallback rendering
  function: string[];       // kept for legacy fallback rendering
  summary_progression?: string[];
  entries?: RomanEntry[];   // G1 enriched, time-aligned per-chord data
  cadences?: RomanCadence[];
  modulations?: RomanModulation[];
}

export interface TheoryExplanation {
  key_summary: string;
  function_explanation: string;
  pattern_name: string | null;
  notable_techniques: string[];
  similar_song: string | null;
  text?: string;            // computed field — full prose rendering
}

export interface SimilarSong {
  title: string;
  artist: string;
  url?: string;
  image?: string;
  source: string;           // e.g. "lastfm", "deezer", "catalog"
  match: number;            // 0-1 similarity score
}

export interface SongAnalysis {
  title: string;
  artist: string;
  duration: number;
  key: string;
  tempo: number;
  time_signature?: string;
  chords: ChordEvent[];
  beats?: number[];
  sections: SongSection[];
  roman?: RomanAnalysis;
  theory?: TheoryExplanation | null;   // G4 structured object; preferred when present
  // theory_explanation kept for back-compat (equals theory.text when theory is set)
  theory_explanation?: string | null;
  similar_songs?: SimilarSong[];       // G4 surface — absent when backend hasn't computed it
  vibe_palette?: string[];
  instrument_guides?: Record<string, InstrumentGuide>;
  audioUrl?: string;
  // Metadata enrichment (C4). All optional — backend populates lazily.
  album?: string;
  album_art_url?: string;
  mbid?: string;
  spotify_id?: string;
  isrc?: string;
  audio_source?: string;
}

export interface ChordDiagram {
  chord: string;
  instrument: string;
  frets?: number[];
  fingers?: number[];
  right_hand?: string[];
  left_hand?: string[];
  no_voicing?: boolean;     // True = no playable shape exists; render "no diagram" placeholder
}

export interface InstrumentGuide {
  instrument: string;
  difficulty: string;
  chord_diagrams?: ChordDiagram[];
  strum_pattern?: string;
  tips?: string[];
  capo?: number;
}

// Chat types
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

// Analysis job response (mirrors backend AnalyzeResponse)
export interface AnalyzeResponse {
  job_id: string;
  status: string;
  progress?: number;
  message?: string;
  analysis?: SongAnalysis;
  instrument_guide?: InstrumentGuide;
  error?: string;
  audio_url?: string;
  youtube_url?: string;
}
