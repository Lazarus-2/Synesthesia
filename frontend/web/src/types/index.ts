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

export interface RomanAnalysis {
  key: string;
  progression: string[];
  function: string[];
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
  theory_explanation?: string;
  vibe_palette?: string[];
  instrument_guides?: Record<string, InstrumentGuide>;
  audioUrl?: string;
}

export interface ChordDiagram {
  chord: string;
  instrument: string;
  frets?: number[];
  fingers?: number[];
  right_hand?: string[];
  left_hand?: string[];
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
}
