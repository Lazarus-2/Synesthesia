"use client";

import React from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { SimilarSongs } from "./SimilarSongs";
import { analyzeForm } from "../../lib/songForm";

// ---- sub-components ----

const TechniqueChip: React.FC<{ label: string }> = ({ label }) => (
  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20">
    {label}
  </span>
);

const CadenceCallout: React.FC<{ type: string; label: string }> = ({ type, label }) => {
  const colorMap: Record<string, string> = {
    PAC: "border-secondary-container/50 bg-secondary-container/10 text-on-secondary-container",
    IAC: "border-secondary-container/40 bg-secondary-container/5 text-on-secondary-container",
    half: "border-primary/30 bg-primary/5 text-primary",
    deceptive: "border-error/30 bg-error/5 text-error-container",
    plagal: "border-tertiary/30 bg-tertiary/5 text-on-surface-variant",
  };
  const cls = colorMap[type] ?? "border-white/10 bg-white/5 text-on-surface-variant";
  return (
    <div className={`flex items-center gap-2 border ${cls} px-3 py-2 rounded-lg`}>
      <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
        music_note
      </span>
      <span className="text-xs font-medium">{label}</span>
    </div>
  );
};

// ---- main component ----

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
  const cadences = roman?.cadences ?? [];
  const form = analyzeForm(analysis.sections ?? []);

  return (
    <div className="flex flex-col gap-6 p-6 overflow-y-auto hide-scrollbar flex-grow">
      <h2 className="font-headline text-2xl font-medium text-white">Analysis</h2>

      {/* Roman Numeral Function Card — uses entries[0] when available, falls back to flat arrays */}
      {roman && (
        <div className="flex items-center gap-4 bg-surface-container-high rounded-lg p-4 border border-white/5">
          <div className="font-headline text-4xl font-semibold text-primary">
            {roman.entries?.[0]?.numeral ?? roman.progression?.[0] ?? "I"}
          </div>
          <div className="flex-grow">
            <p className="text-sm font-semibold text-on-surface">
              {roman.entries?.[0]?.function ?? roman.function?.[0] ?? "Tonic Chord"}
            </p>
            <p className="text-sm text-on-surface-variant">
              {analysis.key_confidence != null && analysis.key_confidence < 0.4
                ? "Likely key of "
                : "Key of "}
              {roman.key || analysis.key}
            </p>
          </div>
        </div>
      )}

      {/* Chord Progression Row */}
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

      {/* ---- Structured theory block ---- */}
      {theory ? (
        <>
          {/* Pattern name */}
          {theory.pattern_name && (
            <div>
              <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-1">
                Pattern
              </h3>
              <p className="font-headline text-lg font-semibold text-on-surface">
                {theory.pattern_name}
              </p>
            </div>
          )}

          {/* Notable techniques chips */}
          {theory.notable_techniques && theory.notable_techniques.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
                Techniques
              </h3>
              <div className="flex flex-wrap gap-2">
                {theory.notable_techniques.map((t, i) => (
                  <TechniqueChip key={i} label={t} />
                ))}
              </div>
            </div>
          )}

          {/* Function explanation prose */}
          {theory.function_explanation && (
            <div className="border border-secondary-container/30 bg-secondary-container/10 p-5 rounded-xl">
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
              <p className="text-sm text-on-surface/90 leading-relaxed">
                {theory.function_explanation}
              </p>
            </div>
          )}

          {/* Cadence callouts from roman.cadences — identified by chord index */}
          {cadences.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
                Cadences
              </h3>
              <div className="flex flex-col gap-2">
                {cadences.map((c, i) => {
                  const numeralsAtIndex =
                    roman?.progression && c.index > 0
                      ? [roman.progression[c.index - 1], roman.progression[c.index]].filter(Boolean)
                      : roman?.progression?.slice(c.index, c.index + 1) ?? [];
                  const numeralStr = numeralsAtIndex.join(" → ");
                  const labelMap: Record<string, string> = {
                    PAC: `Perfect Authentic Cadence${numeralStr ? ` — ${numeralStr}` : ""}`,
                    IAC: `Imperfect Authentic Cadence${numeralStr ? ` — ${numeralStr}` : ""}`,
                    half: `Half Cadence${numeralStr ? ` — ${numeralStr}` : ""}`,
                    deceptive: `Deceptive Cadence${numeralStr ? ` — ${numeralStr}` : ""}`,
                    plagal: `Plagal Cadence${numeralStr ? ` — ${numeralStr}` : ""}`,
                  };
                  return (
                    <CadenceCallout
                      key={i}
                      type={c.type}
                      label={labelMap[c.type] ?? `${c.type}${numeralStr ? ` — ${numeralStr}` : ""}`}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Grounded similar song citation from theory object */}
          {theory.similar_song && (
            <div className="flex items-center gap-3 bg-surface-container-high rounded-lg px-4 py-3 border border-white/5">
              <span
                className="material-symbols-outlined text-primary"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                queue_music
              </span>
              <div>
                <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-widest">
                  Similar song
                </p>
                <p className="text-sm text-on-surface font-medium">{theory.similar_song}</p>
              </div>
            </div>
          )}
        </>
      ) : (
        /* Legacy fallback — flat theory_explanation string */
        analysis.theory_explanation && (
          <div className="mt-4 border border-secondary-container/30 bg-secondary-container/10 p-5 rounded-xl">
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
        )
      )}

      {/* Song-form card — deterministic structure labelling from sections */}
      {form.sequence.length > 0 && (
        <div className="bg-surface-container-high rounded-lg p-4 border border-white/5">
          <div className="flex items-baseline gap-2 mb-3">
            <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest">
              Form
            </h3>
            <span className="font-headline text-base font-semibold text-primary">
              {form.label}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {form.sequence.map((name, i) => (
              <span
                key={i}
                className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-white/5 text-on-surface-variant border border-white/10"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Vibe Palette — unchanged */}
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

      {/* Similar Songs panel — self-hides when empty */}
      <SimilarSongs />
    </div>
  );
};
