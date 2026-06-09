"use client";

import React from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";

export const TheoryPanel: React.FC = () => {
  const { analysis } = useAnalysisStore();

  if (!analysis) {
    return (
      <div className="flex-grow p-6 flex items-center justify-center text-on-surface-variant text-sm">
        Upload a song to see theory analysis
      </div>
    );
  }

  const roman = analysis.roman;
  const theory = analysis.theory;

  return (
    <div className="flex flex-col gap-6 p-6 overflow-y-auto hide-scrollbar flex-grow">
      <h2 className="font-headline text-2xl font-medium text-white">Analysis</h2>

      {/* Roman Numeral Function Card */}
      {roman && (
        <div className="flex items-center gap-4 bg-surface-container-high rounded-lg p-4 border border-white/5">
          <div className="font-headline text-4xl font-semibold text-primary">
            {roman.progression?.[0] || "I"}
          </div>
          <div className="flex-grow">
            <p className="text-sm font-semibold text-on-surface">
              {roman.function?.[0] || "Tonic Chord"}
            </p>
            <p className="text-sm text-on-surface-variant">
              Key of {roman.key || analysis.key}
            </p>
          </div>
        </div>
      )}

      {/* Chord Progression Display */}
      {roman?.progression && (
        <div className="flex gap-2 font-headline text-4xl text-on-surface-variant/70 flex-wrap">
          {roman.progression.map((numeral, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span className="text-white/20">-</span>}
              <span className={i === 0 ? "text-primary" : ""}>{numeral}</span>
            </React.Fragment>
          ))}
        </div>
      )}

      {/* Structured AI Insight — renders chips when theory object is present */}
      {theory ? (
        <div className="mt-4 border-l-4 border-secondary-container bg-secondary-container/10 p-5 rounded-r-xl flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span
              className="material-symbols-outlined text-secondary-container"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              lightbulb
            </span>
            <h4 className="text-sm font-semibold text-on-secondary-container">
              AI Insight
            </h4>
          </div>

          {/* Key summary */}
          <p className="text-sm text-on-surface/90 leading-relaxed">
            {theory.key_summary}
          </p>

          {/* Pattern chip */}
          {theory.pattern_name && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest">
                Pattern
              </span>
              <span className="px-2 py-0.5 rounded-full bg-primary/20 text-primary text-xs font-medium">
                {theory.pattern_name}
              </span>
            </div>
          )}

          {/* Technique chips */}
          {theory.notable_techniques && theory.notable_techniques.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest">
                Techniques
              </span>
              {theory.notable_techniques.map((t, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-full bg-secondary/20 text-secondary text-xs font-medium"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {/* Similar song citation */}
          {theory.similar_song && (
            <p className="text-xs text-on-surface-variant italic">
              Similar: {theory.similar_song}
            </p>
          )}

          {/* Function explanation as prose */}
          <p className="text-sm text-on-surface/80 leading-relaxed">
            {theory.function_explanation}
          </p>
        </div>
      ) : analysis.theory_explanation ? (
        /* Legacy fallback: render the flat string if no structured theory */
        <div className="mt-4 border-l-4 border-secondary-container bg-secondary-container/10 p-5 rounded-r-xl">
          <div className="flex items-center gap-2 mb-2">
            <span
              className="material-symbols-outlined text-secondary-container"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              lightbulb
            </span>
            <h4 className="text-sm font-semibold text-on-secondary-container">
              AI Insight
            </h4>
          </div>
          <p className="text-sm text-on-surface/90 leading-relaxed whitespace-pre-wrap">
            {analysis.theory_explanation}
          </p>
        </div>
      ) : null}

      {/* Vibe Palette */}
      {analysis.vibe_palette && analysis.vibe_palette.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-3">
            Synesthesia Palette
          </h3>
          <div className="flex gap-2">
            {analysis.vibe_palette.map((color, i) => (
              <div
                key={i}
                className="w-10 h-10 rounded-lg border border-white/10 shadow-lg"
                style={{ backgroundColor: color }}
                title={color}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
