"use client";

import React from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";
import { usePracticeStore } from "../../store/usePracticeStore";
import { useReharmStore } from "../../store/useReharmStore";
import { transposeChord } from "../../lib/music";
import type { RomanEntry, RomanModulation, RomanCadence } from "../../types";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// Figured-bass notation from inversion number.
function inversionSuffix(inv: number | undefined): string {
  if (!inv) return "";
  const map: Record<number, string> = { 1: "6", 2: "64", 3: "42" };
  return map[inv] ?? "";
}

// ---------- small presentational sub-components ----------

const FunctionPill: React.FC<{ fn: string }> = ({ fn }) => {
  const colorMap: Record<string, string> = {
    tonic: "bg-primary/20 text-primary",
    dominant: "bg-error/20 text-error-container",
    subdominant: "bg-secondary-container/30 text-on-secondary-container",
    submediant: "bg-tertiary/20 text-on-surface-variant",
    borrowed: "bg-warning/20 text-on-surface",
    secondary: "bg-yellow-400/20 text-yellow-300",
    secondary_dominant: "bg-yellow-400/20 text-yellow-300",
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

  if (!analysis?.chords || analysis.chords.length === 0) {
    return (
      <section className="glass-panel rounded-xl p-4">
        <div className="flex items-center justify-center h-24 text-on-surface-variant text-sm">
          No chord data available
        </div>
      </section>
    );
  }

  const activeIdx = analysis.chords.findIndex(
    (c) => currentTime >= c.start && currentTime < c.end
  );

  const entries: RomanEntry[] = analysis.roman?.entries ?? [];
  const modulations: RomanModulation[] = analysis.roman?.modulations ?? [];
  const cadences: RomanCadence[] = analysis.roman?.cadences ?? [];

  // Build per-chord-index lookup maps from time-aligned entries.
  // An entry's [start,end) bracket maps to the chord with closest start.
  const entryByChordIdx = new Map<number, RomanEntry>();
  for (const entry of entries) {
    const idx = analysis.chords.findIndex(
      (c) => Math.abs(c.start - entry.start) < 0.15
    );
    if (idx !== -1) entryByChordIdx.set(idx, entry);
  }

  // Cadence badges: backend stores {type, index} where index is chord index.
  const cadenceByChordIdx = new Map<number, RomanCadence>();
  for (const cadence of cadences) {
    if (cadence.index >= 0 && cadence.index < analysis.chords.length) {
      cadenceByChordIdx.set(cadence.index, cadence);
    }
  }

  // Modulation chips: backend stores {to_key, at_index} where at_index is
  // the chord index where the new key begins. Render chip BEFORE that chord.
  const modulationBeforeIdx = new Map<number, RomanModulation>();
  for (const mod of modulations) {
    if (mod.at_index >= 0 && mod.at_index < analysis.chords.length) {
      modulationBeforeIdx.set(mod.at_index, mod);
    }
  }

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
      <div className="flex items-end gap-4 overflow-x-auto hide-scrollbar pb-2">
        {analysis.chords.map((chord, i) => {
          const isActive = i === activeIdx;
          const isPast = i < activeIdx;
          const isFuture = i > activeIdx;
          const entry = entryByChordIdx.get(i);
          const cadence = cadenceByChordIdx.get(i);
          const modBefore = modulationBeforeIdx.get(i);

          return (
            <React.Fragment key={i}>
              {modBefore && <ModulationChip mod={modBefore} />}

              <div
                className={`flex-shrink-0 rounded-lg flex flex-col items-center justify-center cursor-pointer transition-all duration-200 ${
                  isActive
                    ? "w-32 bg-surface-container-high border-2 border-primary-container inner-glow-focus transform scale-105 z-10"
                    : "w-24 bg-surface-container-high border border-white/5"
                } ${isPast ? "opacity-50 hover:opacity-100" : ""} ${
                  isFuture ? "opacity-70 hover:opacity-100" : ""
                } p-2 gap-1`}
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

                {/* Roman numeral + inversion (figured-bass) */}
                {entry && (
                  <span
                    className={`font-headline ${
                      isActive ? "text-lg font-semibold text-secondary-container" : "text-sm text-on-surface-variant"
                    }`}
                    title={entry.is_secondary ? "Secondary dominant" : entry.is_borrowed ? "Borrowed chord" : entry.function}
                  >
                    {entry.numeral}
                    {inversionSuffix(entry.inversion) && (
                      <sup className="text-[9px]">{inversionSuffix(entry.inversion)}</sup>
                    )}
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

                {/* Cadence badge */}
                {cadence && <CadenceBadge type={cadence.type} />}

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
