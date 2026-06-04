import { create } from 'zustand';

/**
 * Practice-mode state (Plan 3 A3 + B1 + B6).
 *
 * Holds the looping region, playback rate, and metronome toggle. Kept
 * intentionally small — playback is still driven by the WaveSurfer
 * instance owned by usePlayerStore; this store only carries *intent*
 * (loop range, target rate). The BottomBar reads these values and forwards
 * them to wavesurfer.setPlaybackRate / .seekTo via effects.
 *
 * Pitch preservation note (Plan 2 corrections doc):
 * ``wavesurfer.setPlaybackRate`` shifts pitch with tempo. Real practice
 * mode wants a time-stretching library (soundtouchjs, web-audio-worklet
 * phase vocoder). For now we ship the basic rate change with a TODO so the
 * UX is functional, and users get explicit visual feedback about the
 * pitch artifact.
 */
export interface PracticeState {
  practiceMode: boolean;
  togglePracticeMode: () => void;

  // Loop region, in seconds. ``null`` means "no loop set yet."
  loopStart: number | null;
  loopEnd: number | null;
  setLoopStart: (t: number | null) => void;
  setLoopEnd: (t: number | null) => void;
  clearLoop: () => void;

  // Playback speed. When ``pitchLock`` is on, the rate change is routed
  // through the SoundTouch AudioWorklet so pitch stays at original;
  // otherwise WaveSurfer's native ``setPlaybackRate`` is used (which DOES
  // shift pitch).
  playbackRate: number;
  setPlaybackRate: (rate: number) => void;

  // When true, route playback-rate changes through the pitch-preserving
  // time-stretch worklet. Default off so existing UX is unchanged.
  pitchLock: boolean;
  togglePitchLock: () => void;
  setPitchLock: (on: boolean) => void;

  // Transpose offset in semitones. Range [-5, +5]. Stored centrally so
  // chord labels (ChordTimeline / TheoryPanel / PlayPanel) and the audio
  // pitch-shift node stay in sync.
  transpose: number;
  setTranspose: (semitones: number) => void;
  bumpTranspose: (delta: number) => void;

  // Metronome (Plan 3 B6).
  metronomeOn: boolean;
  toggleMetronome: () => void;
  tapTempoBPM: number | null;
  recordTap: () => void;
}

let tapTimestamps: number[] = [];

export const usePracticeStore = create<PracticeState>((set, get) => ({
  practiceMode: false,
  togglePracticeMode: () => set((s) => ({ practiceMode: !s.practiceMode })),

  loopStart: null,
  loopEnd: null,
  setLoopStart: (t) => set({ loopStart: t }),
  setLoopEnd: (t) => set({ loopEnd: t }),
  clearLoop: () => set({ loopStart: null, loopEnd: null }),

  playbackRate: 1.0,
  setPlaybackRate: (rate) => set({ playbackRate: rate }),

  pitchLock: false,
  togglePitchLock: () => set((s) => ({ pitchLock: !s.pitchLock })),
  setPitchLock: (on) => set({ pitchLock: on }),

  transpose: 0,
  setTranspose: (semitones) =>
    set({ transpose: Math.max(-5, Math.min(5, Math.trunc(semitones))) }),
  bumpTranspose: (delta) =>
    set((s) => ({
      transpose: Math.max(-5, Math.min(5, s.transpose + delta)),
    })),

  metronomeOn: false,
  toggleMetronome: () => set((s) => ({ metronomeOn: !s.metronomeOn })),
  tapTempoBPM: null,
  recordTap: () => {
    const now = performance.now();
    // Drop taps older than 3s (the user almost certainly started over).
    tapTimestamps = [...tapTimestamps, now].filter((t) => now - t <= 3000);
    if (tapTimestamps.length < 2) {
      set({ tapTempoBPM: null });
      return;
    }
    // Average inter-tap interval -> BPM.
    const intervals: number[] = [];
    for (let i = 1; i < tapTimestamps.length; i++) {
      intervals.push(tapTimestamps[i] - tapTimestamps[i - 1]);
    }
    const meanMs = intervals.reduce((a, b) => a + b, 0) / intervals.length;
    if (meanMs <= 0) return;
    const bpm = Math.round(60000 / meanMs);
    set({ tapTempoBPM: bpm });
    void get(); // suppress unused get() warning
  },
}));
