import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { addLoop, removeLoop, renameLoop, loopsFor, type LoopMap, type SavedLoop } from "../lib/practice";

// LocalStorage-backed saved loops, keyed by jobId. Mirrors useFavoritesStore.
// Server sync is deferred to the Collections sub-project.

let idCounter = 0;
function freshId(): string {
  idCounter += 1;
  // crypto.randomUUID when available; fall back to a counter (e.g. SSR/jsdom).
  const g = globalThis as unknown as { crypto?: { randomUUID?: () => string } };
  return g.crypto?.randomUUID?.() ?? `loop_${Date.now()}_${idCounter}`;
}

interface SavedLoopsState {
  loops: LoopMap;
  save: (jobId: string, name: string, start: number, end: number) => void;
  remove: (jobId: string, id: string) => void;
  rename: (jobId: string, id: string, name: string) => void;
  list: (jobId: string) => SavedLoop[];
}

export const useSavedLoopsStore = create<SavedLoopsState>()(
  persist(
    (set, get) => ({
      loops: {},
      save: (jobId, name, start, end) => {
        if (!jobId || end <= start) return;
        set({ loops: addLoop(get().loops, jobId, { id: freshId(), name: name || "Loop", start, end }) });
      },
      remove: (jobId, id) => set({ loops: removeLoop(get().loops, jobId, id) }),
      rename: (jobId, id, name) => set({ loops: renameLoop(get().loops, jobId, id, name) }),
      list: (jobId) => loopsFor(get().loops, jobId),
    }),
    {
      name: "synesthesia.savedLoops",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ loops: s.loops }),
    },
  ),
);
