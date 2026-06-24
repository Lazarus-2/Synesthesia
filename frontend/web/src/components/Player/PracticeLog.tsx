"use client";

import React from "react";
import { usePracticeLogStore } from "../../store/usePracticeLogStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";

/** Compact practiced-time + streak badge for the current song. */
export const PracticeLog: React.FC = () => {
  const jobId = useAnalysisStore((s) => s.jobId);
  const log = usePracticeLogStore((s) => (jobId ? s.perSong[jobId] : undefined));
  const streakDays = usePracticeLogStore((s) => s.streak.streakDays);

  if (!jobId || !log || log.secondsPracticed === 0) return null;
  const mins = Math.round(log.secondsPracticed / 60);

  return (
    <span className="text-xs text-on-surface-variant flex items-center gap-1" title="Your practice on this song">
      <span className="material-symbols-outlined text-[14px]">timer</span>
      Practiced {mins}m{streakDays > 1 ? ` · ${streakDays}-day streak` : ""}
    </span>
  );
};
