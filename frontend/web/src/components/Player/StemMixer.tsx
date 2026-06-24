"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { API_V1 } from "../../lib/apiClient";
import { usePlayAlongStore } from "../../store/usePlayAlongStore";
import { usePlayerStore } from "../../store/usePlayerStore";
import { PlayAlongPresets } from "./PlayAlongPresets";

interface Stem {
  id: "vocals" | "drums" | "bass" | "other";
  label: string;
  icon: string;
  color: string;
}

const STEMS: Stem[] = [
  { id: "vocals", label: "Vocals", icon: "mic", color: "#c4abff" },
  { id: "drums", label: "Drums", icon: "album", color: "#ffb547" },
  { id: "bass", label: "Bass", icon: "speaker", color: "#ffafac" },
  { id: "other", label: "Melodics", icon: "piano", color: "#ffd9ab" },
];

export const StemMixer: React.FC = () => {
  const { analysis, jobId } = useAnalysisStore();
  // Memoize so the availableStems useMemo isn't recomputed every render
  // (eslint-react-hooks/exhaustive-deps).
  const stems = useMemo(
    () => (analysis as { stems?: Record<string, string> } | null)?.stems ?? {},
    [analysis],
  );

  const [volumes, setVolumes] = useState<Record<string, number>>({
    vocals: 80, drums: 100, bass: 70, other: 90,
  });
  const [muted, setMuted] = useState<Record<string, boolean>>({});
  // Solo: when any stem is soloed, only soloed stems are audible (mute is
  // ignored while soloing). The classic mixer behaviour.
  const [soloed, setSoloed] = useState<Record<string, boolean>>({});

  const playAlongMuted = usePlayAlongStore((s) => (s.engaged ? s.mutedStem : null));
  const playAlongEngaged = usePlayAlongStore((s) => s.engaged);

  // Lazy WebAudio routing — one HTMLAudioElement + GainNode per stem so
  // the user can blend without re-fetching. Created the first time a stem
  // has both a URL and isn't muted; teardown on unmount.
  const audioElementsRef = useRef<Record<string, HTMLAudioElement | null>>({});
  const gainNodesRef = useRef<Record<string, GainNode | null>>({});
  const ctxRef = useRef<AudioContext | null>(null);

  const availableStems = useMemo(
    () => STEMS.filter((s) => Boolean(stems[s.id])),
    [stems],
  );

  // Sync gain to slider values + mute/solo state.
  useEffect(() => {
    const anySolo = Object.values(soloed).some(Boolean);
    for (const s of availableStems) {
      const gain = gainNodesRef.current[s.id];
      if (!gain) continue;
      if (playAlongMuted === s.id) {
        gain.gain.value = 0; // Play-Along: user's instrument is silenced
        continue;
      }
      const audible = anySolo ? Boolean(soloed[s.id]) : !muted[s.id];
      gain.gain.value = audible ? volumes[s.id] / 100 : 0;
    }
  }, [volumes, muted, soloed, availableStems, playAlongMuted]);

  // Build the audio graph when stems first arrive.
  useEffect(() => {
    if (availableStems.length === 0 || !jobId) return;
    if (!ctxRef.current) {
      const w = window as unknown as {
        AudioContext?: typeof AudioContext;
        webkitAudioContext?: typeof AudioContext;
      };
      const Ctor = w.AudioContext ?? w.webkitAudioContext;
      if (Ctor) ctxRef.current = new Ctor();
    }
    const ctx = ctxRef.current;
    if (!ctx) return;

    for (const s of availableStems) {
      if (audioElementsRef.current[s.id]) continue;
      const el = new Audio(`${API_V1}/stems/${encodeURIComponent(jobId)}/${s.id}`);
      el.crossOrigin = "anonymous";
      el.preload = "auto";
      const source = ctx.createMediaElementSource(el);
      const gain = ctx.createGain();
      gain.gain.value = muted[s.id] ? 0 : volumes[s.id] / 100;
      source.connect(gain).connect(ctx.destination);
      audioElementsRef.current[s.id] = el;
      gainNodesRef.current[s.id] = gain;
    }
    // Snapshot the refs before cleanup runs — the original ref objects may
    // mutate between effect setup and teardown (lint: exhaustive-deps).
    const elementsSnapshot = audioElementsRef.current;
    const gainsSnapshot = gainNodesRef.current;
    const ctxToClose = ctxRef.current;
    return () => {
      // Full teardown: this component unmounts on every tab switch (tab content
      // is keyed by activeTab), so pausing alone would leak an AudioContext +
      // MediaElementSource/Gain nodes each time. Release them and clear the refs
      // so a remount rebuilds a fresh graph.
      for (const id of Object.keys(elementsSnapshot)) {
        const el = elementsSnapshot[id];
        if (el) {
          try { el.pause(); el.src = ""; el.load(); } catch { /* */ }
        }
      }
      for (const id of Object.keys(gainsSnapshot)) {
        try { gainsSnapshot[id]?.disconnect(); } catch { /* */ }
      }
      try { void ctxToClose?.close(); } catch { /* */ }
      ctxRef.current = null;
      audioElementsRef.current = {};
      gainNodesRef.current = {};
    };
    // We intentionally exclude volumes/muted from deps — the first effect
    // syncs them on every change without rebuilding the graph.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availableStems, jobId]);

  const setVolume = (id: string, vol: number) =>
    setVolumes((prev) => ({ ...prev, [id]: vol }));
  const toggleMute = (id: string) =>
    setMuted((prev) => ({ ...prev, [id]: !prev[id] }));
  const toggleSolo = (id: string) =>
    setSoloed((prev) => ({ ...prev, [id]: !prev[id] }));

  const allPlay = useCallback(() => {
    // The stem AudioContext starts suspended (no user gesture in the stem
    // graph itself). Resume it so the stems are actually audible — mirrors the
    // Tone.start() resume the main transport does on its play button.
    void ctxRef.current?.resume().catch(() => undefined);
    for (const el of Object.values(audioElementsRef.current)) {
      el?.play().catch(() => undefined);
    }
  }, []);
  const allPause = useCallback(() => {
    for (const el of Object.values(audioElementsRef.current)) el?.pause();
  }, []);

  // ── Play-Along: single-transport sync ──────────────────────────────────
  // When Play-Along is engaged the stem mixer becomes the SOLE audible source:
  // the main WaveSurfer track is muted and the stems follow the main player's
  // play/pause/seek. Without this, the StemMixer's 4 <audio> elements and the
  // main track are two independent transports → doubled audio + drift.
  // All three effects below are gated on `playAlongEngaged && stems available`;
  // when disengaged the manual Play/Pause buttons remain the only driver.

  // Authoritative "main track time" — prefer the live wavesurfer clock, fall
  // back to the throttled store value.
  const mainTime = useCallback((): number => {
    const ws = usePlayerStore.getState().wavesurfer as unknown as
      | { getCurrentTime?: () => number }
      | null;
    const t = ws?.getCurrentTime?.();
    return typeof t === "number" && Number.isFinite(t)
      ? t
      : usePlayerStore.getState().currentTime;
  }, []);

  // (1) Mute the main media element while engaged; restore exactly on cleanup.
  useEffect(() => {
    if (!playAlongEngaged || availableStems.length === 0) return;
    const ws = usePlayerStore.getState().wavesurfer as unknown as
      | { getMediaElement?: () => HTMLMediaElement; setMuted?: (m: boolean) => void }
      | null;
    const media = ws?.getMediaElement?.();
    if (media) {
      const prevMuted = media.muted;
      media.muted = true;
      return () => {
        media.muted = prevMuted;
      };
    }
    // Fallback path: no media element exposed → mute via the store volume and
    // restore the prior volume on disengage.
    const prevVolume = usePlayerStore.getState().volume;
    if (ws?.setMuted) {
      ws.setMuted(true);
      return () => {
        ws.setMuted?.(false);
        usePlayerStore.getState().setVolume(prevVolume);
      };
    }
    usePlayerStore.getState().setVolume(0);
    return () => {
      usePlayerStore.getState().setVolume(prevVolume);
    };
  }, [playAlongEngaged, availableStems.length]);

  // (2) Stems follow the main transport's play/pause. Subscribe to isPlaying
  // (transient subscription so this effect doesn't re-render the component).
  useEffect(() => {
    if (!playAlongEngaged || availableStems.length === 0) return;
    const apply = (playing: boolean) => {
      if (playing) {
        // Align before starting so the stems begin from the main track's spot.
        const t = mainTime();
        for (const el of Object.values(audioElementsRef.current)) {
          if (el && Number.isFinite(t)) {
            try { el.currentTime = t; } catch { /* not seekable yet */ }
          }
        }
        allPlay();
      } else {
        allPause();
      }
    };
    // Apply current state immediately, then on every change.
    apply(usePlayerStore.getState().isPlaying);
    const unsub = usePlayerStore.subscribe((state, prev) => {
      if (state.isPlaying !== prev.isPlaying) apply(state.isPlaying);
    });
    return () => {
      unsub();
      allPause();
    };
  }, [playAlongEngaged, availableStems.length, allPlay, allPause, mainTime]);

  // (3) Stems follow the clock / seeks. currentTime is throttled to ~10/sec;
  // only re-align a stem when it has drifted from the main track by >0.3s
  // (i.e. a seek), so we don't fight normal playback drift every tick.
  useEffect(() => {
    if (!playAlongEngaged || availableStems.length === 0) return;
    const realign = () => {
      const t = mainTime();
      if (!Number.isFinite(t)) return;
      for (const el of Object.values(audioElementsRef.current)) {
        if (el && Math.abs(el.currentTime - t) > 0.3) {
          try { el.currentTime = t; } catch { /* not seekable yet */ }
        }
      }
    };
    realign(); // align on engage
    const unsub = usePlayerStore.subscribe((state, prev) => {
      if (state.currentTime !== prev.currentTime) realign();
    });
    return unsub;
  }, [playAlongEngaged, availableStems.length, mainTime]);

  return (
    <div className="flex flex-col gap-6 p-6 overflow-y-auto hide-scrollbar flex-grow">
      <div className="flex justify-between items-baseline">
        <h2 className="font-headline text-2xl font-medium text-white">Stems</h2>
        {availableStems.length > 0 && (
          <div className="flex gap-2">
            <button
              onClick={allPlay}
              className="px-3 py-1 text-xs rounded-full glass-panel hover:border-primary/30"
            >
              Play
            </button>
            <button
              onClick={allPause}
              className="px-3 py-1 text-xs rounded-full glass-panel hover:border-primary/30"
            >
              Pause
            </button>
          </div>
        )}
      </div>

      <PlayAlongPresets availableStems={availableStems.map((s) => s.id)} />

      <p className="text-sm text-on-surface-variant -mt-2">
        {availableStems.length === 0
          ? "No isolated stems for this track. Stem separation runs the Demucs model on the backend — it isn't installed in this deployment, so vocals/drums/bass/other couldn't be split out."
          : "Adjust individual instrument levels. Stems are streamed independently from the backend."}
      </p>

      <div className="flex flex-col gap-4">
        {STEMS.map((stem) => {
          const isAvailable = Boolean(stems[stem.id]);
          const anySolo = Object.values(soloed).some(Boolean);
          const silencedBySolo = anySolo && !soloed[stem.id];
          const vol = muted[stem.id] || silencedBySolo ? 0 : volumes[stem.id];
          return (
            <div
              key={stem.id}
              className={`glass-panel rounded-xl p-4 flex items-center gap-4 ${
                isAvailable ? "" : "opacity-40"
              } ${silencedBySolo ? "opacity-50" : ""}`}
            >
              <button
                className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 transition-all ${
                  muted[stem.id] || !isAvailable ? "bg-white/5" : "bg-white/10"
                }`}
                onClick={() => isAvailable && toggleMute(stem.id)}
                disabled={!isAvailable}
                title={!isAvailable ? "Not separated yet" : muted[stem.id] ? "Unmute" : "Mute"}
              >
                <span
                  className="material-symbols-outlined text-xl"
                  style={{ color: muted[stem.id] || !isAvailable ? "#9e8e7c" : stem.color }}
                >
                  {muted[stem.id] || !isAvailable ? "volume_off" : stem.icon}
                </span>
              </button>

              <div className="flex-grow">
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-sm font-medium text-on-surface">{stem.label}</span>
                  <span className="text-xs text-on-surface-variant tabular-nums">{vol}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={vol}
                  onChange={(e) => setVolume(stem.id, Number(e.target.value))}
                  className="stem-slider w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-full"
                  disabled={muted[stem.id] || !isAvailable}
                  aria-label={`${stem.label} volume`}
                  aria-valuetext={`${vol}%`}
                />
              </div>

              {/* Solo toggle */}
              <button
                onClick={() => isAvailable && toggleSolo(stem.id)}
                disabled={!isAvailable}
                aria-pressed={Boolean(soloed[stem.id])}
                title={soloed[stem.id] ? "Unsolo" : "Solo"}
                className={`w-9 h-9 rounded-lg text-xs font-bold shrink-0 transition-all ${
                  soloed[stem.id]
                    ? "bg-primary-container text-on-primary-container shadow-[0_0_10px_rgba(255,181,71,0.35)]"
                    : "bg-white/5 text-on-surface-variant hover:bg-white/10"
                } disabled:opacity-40`}
              >
                S
              </button>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-outline-variant text-center mt-4 italic">
        Stem separation powered by Demucs. Processing may take up to 60 seconds.
      </p>
    </div>
  );
};
