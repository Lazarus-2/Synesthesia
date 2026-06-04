"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

// LocalStorage-backed favorites. Pure client-side for v1 — there is no
// ``/api/v1/favorites`` endpoint yet and we deliberately avoid one so the
// feature ships without a backend round-trip.

interface FavoritesState {
  ids: string[];
  add: (jobId: string) => void;
  remove: (jobId: string) => void;
  has: (jobId: string) => boolean;
  all: () => string[];
}

export const useFavoritesStore = create<FavoritesState>()(
  persist(
    (set, get) => ({
      ids: [],
      add: (jobId) => {
        if (!jobId) return;
        const { ids } = get();
        if (ids.includes(jobId)) return;
        set({ ids: [...ids, jobId] });
      },
      remove: (jobId) =>
        set({ ids: get().ids.filter((id) => id !== jobId) }),
      has: (jobId) => get().ids.includes(jobId),
      all: () => get().ids,
    }),
    {
      name: "synesthesia.favorites",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ ids: s.ids }),
    },
  ),
);
