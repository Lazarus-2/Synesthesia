"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useReharmStore } from "../../store/useReharmStore";
import { transposeChord } from "../../lib/music";

type Tone = typeof import("tone");

/** "What if?" chord-swap explorer.
 *
 *  Click a chord chip → open this modal → see four substitution
 *  candidates (relative minor/major, tritone sub, secondary dominant,
 *  modal interchange). Each has a 🔊 preview button that plays the
 *  swapped chord via a Tone.js PolySynth (built-in; no sample
 *  loading). Apply just closes the modal — we don't mutate the
 *  analysis, this is exploratory. */
export const ReharmSandbox: React.FC = () => {
  const { open, chord, close } = useReharmStore();
  const openChord = chord?.chord ?? null;
  const toneRef = useRef<Tone | null>(null);
  const synthRef = useRef<InstanceType<Tone["PolySynth"]> | null>(null);
  const [, setReady] = useState(false);

  // Lazy-init Tone — has to be inside a user gesture (open is one).
  useEffect(() => {
    if (!open || !openChord) return;
    let cancelled = false;
    (async () => {
      const tone = await import("tone");
      if (cancelled) return;
      toneRef.current = tone;
      if (!synthRef.current) {
        synthRef.current = new tone.PolySynth(tone.Synth, {
          envelope: { attack: 0.02, decay: 0.2, sustain: 0.5, release: 0.7 },
        }).toDestination();
      }
      setReady(true);
    })();
    return () => { cancelled = true; };
  }, [open, openChord]);

  // Dispose the Tone synth on final unmount (it's reused across opens, so it's
  // only torn down when the component itself goes away).
  useEffect(() => {
    return () => {
      try {
        (synthRef.current as { dispose?: () => void } | null)?.dispose?.();
        synthRef.current = null;
      } catch { /* */ }
    };
  }, []);

  const swaps = useMemo(() => {
    if (!openChord) return [];
    return computeSwaps(openChord);
  }, [openChord]);

  if (!open || !openChord) return null;

  const playChord = async (chordName: string) => {
    const tone = toneRef.current;
    const synth = synthRef.current;
    if (!tone || !synth) return;
    await tone.start();
    const notes = chordToMidi(chordName);
    if (!notes.length) return;
    synth.triggerAttackRelease(notes, "2n");
  };

  return (
    <div
      className="fixed inset-0 z-[100] bg-background/80 backdrop-blur-sm flex items-center justify-center p-6"
      onClick={close}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="glass-panel rounded-xl max-w-lg w-full p-6 border border-primary/20"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-headline text-xl text-on-surface">
            What if <span className="primary-gradient-text">{openChord}</span> was…?
          </h3>
          <button
            className="text-on-surface-variant hover:text-on-surface"
            onClick={close}
            aria-label="Close"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <ul className="flex flex-col gap-2">
          {swaps.map((s) => (
            <li
              key={s.name}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-container-high border border-white/5"
            >
              <div className="flex-grow">
                <div className="font-headline text-lg text-on-surface">
                  → <span className="primary-gradient-text">{s.result}</span>
                </div>
                <div className="text-xs text-on-surface-variant">
                  <span className="font-semibold text-on-surface mr-1">{s.name}.</span>
                  {s.blurb}
                </div>
              </div>
              <button
                className="px-3 py-2 rounded-full glass-panel hover:border-primary/30 text-primary"
                onClick={() => playChord(s.result)}
                title={`Preview ${s.result}`}
              >
                <span className="material-symbols-outlined text-lg">volume_up</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------
// Swap math — kept inline since it's tiny + only used here.
// ---------------------------------------------------------------------

interface Swap {
  name: string;
  result: string;
  blurb: string;
}

function computeSwaps(chord: string): Swap[] {
  const { root, quality } = parse(chord);
  const isMinor = /m(?![aA])/.test(quality) && !/dim|aug/.test(quality);
  const isMajor = !isMinor && !/dim|aug/.test(quality);

  const relMinor = `${transposeChord(root, -3)}m`;
  const relMajor = transposeChord(root, 3);
  const tritone = `${transposeChord(root, 6)}7`;
  const secondary = `${transposeChord(root, 7)}7`;
  const borrowed = isMajor ? `${root}m` : root;

  return [
    {
      name: "Relative " + (isMinor ? "major" : "minor"),
      result: isMinor ? relMajor : relMinor,
      blurb: "Same key signature, opposite tonality. Softens or warms the same scale.",
    },
    {
      name: "Tritone substitution",
      result: tritone,
      blurb: "V7 → bII7. Shares the same tritone, adds chromatic descent and bluesy color.",
    },
    {
      name: "Secondary dominant",
      result: secondary,
      blurb: "Borrows the dominant of the next chord — strengthens the pull forward.",
    },
    {
      name: "Modal interchange",
      result: borrowed,
      blurb: "Borrow from the parallel mode. Major → minor (or vice versa) for unexpected colour.",
    },
  ];
}

function parse(chord: string): { root: string; quality: string } {
  const m = chord.match(/^([A-G][b#]?)(.*)$/);
  if (!m) return { root: "C", quality: "" };
  return { root: m[1], quality: m[2] };
}

const _NOTE_MIDI: Record<string, number> = {
  C: 60, "C#": 61, Db: 61, D: 62, "D#": 63, Eb: 63, E: 64, F: 65,
  "F#": 66, Gb: 66, G: 67, "G#": 68, Ab: 68, A: 69, "A#": 70, Bb: 70, B: 71,
};

function qualityIntervals(quality: string): number[] {
  // Order matters: specific qualities first so e.g. "dim7" never reads as "m7".
  if (/dim7/.test(quality)) return [0, 3, 6, 9];
  if (/dim|°|o(?![a-z])/.test(quality)) return [0, 3, 6];
  if (/aug|\+/.test(quality)) return [0, 4, 8];
  if (/sus2/.test(quality)) return [0, 2, 7];
  if (/sus4|sus/.test(quality)) return [0, 5, 7];
  const isMinor = /m(?![aA])/.test(quality);
  if (/maj7/.test(quality)) return [0, 4, 7, 11];
  if (/7/.test(quality)) return isMinor ? [0, 3, 7, 10] : [0, 4, 7, 10];
  return isMinor ? [0, 3, 7] : [0, 4, 7];
}

function chordToMidi(chord: string): string[] {
  const { root, quality } = parse(chord);
  const base = _NOTE_MIDI[root];
  if (base == null) return [];
  return qualityIntervals(quality).map((s) => midiToNote(base + s));
}

const _PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function midiToNote(m: number): string {
  const oct = Math.floor(m / 12) - 1;
  return `${_PITCH_NAMES[m % 12]}${oct}`;
}
