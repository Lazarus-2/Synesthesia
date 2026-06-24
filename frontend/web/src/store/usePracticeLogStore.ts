"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { updateStreak, type StreakState } from "../lib/practice";

interface SongLog {
  secondsPracticed: number;
  loopsCompleted: number;
  lastPracticedAt: string; // ISO date
}

interface PracticeLogState {
  perSong: Record<string, SongLog>;
  streak: StreakState;
  /** Add practiced seconds for a song. `today` injected for testability. */
  addTime: (jobId: string, seconds: number, today: string) => void;
  addLoop: (jobId: string, today: string) => void;
}

function emptyLog(): SongLog {
  return { secondsPracticed: 0, loopsCompleted: 0, lastPracticedAt: "" };
}

export const usePracticeLogStore = create<PracticeLogState>()(
  persist(
    (set, get) => ({
      perSong: {},
      streak: { streakDays: 0, lastActiveDate: null },
      addTime: (jobId, seconds, today) => {
        if (!jobId || seconds <= 0) return;
        const cur = get().perSong[jobId] ?? emptyLog();
        set({
          perSong: {
            ...get().perSong,
            [jobId]: { ...cur, secondsPracticed: cur.secondsPracticed + seconds, lastPracticedAt: today },
          },
          streak: updateStreak(get().streak, today),
        });
      },
      addLoop: (jobId, today) => {
        if (!jobId) return;
        const cur = get().perSong[jobId] ?? emptyLog();
        set({
          perSong: {
            ...get().perSong,
            [jobId]: { ...cur, loopsCompleted: cur.loopsCompleted + 1, lastPracticedAt: today },
          },
          streak: updateStreak(get().streak, today),
        });
      },
    }),
    {
      name: "synesthesia.practiceLog",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ perSong: s.perSong, streak: s.streak }),
    },
  ),
);
