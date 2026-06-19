"use client";

import React, { useState, useEffect } from "react";
import { API_V1 } from "../../lib/apiClient";

interface SearchResult {
  source?: string;
  sources?: string[];
  title: string;
  artist: string;
  album?: string;
  year?: string;
  duration?: number;
  image_url?: string;
  preview_url?: string;
  mbid?: string;
  deezer_id?: number;
}

/** Debounced (250 ms) hit to /api/v1/search backed by Deezer + MusicBrainz.
 *
 *  Clicking a result enqueues the existing /analyze flow with a synthesized
 *  ytsearch URL — the user gets the same end-to-end pipeline they'd get
 *  from pasting a YouTube link. We don't try to download Deezer's 30 s
 *  preview directly because the analysis pipeline wants a full track. */
export const SearchPanel: React.FC<{
  onPick: (query: string) => void;
}> = ({ onPick }) => {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const trimmed = q.trim();
    if (trimmed.length < 2) {
      // Bail-out updaters: return the SAME reference when already empty so React
      // skips the re-render (no cascade) on every keystroke under the threshold.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional reset of this fetch effect's own state; bail-out updaters prevent cascades
      setResults((r) => (r.length ? [] : r));
      setErr((e) => (e === null ? e : null));
      setLoading((l) => (l ? false : l));
      return;
    }
    const ctl = new AbortController();
    const t = setTimeout(() => {
      // setState moved off the synchronous effect body into the debounced
      // callback so a fetch only starts (and toggles loading) once per pause.
      setLoading(true);
      setErr(null);
      fetch(`${API_V1}/search?q=${encodeURIComponent(trimmed)}&limit=12`, {
        signal: ctl.signal,
      })
        .then(async (r) => {
          if (!r.ok) throw new Error(`search failed: ${r.status}`);
          return r.json();
        })
        .then((d) => setResults(d.results || []))
        .catch((e) => {
          if (e.name !== "AbortError") setErr(e.message);
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
  }, [q]);

  return (
    <div className="md:col-span-12 glass-panel rounded-xl p-4 flex flex-col gap-3 glow-focus">
      <div className="flex items-center gap-3 px-2 py-1 border-b border-white/5 pb-3">
        <span className="material-symbols-outlined text-outline">search</span>
        <input
          className="bg-transparent border-none w-full text-on-surface focus:ring-0 focus:outline-none placeholder:text-outline-variant p-0"
          placeholder="Search a song by title or artist — e.g. blackbird beatles"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {loading && (
          <span className="material-symbols-outlined text-primary animate-spin text-[18px]">progress_activity</span>
        )}
      </div>
      {err && <p className="text-xs text-error">{err}</p>}
      {results.length > 0 && (
        <ul className="flex flex-col gap-1 max-h-96 overflow-y-auto" role="listbox">
          {results.map((r, idx) => (
            <li key={(r.mbid || r.deezer_id || idx).toString()}>
              <button
                role="option"
                aria-selected={false}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-surface-container-high text-left transition-colors group"
                onClick={() => onPick(`${r.title} ${r.artist}`)}
              >
                {r.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={r.image_url} alt="" className="w-10 h-10 rounded shrink-0 object-cover" />
                ) : (
                  <div className="w-10 h-10 rounded shrink-0 bg-surface-container-highest flex items-center justify-center">
                    <span className="material-symbols-outlined text-on-surface-variant text-[20px]">music_note</span>
                  </div>
                )}
                <div className="flex-grow min-w-0">
                  <div className="truncate text-on-surface text-sm font-medium">{r.title}</div>
                  <div className="truncate text-on-surface-variant text-xs">
                    {r.artist}{r.album ? ` · ${r.album}` : ""}{r.year ? ` · ${r.year}` : ""}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  {(r.sources || [r.source]).filter(Boolean).map((s) => (
                    <span
                      key={s}
                      className="px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border border-white/10 bg-surface-container-high text-on-surface-variant"
                      title={s === "musicbrainz" ? "MusicBrainz" : "Deezer"}
                    >
                      {s === "musicbrainz" ? "MB" : "DZ"}
                    </span>
                  ))}
                </div>
                <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary text-[18px] shrink-0">
                  arrow_forward
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!loading && !results.length && q.trim().length >= 2 && (
        <p className="text-xs text-on-surface-variant px-2">No matches.</p>
      )}
    </div>
  );
};
