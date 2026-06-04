"use client";

import React, { useMemo } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePracticeStore } from "../../store/usePracticeStore";
import { transposeChord } from "../../lib/music";

const _OPEN_SHAPES = new Set(["G", "C", "D", "Em", "Am", "A", "E", "Dm"]);

/** Capo Whisperer — given the song's chord set, find the capo position
 *  (0-7) that maximises the count of "open-shape" chords from the
 *  curated set. ``Apply capo`` updates ``usePracticeStore.transpose``
 *  so the chord chip labels re-render in capo-relative shapes
 *  immediately. */
export const CapoWhisperer: React.FC = () => {
  const analysis = useAnalysisStore((s) => s.analysis);
  const transpose = usePracticeStore((s) => s.transpose);
  const setTranspose = usePracticeStore((s) => s.setTranspose);

  const recommendation = useMemo(() => {
    if (!analysis?.chords?.length) return null;
    const roots = Array.from(new Set(analysis.chords.map((c) => c.chord)));
    let bestFret = 0;
    let bestScore = -1;
    let bestShapes: string[] = roots;
    for (let fret = 0; fret <= 7; fret++) {
      const shapes = roots.map((c) => transposeChord(c, -fret));
      const score = shapes.filter((s) => _OPEN_SHAPES.has(stripQuality(s))).length;
      if (score > bestScore) {
        bestScore = score;
        bestFret = fret;
        bestShapes = shapes;
      }
    }
    return { fret: bestFret, shapes: bestShapes, openCount: bestScore, total: roots.length };
  }, [analysis?.chords]);

  if (!recommendation || !analysis?.chords?.length) return null;
  if (recommendation.fret === 0) {
    return (
      <div className="px-4 py-3 rounded-xl glass-panel border border-white/5 text-sm text-on-surface-variant">
        🎸 Capo Whisperer · Already at the easiest position — capo 0.
      </div>
    );
  }

  const originalRoots = Array.from(new Set(analysis.chords.map((c) => c.chord))).slice(0, 6);
  const capoShapes = recommendation.shapes.slice(0, 6);

  return (
    <div className="px-4 py-3 rounded-xl glass-panel border border-primary-container/20">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-headline text-base text-on-surface flex items-center gap-2">
          <span className="material-symbols-outlined text-primary-container">graphic_eq</span>
          Capo Whisperer
        </h4>
        <button
          className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider transition-colors ${
            transpose === -recommendation.fret
              ? "primary-gradient text-on-primary"
              : "glass-panel text-on-surface hover:border-primary/30"
          }`}
          onClick={() =>
            setTranspose(transpose === -recommendation.fret ? 0 : -recommendation.fret)
          }
        >
          {transpose === -recommendation.fret
            ? `Capo ${recommendation.fret} applied`
            : `Apply Capo ${recommendation.fret}`}
        </button>
      </div>
      <p className="text-xs text-on-surface-variant mb-2">
        At capo {recommendation.fret}, {recommendation.openCount} of {recommendation.total} unique chords
        become open shapes — easier to play and to sing over.
      </p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div>
          <div className="text-on-surface-variant uppercase tracking-wider mb-1">Original</div>
          <div className="text-on-surface font-mono">
            {originalRoots.join(" · ")}
          </div>
        </div>
        <div>
          <div className="text-on-surface-variant uppercase tracking-wider mb-1">With capo</div>
          <div className="text-on-surface font-mono">
            {capoShapes.join(" · ")}
          </div>
        </div>
      </div>
    </div>
  );
};

function stripQuality(chord: string): string {
  // Treat "Em7" / "Em9" as "Em" for the open-shape check.
  const m = chord.match(/^([A-G][b#]?)(m(?!a)|dim|aug)?/);
  return m ? `${m[1]}${m[2] ?? ""}` : chord;
}
