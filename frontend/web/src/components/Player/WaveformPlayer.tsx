"use client";

import React, { useEffect, useRef } from "react";
import { usePlayerStore } from "../../store/usePlayerStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export const WaveformPlayer: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const { isPlaying, setIsPlaying, currentTime, duration, setCurrentTime, setDuration, audioFileUrl, setWavesurfer } = usePlayerStore();
  const { analysis } = useAnalysisStore();
  const wsRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current || !audioFileUrl) return;

    let ws: any;
    (async () => {
      const WaveSurfer = (await import("wavesurfer.js")).default;
      ws = WaveSurfer.create({
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
        backend: "WebAudio",
      });

      ws.load(audioFileUrl);
      ws.on("ready", () => {
        setDuration(ws.getDuration());
        setWavesurfer(ws);
      });
      ws.on("audioprocess", () => setCurrentTime(ws.getCurrentTime()));
      ws.on("seeking", () => setCurrentTime(ws.getCurrentTime()));
      ws.on("finish", () => setIsPlaying(false));
      wsRef.current = ws;
    })();

    return () => { ws?.destroy(); };
  }, [audioFileUrl, setDuration, setWavesurfer, setCurrentTime, setIsPlaying]);

  const remaining = duration - currentTime;

  return (
    <section className="glass-panel rounded-xl p-6 relative overflow-hidden flex flex-col gap-4">
      {/* Song Structure Ribbon */}
      {analysis?.sections && analysis.sections.length > 0 && (
        <div className="flex w-full h-8 rounded-md overflow-hidden bg-white/5 border border-white/5 text-xs font-semibold">
          {analysis.sections.map((sec, i) => {
            const pct = duration > 0 ? ((sec.end - sec.start) / duration) * 100 : 100 / analysis.sections.length;
            const isVerse = sec.name.toLowerCase().includes("verse");
            const isChorus = sec.name.toLowerCase().includes("chorus");
            return (
              <div
                key={i}
                className={`flex items-center justify-center border-r border-white/5 last:border-r-0 ${
                  isChorus
                    ? "bg-secondary-container/20 text-on-secondary-container"
                    : isVerse
                    ? "bg-primary-container/10 text-primary"
                    : "bg-surface-variant/40 text-on-surface-variant"
                }`}
                style={{ width: `${pct}%` }}
              >
                {sec.name}
              </div>
            );
          })}
        </div>
      )}

      {/* Waveform Display */}
      <div className="relative w-full min-h-[160px]">
        <div ref={containerRef} className="w-full" />
        {!audioFileUrl && (
          <div className="absolute inset-0 flex items-center justify-center text-on-surface-variant text-sm">
            No audio loaded
          </div>
        )}
      </div>

      {/* Transport Controls */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-primary-container tabular-nums">
          {formatTime(currentTime)}
        </span>

        <button
          className="w-16 h-16 rounded-full bg-gradient-to-br from-primary-container to-tertiary-container flex items-center justify-center shadow-[0_4px_20px_rgba(255,181,71,0.3)] hover:scale-105 active:scale-95 transition-transform"
          onClick={() => setIsPlaying(!isPlaying)}
        >
          <span
            className="material-symbols-outlined text-on-primary-container text-3xl"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            {isPlaying ? "pause" : "play_arrow"}
          </span>
        </button>

        <span className="text-xs font-medium text-on-surface-variant tabular-nums">
          -{formatTime(remaining > 0 ? remaining : 0)}
        </span>
      </div>
    </section>
  );
};
