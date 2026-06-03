"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, ApiError } from "../../lib/apiClient";
import { useToastStore } from "../../store/useToastStore";

// Library entry shape mirrors backend ``LibraryEntry`` (Plan 3 A7).
interface LibraryEntry {
  job_id: string;
  title: string | null;
  artist: string | null;
  key: string;
  tempo: number;
  duration: number;
  created_at: string | null;
  vibe_palette: string[];
}

interface LibraryResponse {
  items: LibraryEntry[];
  total: number;
  limit: number;
  offset: number;
}

const PAGE_SIZE = 24;

function formatDuration(s: number): string {
  if (!s || s <= 0) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function LibraryPage() {
  // ``activePage`` tracks the page whose fetch has completed; loading is
  // derived from comparing it to the requested ``page``. This avoids the
  // synchronous-setState-in-effect warning under React 19's stricter purity
  // rules and naturally reflects pending fetches without a separate flag.
  const [data, setData] = useState<LibraryResponse | null>(null);
  const [page, setPage] = useState(0);
  const [activePage, setActivePage] = useState<number | null>(null);
  const loading = activePage !== page;

  useEffect(() => {
    let cancelled = false;
    apiGet<LibraryResponse>(`/library?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`)
      .then((r) => { if (!cancelled) { setData(r); setActivePage(page); } })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : "Could not load library.";
        useToastStore.getState().error("Library failed to load", message);
        if (!cancelled) setActivePage(page);  // unblock loading state
      });
    return () => { cancelled = true; };
  }, [page]);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Top Nav */}
      <nav className="w-full px-6 md:px-16 h-20 flex justify-between items-center border-b border-white/5 bg-surface/30 backdrop-blur-xl shrink-0">
        <Link href="/" className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary-container text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            graphic_eq
          </span>
          <span className="font-headline text-3xl font-semibold text-primary-container tracking-tight">
            Synesthesia
          </span>
        </Link>
        <Link
          href="/"
          className="text-sm text-on-surface-variant hover:text-primary"
        >
          ← New analysis
        </Link>
      </nav>

      <main className="flex-grow px-6 md:px-16 py-10 max-w-[1280px] mx-auto w-full">
        <h1 className="font-headline text-4xl font-semibold text-on-surface mb-2">Library</h1>
        <p className="text-sm text-on-surface-variant mb-8">
          {loading ? "Loading…" : `${total} analyzed song${total === 1 ? "" : "s"}`}
        </p>

        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="glass-panel rounded-xl h-44 animate-pulse-glow"
              />
            ))}
          </div>
        )}

        {!loading && items.length === 0 && (
          <div className="glass-panel rounded-xl p-12 text-center">
            <span className="material-symbols-outlined text-5xl text-on-surface-variant mb-4 inline-block">
              library_music
            </span>
            <h2 className="font-headline text-xl text-on-surface mb-2">No analyses yet</h2>
            <p className="text-sm text-on-surface-variant mb-6">
              Drop an audio file or paste a YouTube link on the home page to get started.
            </p>
            <Link
              href="/"
              className="inline-block px-5 py-2 primary-gradient text-on-primary rounded-full font-semibold text-sm"
            >
              Start an analysis
            </Link>
          </div>
        )}

        {!loading && items.length > 0 && (
          <>
            <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {items.map((it) => (
                <li key={it.job_id}>
                  <Link
                    href={`/s/${it.job_id}`}
                    className="glass-panel rounded-xl p-5 flex flex-col gap-3 hover:border-primary/30 transition-all group h-full"
                  >
                    {/* Vibe palette stripe */}
                    {it.vibe_palette.length > 0 && (
                      <div className="flex h-2 w-full rounded-md overflow-hidden">
                        {it.vibe_palette.slice(0, 6).map((c, i) => (
                          <div key={i} className="flex-1" style={{ backgroundColor: c }} />
                        ))}
                      </div>
                    )}
                    <div>
                      <p className="font-headline text-lg text-on-surface line-clamp-1">
                        {it.title || "Untitled"}
                      </p>
                      <p className="text-sm text-on-surface-variant line-clamp-1">
                        {it.artist || "Unknown artist"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 mt-auto">
                      <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-1 rounded bg-secondary-container/15 text-on-secondary-container">
                        {it.key}
                      </span>
                      <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-1 rounded bg-white/5 text-on-surface-variant">
                        {Math.round(it.tempo)} BPM
                      </span>
                      <span className="text-[10px] text-on-surface-variant ml-auto">
                        {formatDuration(it.duration)}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>

            {lastPage > 0 && (
              <div className="flex justify-center gap-2 mt-10">
                <button
                  className="px-4 py-2 rounded-full glass-panel text-sm disabled:opacity-30"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  ← Prev
                </button>
                <span className="px-4 py-2 text-sm text-on-surface-variant">
                  Page {page + 1} / {lastPage + 1}
                </span>
                <button
                  className="px-4 py-2 rounded-full glass-panel text-sm disabled:opacity-30"
                  onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
                  disabled={page === lastPage}
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
