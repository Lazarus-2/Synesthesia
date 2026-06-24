"use client";

import React from "react";
import { usePlayAlongStore } from "../../store/usePlayAlongStore";
import { useAppStore } from "../../store/useAppStore";
import { instrumentToStem, type StemId } from "../../lib/practice";

const STEM_LABELS: Record<StemId, string> = {
  vocals: "Vocals",
  drums: "Drums",
  bass: "Bass",
  other: "Melodics",
};

/** One-tap backing-track presets. Rendered atop the StemMixer; disabled when no
 *  stems are available (the mixer shows the explanatory copy in that case). */
export const PlayAlongPresets: React.FC<{ availableStems: StemId[] }> = ({ availableStems }) => {
  const { engaged, mutedStem, engage, disengage } = usePlayAlongStore();
  const instrument = useAppStore((s) => s.instrument);
  const suggested = instrumentToStem(instrument);

  if (availableStems.length === 0) return null;

  return (
    <div className="glass-panel rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="font-headline text-lg text-white">Play-Along</span>
        {engaged && (
          <button onClick={disengage} className="text-xs text-on-surface-variant hover:text-error">
            Stop
          </button>
        )}
      </div>
      <p className="text-xs text-on-surface-variant -mt-1">
        Mute your instrument and play over the rest. Suggested for you: {STEM_LABELS[suggested]}.
      </p>
      <div className="flex flex-wrap gap-2">
        {availableStems.map((s) => {
          const active = engaged && mutedStem === s;
          return (
            <button
              key={s}
              onClick={() => (active ? disengage() : engage(s))}
              aria-pressed={active}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                active
                  ? "bg-primary-container/20 text-primary border border-primary-container/40"
                  : "glass-panel text-on-surface-variant hover:text-primary hover:border-primary/30"
              } ${s === suggested && !engaged ? "ring-1 ring-primary/40" : ""}`}
            >
              Mute {STEM_LABELS[s]}
            </button>
          );
        })}
      </div>
    </div>
  );
};
