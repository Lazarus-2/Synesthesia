"use client";

import React, { useEffect, useRef } from "react";
import type WaveSurfer from "wavesurfer.js";
import { usePlayerStore } from "../../store/usePlayerStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { useRehearseStore } from "../../store/useRehearseStore";
import { usePracticeStore } from "../../store/usePracticeStore";
import { formatTime } from "../../lib/format";

/** The elapsed / remaining time labels. Isolated so ONLY this tiny node
 *  re-renders on each currentTime tick (~10/sec) — the parent WaveformPlayer
 *  (waveform + section ribbon) doesn't subscribe to currentTime and so stays
 *  put while playing. */
const TransportTime: React.FC<{ side: "elapsed" | "remaining" }> = ({ side }) => {
  const currentTime = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);
  if (side === "elapsed") {
    return (
      <span className="text-xs font-medium text-primary-container tabular-nums">
        {formatTime(currentTime)}
      </span>
    );
  }
  const remaining = duration - currentTime;
  return (
    <span className="text-xs font-medium text-on-surface-variant tabular-nums">
      -{formatTime(remaining > 0 ? remaining : 0)}
    </span>
  );
};

export const WaveformPlayer: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  // Field selectors (no currentTime) so the player body + section ribbon don't
  // re-render 10×/sec; the time labels live in <TransportTime> which does.
  const isPlaying = usePlayerStore((s) => s.isPlaying);
  const setIsPlaying = usePlayerStore((s) => s.setIsPlaying);
  const duration = usePlayerStore((s) => s.duration);
  const setCurrentTime = usePlayerStore((s) => s.setCurrentTime);
  const setDuration = usePlayerStore((s) => s.setDuration);
  const audioFileUrl = usePlayerStore((s) => s.audioFileUrl);
  const setWavesurfer = usePlayerStore((s) => s.setWavesurfer);
  const { analysis } = useAnalysisStore();
  const { practiceMode, loopStart, loopEnd, setLoopStart, setLoopEnd } = usePracticeStore();
  const wsRef = useRef<WaveSurfer | null>(null);

  useEffect(() => {
    if (!containerRef.current || !audioFileUrl) return;

    // Holder for the cleanup closure — assigned after the async create.
    let cleanup: (() => void) | null = null;

    (async () => {
      const WaveSurferCtor = (await import("wavesurfer.js")).default;
      const ws: WaveSurfer = WaveSurferCtor.create({
        container: containerRef.current!,
        waveColor: "rgba(255, 181, 71, 0.4)",
        progressColor: "#ffb547",
        cursorColor: "#c4abff",
        cursorWidth: 2,
        barWidth: 3,
        barGap: 2,
        barRadius: 2,
        height: 160,
        normalize: true,
        // MediaElement exposes the underlying <audio> via getMediaElement(),
        // which the AudioEngine bridge needs to intercept the signal for
        // pitch-preserving slowdown + transpose. WebAudio backend hides
        // its source node inside an opaque WaveSurfer-owned graph.
        backend: "MediaElement",
      });

      ws.load(audioFileUrl);
      ws.on("ready", () => {
        setDuration(ws.getDuration());
        setWavesurfer(ws);
        // During rehearse, each queued song auto-plays as it becomes ready.
        // Rehearse is always user-initiated (the "Rehearse" button → navigation
        // → first user gesture), so the AudioContext is already running and a
        // programmatic play is allowed. Guarded on `active` so ordinary
        // single-song loads (Library/Collections "Open") never auto-play.
        if (useRehearseStore.getState().active) {
          setIsPlaying(true);
        }
      });
      // ``audioprocess`` fires ~60×/sec. Pushing every tick into the store
      // re-renders every currentTime subscriber (section ribbon, chord strip,
      // chord diagram, labels) at 60fps — the jank the user reported. The
      // waveform cursor is drawn natively by WaveSurfer (already smooth), so
      // React only needs the time for labels + chord highlighting; ~10/sec is
      // plenty. Throttle to one store write per 100ms.
      let lastTick = 0;
      ws.on("audioprocess", () => {
        const now = typeof performance !== "undefined" ? performance.now() : Date.now();
        if (now - lastTick >= 100) {
          lastTick = now;
          setCurrentTime(ws.getCurrentTime());
        }
      });
      // Seeks are discrete + need an immediate label update.
      ws.on("seeking", () => setCurrentTime(ws.getCurrentTime()));
      ws.on("finish", () => {
        setIsPlaying(false);
        // Rehearse mode: when a song finishes, advance to the next queued song.
        // next() returns null (and self-deactivates) at the end of the queue.
        if (useRehearseStore.getState().active) {
          const nextId = useRehearseStore.getState().next();
          if (nextId) {
            // loadExisting swaps analysis + audioFileUrl, which re-runs this
            // effect for the new song (new WaveSurfer instance). It catches its
            // own errors and resets jobStatus to 'idle' on failure rather than
            // throwing — so detect that and stop rehearse cleanly so we don't
            // get stuck on a song that won't load.
            void useAnalysisStore
              .getState()
              .loadExisting(nextId)
              .then(() => {
                if (useAnalysisStore.getState().jobStatus !== "done") {
                  useRehearseStore.getState().stop();
                }
              });
          }
        }
      });
      wsRef.current = ws;
      cleanup = () => ws.destroy();
    })();

    return () => { cleanup?.(); };
  }, [audioFileUrl, setDuration, setWavesurfer, setCurrentTime, setIsPlaying]);

  return (
    <section className="glass-panel rounded-xl p-6 relative overflow-hidden flex flex-col gap-4">
      {/* Song Structure Ribbon — click a section to jump to it (Phase 5 G7) */}
      {analysis?.sections && analysis.sections.length > 0 && (
        <div className="flex w-full h-8 rounded-md overflow-hidden bg-white/5 border border-white/5 text-xs font-semibold">
          {analysis.sections.map((sec, i) => {
            const pct = duration > 0 ? ((sec.end - sec.start) / duration) * 100 : 100 / analysis.sections.length;
            const isVerse = sec.name.toLowerCase().includes("verse");
            const isChorus = sec.name.toLowerCase().includes("chorus");
            // Lower-confidence sections read fainter so the label honesty
            // matches the clustering certainty (Phase 5 section confidence).
            const conf = sec.confidence ?? 1;
            const seekTo = () => {
              const ws = wsRef.current;
              if (ws && duration > 0) {
                ws.seekTo(Math.min(0.999, Math.max(0, sec.start / duration)));
                setCurrentTime(sec.start);
                // In practice mode, one tap loops the whole section (Moises-style).
                if (practiceMode) {
                  setLoopStart(sec.start);
                  setLoopEnd(sec.end);
                }
              }
            };
            const confLabel =
              sec.confidence != null ? ` · ${Math.round(conf * 100)}% confident` : "";
            const action = practiceMode ? `Loop ${sec.name}` : `Jump to ${sec.name}`;
            return (
              <button
                key={i}
                type="button"
                onClick={seekTo}
                title={`${action} · ${formatTime(sec.start)}${confLabel}`}
                aria-label={`${action} at ${formatTime(sec.start)}${confLabel}`}
                className={`relative flex min-w-0 items-center justify-center border-r border-white/5 last:border-r-0 cursor-pointer transition-colors hover:brightness-125 focus:outline-none focus-visible:ring-1 focus-visible:ring-primary ${
                  isChorus
                    ? "bg-secondary-container/20 text-on-secondary-container"
                    : isVerse
                    ? "bg-primary-container/10 text-primary"
                    : "bg-surface-variant/40 text-on-surface-variant"
                }`}
                style={{ width: `${pct}%` }}
              >
                {/* Text stays full-opacity for legibility; a bottom underline
                    fill (width ∝ confidence) conveys clustering certainty. */}
                <span className="truncate px-1">{sec.name}</span>
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute bottom-0 left-0 h-0.5 bg-current"
                  style={{ width: `${conf * 100}%`, opacity: 0.6 }}
                />
              </button>
            );
          })}
        </div>
      )}

      {/* Waveform Display */}
      <div className="relative w-full min-h-[160px]">
        <div ref={containerRef} className="w-full" />
        {/* A/B loop region overlay — shows the span being looped. */}
        {loopStart !== null && loopEnd !== null && loopEnd > loopStart && duration > 0 && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-0 bottom-0 bg-primary/15 border-x-2 border-primary/70"
            style={{
              left: `${(loopStart / duration) * 100}%`,
              width: `${((loopEnd - loopStart) / duration) * 100}%`,
            }}
          >
            <span className="absolute -top-0.5 left-0 -translate-x-1/2 text-[9px] font-bold text-primary">A</span>
            <span className="absolute -top-0.5 right-0 translate-x-1/2 text-[9px] font-bold text-primary">B</span>
          </div>
        )}
        {!audioFileUrl && (
          <div className="absolute inset-0 flex items-center justify-center text-on-surface-variant text-sm">
            No audio loaded
          </div>
        )}
      </div>

      {/* Transport Controls */}
      <div className="flex items-center justify-between">
        <TransportTime side="elapsed" />

        <button
          aria-label={isPlaying ? "Pause" : "Play"}
          className="w-16 h-16 rounded-full bg-gradient-to-br from-primary-container to-tertiary-container flex items-center justify-center shadow-[0_4px_20px_rgba(255,181,71,0.3)] hover:scale-105 active:scale-95 transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          onClick={async () => {
            // AudioEngine reroutes playback through Tone's Web Audio graph
            // (createMediaElementSource disconnects the element's default
            // speaker output). Browsers start that context suspended, so
            // ws.play() would run silently — resume it on this user gesture.
            if (!isPlaying) {
              try {
                const tone = await import("tone");
                await tone.start();
              } catch {
                /* no pitch bridge this session — element's default route plays */
              }
            }
            setIsPlaying(!isPlaying);
          }}
        >
          <span
            className="material-symbols-outlined text-on-primary-container text-3xl"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            {isPlaying ? "pause" : "play_arrow"}
          </span>
        </button>

        <TransportTime side="remaining" />
      </div>
    </section>
  );
};
