"use client";

import React from "react";

/**
 * Tiny confidence indicator for analysis estimates (key / tempo).
 *
 * Renders a small glowing dot color-coded by confidence band, with the
 * exact percentage available on hover and to screen readers. Renders
 * nothing when the value is absent (analyses from before Phase 4).
 */

interface ConfidenceDotProps {
  /** Confidence in [0, 1]; null/undefined hides the dot entirely. */
  value?: number | null;
  /** What the confidence describes, e.g. "Key detection". */
  label: string;
}

const BANDS = [
  {
    min: 0.7,
    word: "high",
    dot: "bg-emerald-400",
    glow: "shadow-[0_0_8px_rgba(52,211,153,0.7)]",
  },
  {
    min: 0.4,
    word: "medium",
    dot: "bg-amber-400",
    glow: "shadow-[0_0_8px_rgba(251,191,36,0.7)]",
  },
  {
    min: 0,
    word: "low",
    dot: "bg-rose-400",
    glow: "shadow-[0_0_8px_rgba(251,113,133,0.7)]",
  },
] as const;

export const ConfidenceDot: React.FC<ConfidenceDotProps> = ({ value, label }) => {
  if (value == null || Number.isNaN(value)) return null;

  const clamped = Math.min(1, Math.max(0, value));
  const pct = Math.round(clamped * 100);
  const band = BANDS.find((b) => clamped >= b.min) ?? BANDS[BANDS.length - 1];
  const description = `${label} confidence: ${pct}% (${band.word})`;

  return (
    <span
      role="img"
      aria-label={description}
      title={description}
      className="inline-flex items-center justify-center w-3 h-3 -mr-0.5 cursor-help"
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${band.dot} ${band.glow} ${
          band.word === "low" ? "animate-pulse" : ""
        }`}
      />
    </span>
  );
};
