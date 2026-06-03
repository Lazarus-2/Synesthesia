"use client";

import React, { useEffect, useRef } from "react";
import { usePlayerStore } from "../../store/usePlayerStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePracticeStore } from "../../store/usePracticeStore";

export const BottomBar: React.FC = () => {
  const { isPlaying, setIsPlaying, wavesurfer, currentTime } = usePlayerStore();
  const { analysis } = useAnalysisStore();
  const {
    practiceMode, togglePracticeMode,
    loopStart, loopEnd, setLoopStart, setLoopEnd, clearLoop,
    playbackRate, setPlaybackRate,
    metronomeOn, toggleMetronome, tapTempoBPM, recordTap,
  } = usePracticeStore();

  const pitch = 0; // Pitch shifting deferred — see usePracticeStore doc.

  // Loop enforcement (Plan 3 A3/B1): when both markers are set and we cross
  // ``loopEnd`` during playback, seek back to ``loopStart``.
  useEffect(() => {
    if (!practiceMode || loopStart === null || loopEnd === null) return;
    if (!wavesurfer) return;
    if (currentTime >= loopEnd) {
      const duration = wavesurfer.getDuration();
      if (duration > 0) wavesurfer.seekTo(loopStart / duration);
    }
  }, [practiceMode, loopStart, loopEnd, wavesurfer, currentTime]);

  // Metronome (Plan 3 B6): tick at the song's BPM (or detected tap tempo)
  // whenever ``metronomeOn`` is true. Uses Web Audio so no Tone.js
  // dependency for this minimal version.
  const audioCtxRef = useRef<AudioContext | null>(null);
  useEffect(() => {
    if (!metronomeOn) return;
    const bpm = tapTempoBPM ?? Math.round(analysis?.tempo ?? 120);
    const intervalMs = (60_000 / bpm) / playbackRate;
    if (!audioCtxRef.current) {
      const w = window as unknown as {
        AudioContext?: typeof AudioContext;
        webkitAudioContext?: typeof AudioContext;
      };
      const Ctor = w.AudioContext ?? w.webkitAudioContext;
      if (Ctor) audioCtxRef.current = new Ctor();
    }
    const ctx = audioCtxRef.current;
    if (!ctx) return;
    const id = window.setInterval(() => {
      const t = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 1000;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.4, t + 0.001);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t); osc.stop(t + 0.06);
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [metronomeOn, tapTempoBPM, analysis?.tempo, playbackRate]);

  if (!analysis) return null;

  const handleSpeed = () => {
    const speeds = [0.5, 0.75, 1.0, 1.25, 1.5];
    const idx = speeds.indexOf(playbackRate);
    const next = speeds[(idx + 1) % speeds.length];
    setPlaybackRate(next);
    if (wavesurfer) wavesurfer.setPlaybackRate(next);
  };

  const handleSkipBack = () => {
    if (wavesurfer) {
      const t = Math.max(0, wavesurfer.getCurrentTime() - 5);
      wavesurfer.seekTo(t / wavesurfer.getDuration());
    }
  };

  const handleSkipForward = () => {
    if (wavesurfer) {
      const dur = wavesurfer.getDuration();
      const t = Math.min(dur, wavesurfer.getCurrentTime() + 5);
      wavesurfer.seekTo(t / dur);
    }
  };

  // Loop markers: A sets start at currentTime, B sets end at currentTime.
  const setMarkerA = () => setLoopStart(wavesurfer?.getCurrentTime() ?? null);
  const setMarkerB = () => setLoopEnd(wavesurfer?.getCurrentTime() ?? null);

  return (
    <footer className="fixed bottom-0 left-0 right-0 z-50 h-16 bg-surface-container-lowest border-t border-white/10 backdrop-blur-xl flex items-center justify-between px-6 lg:px-16">
      {/* Left Controls */}
      <div className="flex items-center gap-6">
        <button
          className="flex items-center gap-2 hover:text-primary transition-colors"
          onClick={handleSpeed}
          title="Cycle playback speed (note: changes pitch — pitch-preserving stretch is deferred)"
        >
          <span className="material-symbols-outlined text-lg text-on-surface-variant">speed</span>
          <span className="text-sm font-semibold text-on-surface tabular-nums">{playbackRate}x</span>
        </button>

        <button
          className="flex items-center gap-2 opacity-50 cursor-not-allowed"
          disabled
          title="Pitch shifting requires a time-stretch library (deferred)"
        >
          <span className="material-symbols-outlined text-lg text-on-surface-variant">tune</span>
          <span className="text-sm font-semibold text-on-surface tabular-nums">
            {pitch >= 0 ? `+${pitch}` : pitch} st
          </span>
        </button>

        {/* Practice-mode loop markers */}
        {practiceMode && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-primary-container/10 border border-primary-container/30">
            <button
              onClick={setMarkerA}
              className="text-xs font-semibold text-primary hover:text-on-surface"
              title="Set loop start at current time"
            >
              {loopStart !== null ? `A ${loopStart.toFixed(1)}s` : "Set A"}
            </button>
            <span className="text-xs text-on-surface-variant">→</span>
            <button
              onClick={setMarkerB}
              className="text-xs font-semibold text-primary hover:text-on-surface"
              title="Set loop end at current time"
            >
              {loopEnd !== null ? `B ${loopEnd.toFixed(1)}s` : "Set B"}
            </button>
            {(loopStart !== null || loopEnd !== null) && (
              <button
                onClick={clearLoop}
                className="text-xs text-on-surface-variant hover:text-error ml-1"
                title="Clear loop region"
              >
                ✕
              </button>
            )}
          </div>
        )}
      </div>

      {/* Center Controls */}
      <div className="flex items-center gap-4">
        <button className="hover:text-primary transition-colors" onClick={handleSkipBack}>
          <span className="material-symbols-outlined text-2xl text-on-surface-variant">fast_rewind</span>
        </button>

        <button
          className="w-12 h-12 rounded-full bg-gradient-to-br from-primary-container to-tertiary-container flex items-center justify-center shadow-[0_2px_12px_rgba(255,181,71,0.3)] hover:scale-105 active:scale-95 transition-transform"
          onClick={() => setIsPlaying(!isPlaying)}
        >
          <span
            className="material-symbols-outlined text-on-primary-container text-2xl"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            {isPlaying ? "pause" : "play_arrow"}
          </span>
        </button>

        <button className="hover:text-primary transition-colors" onClick={handleSkipForward}>
          <span className="material-symbols-outlined text-2xl text-on-surface-variant">fast_forward</span>
        </button>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-4">
        {/* Metronome + tap tempo */}
        <button
          className={`flex items-center gap-2 px-3 py-2 rounded-full border transition-all text-sm font-medium ${
            metronomeOn
              ? "border-secondary-container bg-secondary-container/10 text-on-secondary-container"
              : "border-white/10 text-on-surface-variant hover:text-primary"
          }`}
          onClick={toggleMetronome}
          title={metronomeOn ? "Stop metronome" : "Start metronome"}
        >
          <span className="material-symbols-outlined text-lg">straighten</span>
          {tapTempoBPM ?? Math.round(analysis.tempo)} BPM
        </button>
        <button
          className="px-2 py-2 rounded-full glass-panel text-xs hover:border-primary/30"
          onClick={recordTap}
          title="Tap tempo — tap 2+ times to detect BPM"
        >
          Tap
        </button>

        <button
          className={`flex items-center gap-2 px-4 py-2 rounded-full border transition-all text-sm font-medium ${
            practiceMode
              ? "border-primary-container bg-primary-container/10 text-primary"
              : "border-white/10 text-on-surface-variant hover:text-primary"
          }`}
          onClick={togglePracticeMode}
        >
          <span className="material-symbols-outlined text-lg">loop</span>
          Practice Mode
        </button>
      </div>
    </footer>
  );
};
