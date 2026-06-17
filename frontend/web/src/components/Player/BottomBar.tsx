"use client";

import React, { useEffect, useRef } from "react";
import { usePlayerStore } from "../../store/usePlayerStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePracticeStore } from "../../store/usePracticeStore";

export const BottomBar: React.FC = () => {
  const { isPlaying, setIsPlaying, wavesurfer } = usePlayerStore();
  const { analysis } = useAnalysisStore();
  const {
    practiceMode, togglePracticeMode,
    loopStart, loopEnd, setLoopStart, setLoopEnd, clearLoop,
    playbackRate, setPlaybackRate,
    pitchLock, togglePitchLock,
    transpose, setTranspose, bumpTranspose,
    metronomeOn, toggleMetronome, tapTempoBPM, recordTap,
  } = usePracticeStore();

  // Accurate A/B loop enforcement. Subscribe to WaveSurfer's OWN audioprocess
  // (fires ~60/sec, unthrottled) rather than the store's currentTime, which is
  // throttled to ~10/sec and would overshoot loopEnd by up to 100ms before
  // seeking back — an audible stutter past the loop point.
  useEffect(() => {
    if (!wavesurfer || !practiceMode || loopStart === null || loopEnd === null || loopEnd <= loopStart) {
      return;
    }
    const ws = wavesurfer;
    const onProcess = () => {
      if (ws.getCurrentTime() >= loopEnd) {
        const duration = ws.getDuration();
        if (duration > 0) ws.seekTo(loopStart / duration);
      }
    };
    // WaveSurfer v7 .on() returns an unsubscribe function.
    const unsub = ws.on("audioprocess", onProcess);
    return () => {
      try {
        (unsub as unknown as () => void)?.();
      } catch {
        /* older builds: no-op */
      }
    };
  }, [wavesurfer, practiceMode, loopStart, loopEnd]);

  // Metronome — a Web Audio lookahead scheduler (the canonical "two clocks"
  // pattern: a coarse setInterval wakes up and schedules any clicks due within
  // a short lookahead window at sample-accurate ctx.currentTime). This avoids
  // the drift/jitter of scheduling each click straight off setInterval. The
  // downbeat (first beat of each bar, from the time signature) is accented.
  const audioCtxRef = useRef<AudioContext | null>(null);
  useEffect(() => {
    if (!metronomeOn) return;
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
    void ctx.resume(); // toggle is a user gesture — resume if suspended

    const bpm = tapTempoBPM ?? Math.round(analysis?.tempo ?? 120);
    // Slower playback => clicks further apart, so the metronome tracks the
    // (slowed) audio the user is practising to.
    const secondsPerBeat = 60 / bpm / playbackRate;
    const beatsPerBar = parseInt((analysis?.time_signature || "4/4").split("/")[0], 10) || 4;
    const lookahead = 0.1; // schedule clicks up to 100ms ahead

    let nextNoteTime = ctx.currentTime + 0.08;
    let beatInBar = 0;

    const click = (time: number, accent: boolean) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = accent ? 1600 : 1000;
      gain.gain.setValueAtTime(0.0001, time);
      gain.gain.exponentialRampToValueAtTime(accent ? 0.5 : 0.3, time + 0.001);
      gain.gain.exponentialRampToValueAtTime(0.0001, time + 0.05);
      osc.connect(gain).connect(ctx.destination);
      osc.start(time);
      osc.stop(time + 0.06);
    };

    const timer = window.setInterval(() => {
      while (nextNoteTime < ctx.currentTime + lookahead) {
        click(nextNoteTime, beatInBar === 0);
        nextNoteTime += secondsPerBeat;
        beatInBar = (beatInBar + 1) % beatsPerBar;
      }
    }, 25);
    return () => window.clearInterval(timer);
  }, [metronomeOn, tapTempoBPM, analysis?.tempo, analysis?.time_signature, playbackRate]);

  if (!analysis) return null;

  const handleSpeed = () => {
    const speeds = [0.5, 0.75, 1.0, 1.25, 1.5];
    const idx = speeds.indexOf(playbackRate);
    const next = speeds[(idx + 1) % speeds.length];
    setPlaybackRate(next);
    // When pitchLock is ON the SoundTouch worklet in AudioEngine
    // handles the tempo change with no pitch shift — leave the
    // underlying <audio> at rate=1. When OFF, wavesurfer.setPlaybackRate
    // updates ``audio.playbackRate`` directly (pitch shifts with tempo,
    // chipmunk effect — the classic playback-speed behaviour).
    if (wavesurfer) {
      wavesurfer.setPlaybackRate(pitchLock ? 1.0 : next);
    }
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

  // Keyboard shortcuts: space=play/pause, arrows=seek, [/]=loop markers,
  // +/-=transpose, ,/. = playback rate. Skipped when focus is in an input.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable) return;
      if (e.key === " ") {
        e.preventDefault();
        setIsPlaying(!isPlaying);
        return;
      }
      if (e.key === "ArrowLeft") { handleSkipBack(); return; }
      if (e.key === "ArrowRight") { handleSkipForward(); return; }
      if (practiceMode && e.key === "[") { setMarkerA(); return; }
      if (practiceMode && e.key === "]") { setMarkerB(); return; }
      if (e.key === "+" || e.key === "=") { bumpTranspose(1); return; }
      if (e.key === "-" || e.key === "_") { bumpTranspose(-1); return; }
      if (e.key === ",") {
        const next = Math.max(0.5, Number((playbackRate - 0.05).toFixed(2)));
        setPlaybackRate(next);
        // Same logic as handleSpeed: only mirror onto wavesurfer when
        // pitchLock is off (SoundTouch handles rate when on).
        if (wavesurfer) wavesurfer.setPlaybackRate(pitchLock ? 1.0 : next);
        return;
      }
      if (e.key === ".") {
        const next = Math.min(1.5, Number((playbackRate + 0.05).toFixed(2)));
        setPlaybackRate(next);
        if (wavesurfer) wavesurfer.setPlaybackRate(pitchLock ? 1.0 : next);
        return;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaying, practiceMode, playbackRate, pitchLock, wavesurfer, transpose]);

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

        {/* Pitch-lock toggle — when on, playback-rate keeps pitch via SoundTouch Worklet.
            Plumbing the audio chain through the Worklet ships in a follow-up; the toggle
            controls whether the existing wavesurfer.setPlaybackRate call fires (pitch shifts)
            or not (pitch lock means user only changes perceived tempo via slowdown). */}
        <button
          className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
            pitchLock
              ? "bg-secondary-container/20 text-on-secondary-container border border-secondary-container/40"
              : "text-on-surface-variant hover:text-primary"
          }`}
          onClick={togglePitchLock}
          title={pitchLock ? "Pitch lock ON — rate change preserves pitch" : "Pitch lock OFF — rate change shifts pitch"}
        >
          <span className="material-symbols-outlined text-[16px]">{pitchLock ? "lock" : "lock_open"}</span>
          PITCH
        </button>

        {/* Transpose ± stepper — uses @tonaljs/tonal for chord labels (ChordTimeline reads
            ``transpose`` from the store and shifts each label) and (next commit) Tone.PitchShift
            for the audio. */}
        <div className="flex items-center gap-0.5 px-1 py-0.5 rounded-md glass-panel">
          <button
            className="px-1.5 py-0.5 text-on-surface-variant hover:text-primary text-sm font-semibold"
            onClick={() => bumpTranspose(-1)}
            disabled={transpose <= -5}
            title="Transpose down 1 semitone"
          >
            −
          </button>
          <button
            className="text-xs font-semibold text-on-surface tabular-nums px-1 hover:text-primary"
            onClick={() => setTranspose(0)}
            title="Reset transpose to 0"
          >
            {transpose >= 0 ? `+${transpose}` : transpose} st
          </button>
          <button
            className="px-1.5 py-0.5 text-on-surface-variant hover:text-primary text-sm font-semibold"
            onClick={() => bumpTranspose(1)}
            disabled={transpose >= 5}
            title="Transpose up 1 semitone"
          >
            +
          </button>
        </div>

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
