"use client";

import React from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export const ChordTimeline: React.FC = () => {
  const { analysis } = useAnalysisStore();
  const { currentTime, wavesurfer } = usePlayerStore();

  if (!analysis?.chords || analysis.chords.length === 0) {
    return (
      <section className="glass-panel rounded-xl p-4">
        <div className="flex items-center justify-center h-24 text-on-surface-variant text-sm">
          No chord data available
        </div>
      </section>
    );
  }

  // Find the active chord index
  const activeIdx = analysis.chords.findIndex(
    (c) => currentTime >= c.start && currentTime < c.end
  );

  const handleChordClick = (startTime: number) => {
    if (wavesurfer) {
      wavesurfer.seekTo(startTime / wavesurfer.getDuration());
    }
  };

  return (
    <section className="glass-panel rounded-xl p-4">
      <div className="flex items-center gap-4 overflow-x-auto hide-scrollbar pb-2">
        {analysis.chords.map((chord, i) => {
          const isActive = i === activeIdx;
          const isPast = i < activeIdx;
          const isFuture = i > activeIdx;

          return (
            <div
              key={i}
              className={`flex-shrink-0 rounded-lg flex flex-col items-center justify-center cursor-pointer transition-all duration-200 ${
                isActive
                  ? "w-32 h-32 bg-surface-container-high border-2 border-primary-container inner-glow-focus transform scale-105 z-10"
                  : "w-24 h-24 bg-surface-container-high border border-white/5"
              } ${isPast ? "opacity-50 hover:opacity-100" : ""} ${
                isFuture ? "opacity-70 hover:opacity-100" : ""
              }`}
              onClick={() => handleChordClick(chord.start)}
            >
              <span
                className={`font-headline ${
                  isActive
                    ? "text-5xl font-semibold text-primary"
                    : "text-2xl font-medium text-on-surface"
                }`}
              >
                {chord.chord}
              </span>
              <span
                className={`mt-1 text-xs font-medium ${
                  isActive ? "text-primary-container" : "text-on-surface-variant"
                }`}
              >
                {formatTime(chord.start)}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
};
