"use client";

import React, { useState } from "react";
import { useSavedLoopsStore } from "../../store/useSavedLoopsStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePracticeStore } from "../../store/usePracticeStore";
import { formatTime } from "../../lib/format";

/** Save + recall named A/B regions for the current song. */
export const SavedLoops: React.FC = () => {
  const jobId = useAnalysisStore((s) => s.jobId);
  const { list, save, remove } = useSavedLoopsStore();
  const { loopStart, loopEnd, setLoopStart, setLoopEnd } = usePracticeStore();
  const [name, setName] = useState("");

  if (!jobId) return null;
  const loops = list(jobId);
  const canSave = loopStart !== null && loopEnd !== null && loopEnd > loopStart;

  return (
    <div className="glass-panel rounded-lg p-3 flex flex-col gap-2 text-xs">
      <span className="font-semibold text-on-surface flex items-center gap-1.5">
        <span className="material-symbols-outlined text-[16px]">bookmark</span>
        Saved Loops
      </span>

      <div className="flex gap-1.5">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={canSave ? "Name this loop" : "Set A/B first"}
          aria-label="Loop name"
          disabled={!canSave}
          className="flex-grow bg-white/5 rounded px-2 py-1 text-on-surface placeholder:text-on-surface-variant/60 disabled:opacity-40"
        />
        <button
          onClick={() => {
            if (canSave) {
              save(jobId, name.trim(), loopStart!, loopEnd!);
              setName("");
            }
          }}
          disabled={!canSave}
          className="px-2 py-1 rounded glass-panel text-primary hover:border-primary/30 disabled:opacity-40"
        >
          Save
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {loops.length === 0 && <span className="text-on-surface-variant/70">No saved loops yet.</span>}
        {loops.map((l) => (
          <span key={l.id} className="flex items-center gap-1 px-2 py-1 rounded-full bg-white/5">
            <button
              onClick={() => {
                setLoopStart(l.start);
                setLoopEnd(l.end);
              }}
              title={`${formatTime(l.start)} – ${formatTime(l.end)}`}
              className="text-on-surface hover:text-primary"
            >
              {l.name}
            </button>
            <button
              onClick={() => remove(jobId, l.id)}
              aria-label={`Delete ${l.name}`}
              className="text-on-surface-variant hover:text-error"
            >
              ✕
            </button>
          </span>
        ))}
      </div>
    </div>
  );
};
