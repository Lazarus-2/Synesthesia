"use client";

// AuraRing — full-screen Scriabin-color radial glow that "breathes" with
// the currently sounding chord. Sits behind everything in the player view.
//
// Behaviour:
//   • Reads `currentTime` from usePlayerStore.
//   • Looks up the active ChordEvent in `analysis.chords[]` and uses its
//     pre-computed Scriabin hex (`chord.color`). Falls back to the
//     SCRIABIN_COLORS map in lib/music if the backend didn't ship a color.
//   • Animates opacity with a 200ms sine "breath" via requestAnimationFrame
//     — no audio analyser plumbing required, so it works even before the
//     WaveSurfer AnalyserNode is ready.
//   • Color Storm mode (toggled in SettingsPanel) cranks the base opacity
//     way up and stacks an extra accent gradient for a saturated wash.
//
// Pointer-events: none, mounted once in HomeClient, z-0 → never blocks
// interaction with the player above it.

import React, { useEffect, useRef, useState } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";
import { useAppStore } from "../../store/useAppStore";
import { getChordColor } from "../../lib/music";

export const AuraRing: React.FC = () => {
  const { analysis } = useAnalysisStore();
  const { currentTime } = usePlayerStore();
  const colorStorm = useAppStore((s) => s.colorStorm);

  // Breathing factor 0..1 driven by RAF (decoupled from React render rate).
  const [breath, setBreath] = useState(0.5);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const start = performance.now();
    const tick = (t: number) => {
      if (!mounted) return;
      // ~3s breath cycle. sin → [0, 1].
      const phase = ((t - start) / 3000) * Math.PI * 2;
      const v = 0.5 + 0.5 * Math.sin(phase);
      setBreath(v);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      mounted = false;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  // Locate active chord. We don't bail when there's nothing — we want a
  // calm neutral aura on the landing page too.
  const activeChord = analysis?.chords?.find(
    (c) => currentTime >= c.start && currentTime < c.end,
  );
  const fallbackColor = analysis?.chords?.[0]
    ? getChordColor(analysis.chords[0].chord)
    : "#571bc1"; // neutral violet (matches --color-secondary-container)
  const color = activeChord?.color || fallbackColor;

  // Subtle by default; Color Storm cranks it.
  const baseOpacity = colorStorm ? 0.45 : 0.12;
  const peakOpacity = colorStorm ? 0.7 : 0.2;
  const opacity = baseOpacity + (peakOpacity - baseOpacity) * breath;

  // Slight scale wobble for breath-like motion.
  const scale = 1 + (colorStorm ? 0.08 : 0.03) * breath;

  return (
    <div
      aria-hidden
      className="fixed inset-0 pointer-events-none z-0 overflow-hidden"
      style={{
        // Smooth opacity transitions when a chord boundary crosses.
        transition: "background 600ms ease-out",
      }}
    >
      {/* Primary chord-colored radial */}
      <div
        className="absolute inset-0"
        style={{
          background: `radial-gradient(ellipse at 50% 40%, ${color} 0%, transparent 65%)`,
          opacity,
          transform: `scale(${scale})`,
          transformOrigin: "center",
          transition: "opacity 250ms linear, transform 600ms ease-out",
          mixBlendMode: colorStorm ? "screen" : "soft-light",
        }}
      />
      {/* Color Storm accent — secondary off-axis radial for richness. */}
      {colorStorm && (
        <>
          <div
            className="absolute inset-0"
            style={{
              background: `radial-gradient(circle at 15% 80%, ${color} 0%, transparent 55%)`,
              opacity: opacity * 0.7,
              mixBlendMode: "screen",
              transition: "opacity 250ms linear",
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background: `radial-gradient(circle at 85% 20%, ${color} 0%, transparent 55%)`,
              opacity: opacity * 0.6,
              mixBlendMode: "screen",
              transition: "opacity 250ms linear",
            }}
          />
        </>
      )}
    </div>
  );
};
