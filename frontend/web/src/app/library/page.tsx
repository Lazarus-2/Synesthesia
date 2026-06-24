"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiGet, ApiError } from "../../lib/apiClient";
import { useToastStore } from "../../store/useToastStore";
import { useFavoritesStore } from "../../store/useFavoritesStore";

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

// Filter chip primitive — keeps consistent Stitch styling for the chip row.
function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all border ${
        active
          ? "primary-gradient text-on-primary border-transparent"
          : "glass-panel text-on-surface-variant border-white/10 hover:text-on-surface hover:border-white/20"
      }`}
    >
      {children}
    </button>
  );
}

const KEY_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Any key" },
  { value: "C", label: "C" },
  { value: "G", label: "G" },
  { value: "D", label: "D" },
  { value: "A", label: "A" },
  { value: "E", label: "E" },
  { value: "B", label: "B" },
  { value: "F", label: "F" },
  { value: "b", label: "All flats" }, // any key containing a flat accidental
];

type TimeRange = "7d" | "30d" | "all";

const RANGE_LABEL: Record<TimeRange, string> = {
  "7d": "7d",
  "30d": "30d",
  all: "All",
};

function matchesKeyFilter(entryKey: string, filter: string): boolean {
  if (!filter) return true;
  if (filter === "b") return entryKey.includes("b"); // flat accidental
  // Partial, case-sensitive match on the tonic letter. ``entry.key`` is
  // shaped like "C major" / "A minor" — startsWith catches those without
  // matching the "C" in "C# major" via plain ``includes``.
  return entryKey.startsWith(filter);
}

function matchesRangeFilter(createdAt: string | null, range: TimeRange): boolean {
  if (range === "all") return true;
  if (!createdAt) return false;
  const ts = Date.parse(createdAt);
  if (Number.isNaN(ts)) return false;
  const days = range === "7d" ? 7 : 30;
  return Date.now() - ts <= days * 24 * 60 * 60 * 1000;
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

  // Filter state — applied client-side over the current page's items.
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [keyFilter, setKeyFilter] = useState<string>("");
  const [keyMenuOpen, setKeyMenuOpen] = useState(false);
  const [range, setRange] = useState<TimeRange>("all");
  const favoriteIds = useFavoritesStore((s) => s.ids);

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

  // Stable ref unless data changes, so the filter memo below doesn't recompute
  // on every render (a fresh `[]` literal would invalidate it each time).
  const rawItems = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  const items = useMemo(() => {
    const favSet = new Set(favoriteIds);
    return rawItems.filter((it) => {
      if (favoritesOnly && !favSet.has(it.job_id)) return false;
      if (!matchesKeyFilter(it.key ?? "", keyFilter)) return false;
      if (!matchesRangeFilter(it.created_at, range)) return false;
      return true;
    });
  }, [rawItems, favoriteIds, favoritesOnly, keyFilter, range]);
  const filtered = items.length !== rawItems.length;
  const activeKeyLabel =
    KEY_OPTIONS.find((o) => o.value === keyFilter)?.label ?? "Any key";

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
        <p className="text-sm text-on-surface-variant mb-6">
          {loading
            ? "Loading…"
            : filtered
              ? `${items.length} of ${total} song${total === 1 ? "" : "s"} match filters`
              : `${total} analyzed song${total === 1 ? "" : "s"}`}
        </p>

        {/* Filter chips */}
        <div className="flex flex-wrap items-center gap-2 mb-8">
          <Chip active={!favoritesOnly} onClick={() => setFavoritesOnly(false)}>
            All
          </Chip>
          <Chip
            active={favoritesOnly}
            onClick={() => setFavoritesOnly((v) => !v)}
          >
            <span className="mr-1">★</span>
            Favorites
            {favoriteIds.length > 0 && (
              <span className="ml-1 opacity-70">({favoriteIds.length})</span>
            )}
          </Chip>

          <span className="w-px h-5 bg-white/10 mx-1" aria-hidden />

          {/* Key dropdown chip */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setKeyMenuOpen((v) => !v)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all border inline-flex items-center gap-1 ${
                keyFilter
                  ? "primary-gradient text-on-primary border-transparent"
                  : "glass-panel text-on-surface-variant border-white/10 hover:text-on-surface hover:border-white/20"
              }`}
              aria-haspopup="listbox"
              aria-expanded={keyMenuOpen}
            >
              Key: {activeKeyLabel}
              <span
                className="material-symbols-outlined text-base"
                style={{ fontVariationSettings: "'wght' 400" }}
              >
                {keyMenuOpen ? "expand_less" : "expand_more"}
              </span>
            </button>
            {keyMenuOpen && (
              <ul
                className="absolute z-10 mt-2 min-w-[10rem] glass-panel rounded-xl p-1 border border-white/10 shadow-xl"
                role="listbox"
              >
                {KEY_OPTIONS.map((opt) => (
                  <li key={opt.value || "any"}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={keyFilter === opt.value}
                      onClick={() => {
                        setKeyFilter(opt.value);
                        setKeyMenuOpen(false);
                      }}
                      className={`w-full text-left px-3 py-1.5 rounded-lg text-xs ${
                        keyFilter === opt.value
                          ? "bg-primary/15 text-primary"
                          : "text-on-surface-variant hover:bg-white/5 hover:text-on-surface"
                      }`}
                    >
                      {opt.label}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <span className="w-px h-5 bg-white/10 mx-1" aria-hidden />

          {/* Time range chip group */}
          <div className="inline-flex items-center gap-1">
            {(["7d", "30d", "all"] as TimeRange[]).map((r) => (
              <Chip key={r} active={range === r} onClick={() => setRange(r)}>
                {RANGE_LABEL[r]}
              </Chip>
            ))}
          </div>
        </div>

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

        {!loading && items.length === 0 && rawItems.length === 0 && (
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

        {!loading && items.length === 0 && rawItems.length > 0 && (
          <div className="glass-panel rounded-xl p-12 text-center">
            <span className="material-symbols-outlined text-5xl text-on-surface-variant mb-4 inline-block">
              filter_alt_off
            </span>
            <h2 className="font-headline text-xl text-on-surface mb-2">
              No songs match these filters
            </h2>
            <p className="text-sm text-on-surface-variant mb-6">
              Try clearing the key, time range, or favorites filter.
            </p>
            <button
              type="button"
              onClick={() => {
                setFavoritesOnly(false);
                setKeyFilter("");
                setRange("all");
              }}
              className="inline-block px-5 py-2 glass-panel rounded-full text-sm hover:border-primary/30"
            >
              Clear filters
            </button>
          </div>
        )}

        {!loading && items.length > 0 && (
          <>
            <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {items.map((it) => (
                <li key={it.job_id} className="relative group h-full">
                  {/* Primary action: open the saved song in the FULL player. */}
                  <Link
                    href={`/?job=${encodeURIComponent(it.job_id)}`}
                    className="glass-panel rounded-xl p-5 flex flex-col gap-3 hover:border-primary/30 transition-all h-full"
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
                  {/* Secondary: read-only share view. Sits above the card link
                      (not nested — anchors can't nest) and only fades in on
                      hover/focus so the card stays clean. */}
                  <Link
                    href={`/s/${it.job_id}`}
                    className="absolute top-3 right-3 text-[10px] font-semibold tracking-wide px-2 py-1 rounded-full bg-surface/70 text-on-surface-variant opacity-0 group-hover:opacity-100 focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary transition-opacity hover:text-on-surface"
                    title="Open read-only share view"
                  >
                    Share view
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
