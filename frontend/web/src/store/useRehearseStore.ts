import { create } from "zustand";

// Rehearse-mode store — drives "play through a setlist back-to-back".
// Plain (non-persisted) zustand: rehearse is a transient session that begins
// with the user pressing "Rehearse" on a collection/setlist and ends when the
// queue is exhausted or the user hits Stop. Persisting it would awkwardly
// resurrect a half-finished run on reload, so we deliberately keep it in memory.
interface RehearseState {
  active: boolean;
  queue: string[]; // ordered job_ids
  index: number; // current position within the queue

  // Begin a rehearse session: active=true, queue=jobIds, index=0.
  // No-op on an empty list (nothing to rehearse).
  start: (jobIds: string[]) => void;

  // Advance to the next song. Increments index, then returns the new current
  // job_id. If we've moved past the end, calls stop() and returns null.
  next: () => string | null;

  // End the session: clear everything back to the inactive default.
  stop: () => void;

  // The job_id at the current index, or null when inactive / out of range.
  current: () => string | null;
}

export const useRehearseStore = create<RehearseState>((set, get) => ({
  active: false,
  queue: [],
  index: 0,

  start: (jobIds) => {
    if (jobIds.length === 0) return;
    set({ active: true, queue: jobIds, index: 0 });
  },

  next: () => {
    const { queue, index } = get();
    const nextIndex = index + 1;
    if (nextIndex >= queue.length) {
      get().stop();
      return null;
    }
    set({ index: nextIndex });
    return queue[nextIndex];
  },

  stop: () => set({ active: false, queue: [], index: 0 }),

  current: () => {
    const { active, queue, index } = get();
    if (!active || index < 0 || index >= queue.length) return null;
    return queue[index];
  },
}));
