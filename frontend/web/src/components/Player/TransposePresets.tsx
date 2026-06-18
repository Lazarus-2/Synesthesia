"use client";

import React, { useState } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePracticeStore } from "../../store/usePracticeStore";
import { NOTES, FLAT_TO_SHARP } from "../../lib/music";

/** Transpose a key label (e.g. "A minor", "Db major") by N semitones, keeping
 *  the mode word. Returns the original on anything unparseable. */
function transposeKey(key: string, semitones: number): string {
  const m = key.match(/^([A-G][#b]?)(.*)$/);
  if (!m) return key;
  const [, rawRoot, rest] = m;
  const root = FLAT_TO_SHARP[rawRoot] ?? rawRoot;
  const idx = NOTES.indexOf(root.toUpperCase());
  if (idx < 0) return key;
  const newRoot = NOTES[(idx + semitones + 1200) % 12];
  return `${newRoot}${rest}`;
}

const OFFSETS = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5];

/**
 * One-click "change key" presets. Reads the detected key, lists each
 * transposition (±5 semitones) by its RESULTING key, and sets the shared
 * transpose value — which drives the chord labels and the audio pitch-shift
 * (AudioEngine ``pitchSemitones``). Complements the ±1 stepper in the BottomBar.
 */
export const TransposePresets: React.FC = () => {
  const analysis = useAnalysisStore((s) => s.analysis);
  const transpose = usePracticeStore((s) => s.transpose);
  const setTranspose = usePracticeStore((s) => s.setTranspose);
  const [open, setOpen] = useState(false);

  if (!analysis?.key) return null;
  const origKey = analysis.key;
  const currentKey = transposeKey(origKey, transpose);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Change key (transpose)"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full glass-panel text-xs font-medium text-on-surface-variant hover:text-primary hover:border-primary/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span className="material-symbols-outlined text-[18px]">tune</span>
        Key: <span className="text-on-surface font-semibold">{currentKey}</span>
      </button>

      {open && (
        <>
          {/* click-away backdrop */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden="true" />
          <div
            role="listbox"
            aria-label="Transpose to key"
            className="absolute right-0 mt-2 z-50 w-44 max-h-72 overflow-y-auto hide-scrollbar rounded-xl glass-panel border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] p-1"
          >
            {OFFSETS.map((o) => {
              const active = o === transpose;
              return (
                <button
                  key={o}
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    setTranspose(o);
                    setOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-xs transition-colors ${
                    active
                      ? "bg-primary-container/20 text-primary font-semibold"
                      : "text-on-surface-variant hover:bg-white/5 hover:text-on-surface"
                  }`}
                >
                  <span>{transposeKey(origKey, o)}</span>
                  <span className="tabular-nums text-on-surface-variant">
                    {o === 0 ? "orig" : `${o > 0 ? "+" : ""}${o}`}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};
