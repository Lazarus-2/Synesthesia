"use client";

import React, { useState } from "react";
import { usePlayerStore } from "../../store/usePlayerStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";

export const BottomBar: React.FC = () => {
  const { isPlaying, setIsPlaying, wavesurfer } = usePlayerStore();
  const { analysis } = useAnalysisStore();
  const [speed, setSpeed] = useState(1.0);
  const [pitch, setPitch] = useState(0);
  const [looping, setLooping] = useState(false);

  if (!analysis) return null;

  const handleSpeed = () => {
    const speeds = [0.5, 0.75, 1.0, 1.25, 1.5];
    const idx = speeds.indexOf(speed);
    const next = speeds[(idx + 1) % speeds.length];
    setSpeed(next);
    if (wavesurfer) wavesurfer.setPlaybackRate(next);
  };

  const handlePitch = () => {
    const pitches = [-2, -1, 0, 1, 2];
    const idx = pitches.indexOf(pitch);
    const next = pitches[(idx + 1) % pitches.length];
    setPitch(next);
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

  return (
    <footer className="fixed bottom-0 left-0 right-0 z-50 h-16 bg-surface-container-lowest border-t border-white/10 backdrop-blur-xl flex items-center justify-between px-6 lg:px-16">
      {/* Left Controls */}
      <div className="flex items-center gap-6">
        <button
          className="flex items-center gap-2 hover:text-primary transition-colors"
          onClick={handleSpeed}
        >
          <span className="material-symbols-outlined text-lg text-on-surface-variant">speed</span>
          <span className="text-sm font-semibold text-on-surface tabular-nums">{speed}x</span>
        </button>

        <button
          className="flex items-center gap-2 hover:text-primary transition-colors"
          onClick={handlePitch}
        >
          <span className="material-symbols-outlined text-lg text-on-surface-variant">tune</span>
          <span className="text-sm font-semibold text-on-surface tabular-nums">
            {pitch >= 0 ? `+${pitch}` : pitch} st
          </span>
        </button>
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
        <button
          className={`flex items-center gap-2 px-4 py-2 rounded-full border transition-all text-sm font-medium ${
            looping
              ? "border-primary-container bg-primary-container/10 text-primary"
              : "border-white/10 text-on-surface-variant hover:text-primary"
          }`}
          onClick={() => setLooping(!looping)}
        >
          <span className="material-symbols-outlined text-lg">loop</span>
          Loop
        </button>
        <button className="flex items-center gap-2 px-4 py-2 rounded-full glass-panel hover:border-primary/30 transition-all text-sm font-medium text-on-surface">
          <span className="material-symbols-outlined text-lg text-primary-container" style={{ fontVariationSettings: "'FILL' 1" }}>fiber_manual_record</span>
          Practice Mode
        </button>
      </div>
    </footer>
  );
};
