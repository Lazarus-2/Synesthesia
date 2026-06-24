import { create } from "zustand";
import type { StemId } from "../lib/practice";

// Play-Along: when engaged, exactly one stem is muted (the user's instrument)
// and the stem mixer is the audible source. Not persisted — it's a transient
// session mode.
interface PlayAlongState {
  engaged: boolean;
  mutedStem: StemId | null;
  engage: (stem: StemId) => void;
  disengage: () => void;
}

export const usePlayAlongStore = create<PlayAlongState>((set) => ({
  engaged: false,
  mutedStem: null,
  engage: (stem) => set({ engaged: true, mutedStem: stem }),
  disengage: () => set({ engaged: false, mutedStem: null }),
}));
