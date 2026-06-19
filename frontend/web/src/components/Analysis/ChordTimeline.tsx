"use client";

import React, { useEffect, useMemo, useRef } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";
import { usePracticeStore } from "../../store/usePracticeStore";
import { useReharmStore } from "../../store/useReharmStore";
import { transposeChord, getChordColor } from "../../lib/music";
import type { RomanEntry, RomanModulation } from "../../types";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ---------- small presentational sub-components ----------

const FunctionPill: React.FC<{ fn: string }> = ({ fn }) => {
  // Values match harmonic_function() in backend/theory/roman.py exactly.
  const colorMap: Record<string, string> = {
    tonic:             "bg-primary/20 text-primary",
    supertonic:        "bg-secondary/20 text-on-surface-variant",
    mediant:           "bg-tertiary/20 text-on-surface-variant",
    subdominant:       "bg-secondary-container/30 text-on-secondary-container",
    dominant:          "bg-error/20 text-error-container",
    submediant:        "bg-tertiary/20 text-on-surface-variant",
    leading_tone:      "bg-surface-container-highest/60 text-on-surface-variant",
    secondary_dominant:"bg-yellow-400/20 text-yellow-300",
    chromatic:         "bg-blue-400/20 text-blue-300",
  };
  const cls = colorMap[fn] ?? "bg-white/10 text-on-surface-variant";
  return (
    <span className={`text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full ${cls}`}>
      {fn.replace("_", " ")}
    </span>
  );
};

const CadenceBadge: React.FC<{ type: string }> = ({ type }) => {
  const label: Record<string, string> = {
    PAC: "PAC",
    IAC: "IAC",
    half: "HC",
    deceptive: "DC",
    plagal: "PC",
  };
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold bg-secondary-container/40 text-on-secondary-container border border-secondary-container/60"
      title={`${type} cadence`}
    >
      {label[type] ?? type}
    </span>
  );
};

const ModulationChip: React.FC<{ mod: RomanModulation }> = ({ mod }) => (
  <div className="flex-shrink-0 flex flex-col items-center justify-center w-16 self-stretch gap-1">
    <span className="text-[8px] font-semibold text-tertiary uppercase tracking-widest">mod</span>
    <span className="text-[10px] font-bold text-on-surface border border-tertiary/40 bg-tertiary/10 px-1.5 py-0.5 rounded">
      {mod.to_key}
    </span>
  </div>
);

// ---------- main component ----------

export const ChordTimeline: React.FC = () => {
  const { analysis } = useAnalysisStore();
  const { currentTime, wavesurfer } = usePlayerStore();
  const transpose = usePracticeStore((s) => s.transpose);
  const openReharm = useReharmStore((s) => s.openFor);

  // Hooks must run before any early return. Compute the active chord index up
  // front (safe on an empty list), and auto-scroll it into view so the chords
  // follow the music (Chordify-style) instead of drifting off-screen.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const activeRef = useRef<HTMLDivElement | null>(null);
  const activeIdx = (analysis?.chords ?? []).findIndex(
    (c) => currentTime >= c.start && currentTime < c.end
  );
  useEffect(() => {
    const c = containerRef.current;
    const a = activeRef.current;
    if (!c || !a) return;
    // Centre the active card horizontally; scroll only the strip (not the page).
    const target = a.offsetLeft - c.clientWidth / 2 + a.clientWidth / 2;
    c.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
  }, [activeIdx]);

  // Per-chord-index lookup maps from the time-aligned Roman entries. These
  // depend only on the analysis, so memoize them — otherwise the O(entries ×
  // chords) build reran on every currentTime tick (~10×/sec) during playback.
  const { entryByChordIdx, modulationBeforeIdx } = useMemo(() => {
    const chords = analysis?.chords ?? [];
    const entries: RomanEntry[] = analysis?.roman?.entries ?? [];
    const modulations: RomanModulation[] = analysis?.roman?.modulations ?? [];
    const ebci = new Map<number, RomanEntry>();
    for (const entry of entries) {
      const idx = chords.findIndex((c) => Math.abs(c.start - entry.start) < 0.15);
      if (idx !== -1) ebci.set(idx, entry);
    }
    const mbi = new Map<number, RomanModulation>();
    for (const mod of modulations) {
      const entry = entries[mod.at_index];
      if (!entry) continue;
      const chordIdx = chords.findIndex((c) => Math.abs(c.start - entry.start) < 0.15);
      if (chordIdx !== -1) mbi.set(chordIdx, mod);
    }
    return { entryByChordIdx: ebci, modulationBeforeIdx: mbi };
  }, [analysis]);

  if (!analysis?.chords || analysis.chords.length === 0) {
    return (
      <section className="glass-panel rounded-xl p-4">
        <div className="flex items-center justify-center h-24 text-on-surface-variant text-sm">
          No chord data available
        </div>
      </section>
    );
  }

  // entryByChordIdx / modulationBeforeIdx are memoized above. Cadence comes
  // from entry.cadence (already time-aligned per-entry by the backend).

  const handleChordClick = (startTime: number, idx: number, e: React.MouseEvent) => {
    if (e.shiftKey && analysis?.chords) {
      openReharm(idx, analysis.chords[idx]);
      return;
    }
    if (wavesurfer) {
      wavesurfer.seekTo(startTime / wavesurfer.getDuration());
    }
  };

  return (
    <section className="glass-panel rounded-xl p-4">
      <div ref={containerRef} className="flex items-end gap-4 overflow-x-auto hide-scrollbar pb-2 scroll-smooth">
        {analysis.chords.map((chord, i) => {
          const isActive = i === activeIdx;
          const isPast = i < activeIdx;
          const isFuture = i > activeIdx;
          const entry = entryByChordIdx.get(i);
          // I1: cadence comes from entry.cadence (time-aligned) — no index-space mismatch.
          const cadenceType = entry?.cadence ?? null;
          const modBefore = modulationBeforeIdx.get(i);

          return (
            <React.Fragment key={i}>
              {modBefore && <ModulationChip mod={modBefore} />}

              <div
                ref={isActive ? activeRef : undefined}
                className={`flex-shrink-0 rounded-lg flex flex-col items-center justify-center cursor-pointer transition-all duration-200 ${
                  isActive
                    ? "w-32 bg-surface-container-high border-2 transform scale-105 z-10"
                    : "w-24 bg-surface-container-high border border-white/5"
                } ${isPast ? "opacity-50 hover:opacity-100" : ""} ${
                  isFuture ? "opacity-70 hover:opacity-100" : ""
                } p-2 gap-1`}
                // Synesthetic accent: the active chord glows + is bordered in its
                // own Scriabin colour (the whole point of "Synesthesia").
                style={
                  isActive
                    ? {
                        borderColor: getChordColor(chord.chord),
                        boxShadow: `0 0 26px ${getChordColor(chord.chord)}59, inset 0 0 14px ${getChordColor(chord.chord)}26`,
                      }
                    : undefined
                }
                onClick={(e) => handleChordClick(chord.start, i, e)}
                title="Click to seek · Shift-click to reharm"
              >
                <span
                  className={`font-headline ${
                    isActive
                      ? "text-4xl font-semibold text-primary"
                      : "text-2xl font-medium text-on-surface"
                  }`}
                >
                  {transpose !== 0 ? transposeChord(chord.chord, transpose) : chord.chord}
                </span>

                {/* Roman numeral — entry.numeral already includes figured bass from music21.
                    I2: Do NOT append an extra inversion suffix; numeral is the single source of truth. */}
                {entry && (
                  <span
                    className={`font-headline ${
                      isActive ? "text-lg font-semibold text-secondary-container" : "text-sm text-on-surface-variant"
                    }`}
                    title={entry.is_secondary ? "Secondary dominant" : entry.is_borrowed ? "Borrowed chord" : entry.function}
                  >
                    {entry.numeral}
                    {entry.is_secondary && (
                      <span className="ml-0.5 text-[9px] text-yellow-400 font-bold">2°</span>
                    )}
                    {entry.is_borrowed && (
                      <span className="ml-0.5 text-[9px] text-blue-400 font-bold">b</span>
                    )}
                  </span>
                )}

                {/* Function pill */}
                {entry && <FunctionPill fn={entry.function} />}

                {/* Cadence badge — sourced from entry.cadence (time-aligned, N.C.-safe) */}
                {cadenceType && <CadenceBadge type={cadenceType} />}

                {/* Timestamp */}
                <span
                  className={`text-xs font-medium ${
                    isActive ? "text-primary-container" : "text-on-surface-variant"
                  }`}
                >
                  {formatTime(chord.start)}
                </span>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </section>
  );
};
