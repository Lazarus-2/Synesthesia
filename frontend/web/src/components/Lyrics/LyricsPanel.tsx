"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";
import { API_V1 } from "../../lib/apiClient";

interface SyncedLine {
  t: number;          // seconds
  text: string;
}

function parseLrc(lrc: string): SyncedLine[] {
  const lines: SyncedLine[] = [];
  for (const raw of lrc.split(/\r?\n/)) {
    const m = /^\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]\s*(.*)$/.exec(raw);
    if (!m) continue;
    const min = parseInt(m[1], 10);
    const sec = parseInt(m[2], 10);
    const ms = m[3] ? parseInt(m[3].padEnd(3, "0").slice(0, 3), 10) : 0;
    lines.push({ t: min * 60 + sec + ms / 1000, text: m[4].trim() });
  }
  return lines.sort((a, b) => a.t - b.t);
}

/** Synced lyric scroller backed by LRCLIB.
 *
 *  Pulls ``track_name`` + ``artist_name`` from the current analysis, hits
 *  ``GET /api/v1/lyrics``, parses the LRC, and auto-scrolls the active line
 *  to the center of the panel as ``currentTime`` advances. */
export const LyricsPanel: React.FC = () => {
  const analysis = useAnalysisStore((s) => s.analysis);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const [syncedLines, setSyncedLines] = useState<SyncedLine[]>([]);
  const [plainLyrics, setPlainLyrics] = useState<string>("");
  const [status, setStatus] = useState<"idle" | "loading" | "loaded" | "empty" | "error">("idle");
  const scrollerRef = useRef<HTMLDivElement>(null);
  const lineRefs = useRef<Array<HTMLDivElement | null>>([]);

  const trackName = analysis?.title || "";
  const artistName = analysis?.artist || "";
  const duration = Math.round(analysis?.duration || 0);

  // Fetch lyrics whenever the analyzed track changes.
  useEffect(() => {
    if (!trackName || !artistName) {
      setStatus("idle");
      setSyncedLines([]);
      setPlainLyrics("");
      return;
    }
    setStatus("loading");
    const ctl = new AbortController();
    const url = new URL(`${API_V1}/lyrics`);
    url.searchParams.set("track_name", trackName);
    url.searchParams.set("artist_name", artistName);
    if (duration > 0) url.searchParams.set("duration", duration.toString());
    fetch(url.toString(), { signal: ctl.signal })
      .then((r) => r.json())
      .then((d) => {
        const synced = parseLrc(d.synced_lyrics || "");
        setSyncedLines(synced);
        setPlainLyrics(d.plain_lyrics || "");
        setStatus(synced.length || d.plain_lyrics ? "loaded" : "empty");
      })
      .catch((e) => {
        if (e.name !== "AbortError") setStatus("error");
      });
    return () => ctl.abort();
  }, [trackName, artistName, duration]);

  // Active line index based on currentTime.
  const activeIdx = useMemo(() => {
    if (!syncedLines.length) return -1;
    let lo = 0,
      hi = syncedLines.length - 1,
      best = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (syncedLines[mid].t <= currentTime) {
        best = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return best;
  }, [syncedLines, currentTime]);

  // Auto-scroll the active line into the centre.
  useEffect(() => {
    if (activeIdx < 0) return;
    const node = lineRefs.current[activeIdx];
    if (node) node.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeIdx]);

  if (status === "idle") {
    return <p className="text-sm text-on-surface-variant">No track loaded yet.</p>;
  }
  if (status === "loading") {
    return <p className="text-sm text-on-surface-variant">Loading lyrics from LRCLIB…</p>;
  }
  if (status === "error") {
    return <p className="text-sm text-error">Couldn&apos;t reach the lyrics service.</p>;
  }
  if (status === "empty") {
    return (
      <p className="text-sm text-on-surface-variant">
        No lyrics in LRCLIB for {trackName ? `“${trackName}”` : "this track"}.
      </p>
    );
  }

  if (!syncedLines.length) {
    // Plain text fallback.
    return (
      <div className="prose prose-invert max-w-none whitespace-pre-wrap text-on-surface-variant text-sm leading-relaxed">
        {plainLyrics}
      </div>
    );
  }

  return (
    <div
      ref={scrollerRef}
      className="max-h-[60vh] overflow-y-auto px-4 py-6 space-y-3"
      role="list"
      aria-label="Synced lyrics"
    >
      {syncedLines.map((line, i) => (
        <div
          key={i}
          ref={(el) => { lineRefs.current[i] = el; }}
          role="listitem"
          className={`text-center transition-all duration-300 ${
            i === activeIdx
              ? "primary-gradient-text font-headline text-2xl font-semibold scale-105"
              : i < activeIdx
              ? "text-outline text-base"
              : "text-on-surface-variant text-base"
          }`}
        >
          {line.text || "♪"}
        </div>
      ))}
    </div>
  );
};
