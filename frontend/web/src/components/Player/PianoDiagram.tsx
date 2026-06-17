"use client";

import React, { useMemo } from "react";
import { ChordDiagram } from "../../types";
import { NOTES, FLAT_TO_SHARP } from "../../lib/music";

/**
 * Piano chord diagram — an SVG keyboard that highlights the notes of a chord.
 *
 * The backend emits piano voicings as note+octave strings on
 * ``ChordDiagram.right_hand`` / ``.left_hand`` (e.g. ``["A3","C4","E4"]``,
 * with flats like ``"Eb4"``). The old player only rendered a guitar fretboard
 * and ignored these, so piano (and other non-guitar instruments) showed
 * "No diagram available". This renders them properly.
 *
 * Right-hand notes glow amber (the primary brand colour); left-hand notes glow
 * violet (secondary). Note names are printed on highlighted keys.
 */

const WHITE_PCS = ["C", "D", "E", "F", "G", "A", "B"];
// Which white-key index (within an octave) a black key sits to the right of.
const BLACK_AFTER: Record<number, string> = { 0: "C#", 1: "D#", 3: "F#", 4: "G#", 5: "A#" };

interface ParsedNote {
  pc: string; // pitch class, normalised to sharps (e.g. "D#")
  octave: number;
  key: string; // "D#4"
}

function parseNote(raw: string): ParsedNote | null {
  const m = raw.trim().match(/^([A-Ga-g])([#b]?)(-?\d+)?$/);
  if (!m) return null;
  let pc = m[1].toUpperCase() + (m[2] || "");
  if (pc.endsWith("b") && FLAT_TO_SHARP[pc]) pc = FLAT_TO_SHARP[pc];
  if (!NOTES.includes(pc)) return null;
  const octave = m[3] !== undefined ? parseInt(m[3], 10) : 4;
  return { pc, octave, key: `${pc}${octave}` };
}

const WHITE_W = 26;
const WHITE_H = 104;
const BLACK_W = 15;
const BLACK_H = 64;

export const PianoDiagram: React.FC<{ diagram?: ChordDiagram }> = ({ diagram }) => {
  const model = useMemo(() => {
    const right = (diagram?.right_hand ?? []).map(parseNote).filter(Boolean) as ParsedNote[];
    const left = (diagram?.left_hand ?? []).map(parseNote).filter(Boolean) as ParsedNote[];
    const all = [...right, ...left];
    if (all.length === 0) return null;

    const rightKeys = new Set(right.map((n) => n.key));
    const leftKeys = new Set(left.map((n) => n.key));

    // Octave span covering every note, padded to feel like a real keyboard.
    const minOct = Math.min(...all.map((n) => n.octave));
    let maxOct = Math.max(...all.map((n) => n.octave));
    // Ensure at least 2 octaves of context.
    if (maxOct - minOct < 1) maxOct = minOct + 1;

    const octaves: number[] = [];
    for (let o = minOct; o <= maxOct; o++) octaves.push(o);
    return { rightKeys, leftKeys, octaves };
  }, [diagram]);

  if (!diagram || diagram.no_voicing || !model) {
    return (
      <div className="w-full aspect-[3/2] bg-surface-container-highest rounded-xl border border-white/10 p-4 flex items-center justify-center text-on-surface-variant text-sm text-center">
        {diagram?.no_voicing ? "No voicing available for this chord" : "No diagram available"}
      </div>
    );
  }

  const { rightKeys, leftKeys, octaves } = model;
  const whiteCount = octaves.length * 7;
  const vbW = whiteCount * WHITE_W;
  const vbH = WHITE_H + 8;

  const colourFor = (key: string): "right" | "left" | null =>
    rightKeys.has(key) ? "right" : leftKeys.has(key) ? "left" : null;

  return (
    <div className="w-full aspect-[3/2] bg-surface-container-highest rounded-xl border border-white/10 p-4 flex items-center justify-center overflow-hidden">
      <svg
        viewBox={`0 0 ${vbW} ${vbH}`}
        className="w-full h-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Piano voicing for ${diagram.chord}`}
      >
        {/* White keys */}
        {octaves.map((oct, oi) =>
          WHITE_PCS.map((pc, wi) => {
            const idx = oi * 7 + wi;
            const x = idx * WHITE_W;
            const tone = colourFor(`${pc}${oct}`);
            const fill = tone === "right" ? "#ffb547" : tone === "left" ? "#8b6fd6" : "#e9ecf5";
            return (
              <g key={`w-${pc}-${oct}`}>
                <rect
                  x={x + 0.5}
                  y={0.5}
                  width={WHITE_W - 1}
                  height={WHITE_H}
                  rx={3}
                  fill={fill}
                  stroke="#0a0e19"
                  strokeWidth={1}
                />
                {tone && (
                  <text
                    x={x + WHITE_W / 2}
                    y={WHITE_H - 10}
                    textAnchor="middle"
                    fontSize={11}
                    fontWeight={700}
                    fill="#452b00"
                  >
                    {pc}
                  </text>
                )}
              </g>
            );
          })
        )}

        {/* Black keys (drawn on top) */}
        {octaves.map((oct, oi) =>
          Object.entries(BLACK_AFTER).map(([afterIdxStr, pc]) => {
            const afterIdx = Number(afterIdxStr);
            const idx = oi * 7 + afterIdx;
            const x = (idx + 1) * WHITE_W - BLACK_W / 2;
            const tone = colourFor(`${pc}${oct}`);
            const fill = tone === "right" ? "#c77f00" : tone === "left" ? "#571bc1" : "#14181f";
            return (
              <g key={`b-${pc}-${oct}`}>
                <rect
                  x={x}
                  y={0}
                  width={BLACK_W}
                  height={BLACK_H}
                  rx={2.5}
                  fill={fill}
                  stroke="#0a0e19"
                  strokeWidth={1}
                />
                {tone && (
                  <text
                    x={x + BLACK_W / 2}
                    y={BLACK_H - 6}
                    textAnchor="middle"
                    fontSize={8}
                    fontWeight={700}
                    fill={tone === "right" ? "#452b00" : "#ffffff"}
                  >
                    {pc.replace("#", "♯")}
                  </text>
                )}
              </g>
            );
          })
        )}
      </svg>
    </div>
  );
};
