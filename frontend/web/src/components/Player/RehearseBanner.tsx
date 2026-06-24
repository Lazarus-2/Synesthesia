"use client";

import React from "react";
import { useRehearseStore } from "../../store/useRehearseStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";

// A slim strip shown while a rehearse session is active: "Rehearsing 2/5",
// a manual "Next song" control (useful if auto-advance-on-finish is ever
// missed), and a Stop button. Mounted in HomeClient just under the player
// header so it sits unobtrusively above the waveform.
export const RehearseBanner: React.FC = () => {
  const active = useRehearseStore((s) => s.active);
  const index = useRehearseStore((s) => s.index);
  const queue = useRehearseStore((s) => s.queue);

  if (!active) return null;

  const stop = () => {
    useRehearseStore.getState().stop();
    usePlayerStore.getState().setIsPlaying(false);
  };

  // Same advance logic as the WaveformPlayer "finish" handler, surfaced as a
  // manual control. Stops cleanly if the next song fails to load.
  const skipToNext = () => {
    const nextId = useRehearseStore.getState().next();
    if (!nextId) {
      // next() already deactivated the session (end of queue).
      usePlayerStore.getState().setIsPlaying(false);
      return;
    }
    void useAnalysisStore
      .getState()
      .loadExisting(nextId)
      .then(() => {
        if (useAnalysisStore.getState().jobStatus !== "done") {
          useRehearseStore.getState().stop();
          usePlayerStore.getState().setIsPlaying(false);
        }
      });
  };

  const atLast = index >= queue.length - 1;

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2 mb-3 rounded-lg glass-panel border border-primary/30 bg-primary/5">
      <div className="flex items-center gap-2 min-w-0">
        <span
          className="material-symbols-outlined text-primary text-lg shrink-0"
          style={{ fontVariationSettings: "'FILL' 1" }}
        >
          queue_music
        </span>
        <span className="text-sm font-semibold text-on-surface truncate">
          Rehearsing {index + 1}/{queue.length}
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          onClick={skipToNext}
          disabled={atLast}
          className="px-3 py-1.5 rounded-full text-xs font-semibold text-primary hover:bg-primary/10 disabled:opacity-30 disabled:hover:bg-transparent flex items-center gap-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-label="Next song"
        >
          Next song
          <span className="material-symbols-outlined text-base" style={{ fontVariationSettings: "'FILL' 1" }}>
            skip_next
          </span>
        </button>
        <button
          type="button"
          onClick={stop}
          className="px-3 py-1.5 rounded-full glass-panel text-xs font-semibold text-on-surface-variant hover:text-error hover:border-error/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-error"
        >
          Stop
        </button>
      </div>
    </div>
  );
};
