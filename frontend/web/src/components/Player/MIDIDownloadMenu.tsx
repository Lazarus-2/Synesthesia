"use client";

import React, { useState } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { API_V1 } from "../../lib/apiClient";

const _STEMS: Array<{ key: string; label: string }> = [
  { key: "full", label: "Full Mix" },
  { key: "vocals", label: "Vocals" },
  { key: "drums", label: "Drums" },
  { key: "bass", label: "Bass" },
  { key: "other", label: "Other" },
];

/** Tiny dropdown that surfaces ``GET /api/v1/midi/{job_id}/{stem}``
 *  download links. Each row is a plain ``<a download>`` so the
 *  browser handles the binary blob — no fetch + Blob plumbing. */
export const MIDIDownloadMenu: React.FC = () => {
  const analysis = useAnalysisStore((s) => s.analysis);
  const [open, setOpen] = useState(false);
  // job_id is stamped onto the analysis envelope by the pipeline; for the
  // share view the SongAnalysis _id IS the job_id, so we use that.
  const jobId = (analysis as unknown as { job_id?: string; _id?: string } | null)?.job_id
    ?? (analysis as unknown as { _id?: string } | null)?._id;
  if (!analysis || !jobId) return null;

  return (
    <div className="relative inline-block">
      <button
        className="flex items-center gap-2 px-4 py-2 rounded-full glass-panel hover:border-primary/30 text-sm font-medium text-on-surface transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="material-symbols-outlined text-[18px] text-primary">download</span>
        Download MIDI
        <span className="material-symbols-outlined text-[16px] text-on-surface-variant">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open && (
        <ul
          className="absolute z-50 mt-2 right-0 min-w-[180px] glass-panel border border-white/10 rounded-lg overflow-hidden shadow-2xl"
          role="menu"
        >
          {_STEMS.map((s) => (
            <li key={s.key}>
              <a
                role="menuitem"
                className="flex items-center gap-2 px-3 py-2 hover:bg-surface-container-high text-sm text-on-surface transition-colors"
                href={`${API_V1}/midi/${jobId}/${s.key}`}
                download
                onClick={() => setOpen(false)}
              >
                <span className="material-symbols-outlined text-[16px] text-on-surface-variant">
                  music_note
                </span>
                {s.label}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
