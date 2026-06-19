import { create } from 'zustand';
import type { ChordEvent } from '../types';

/**
 * useReharmStore — UI state for the "What If?" Reharm Sandbox.
 *
 * Holds only intent (which chord chip is the user exploring?), not the
 * suggestion list itself — those are derived on the fly inside the modal
 * from the shared helpers in `lib/music` so we don't duplicate music-theory
 * truth.
 */
interface ReharmState {
  open: boolean;
  // Index of the chord in analysis.chords[] the user clicked. -1 = none.
  chordIndex: number;
  chord: ChordEvent | null;
  openFor: (index: number, chord: ChordEvent) => void;
  close: () => void;
}

export const useReharmStore = create<ReharmState>((set) => ({
  open: false,
  chordIndex: -1,
  chord: null,
  openFor: (chordIndex, chord) => set({ open: true, chordIndex, chord }),
  close: () => set({ open: false, chordIndex: -1, chord: null }),
}));
