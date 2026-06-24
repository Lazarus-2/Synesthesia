"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiGet, ApiError } from "../../../lib/apiClient";
import { useAuthStore } from "../../../store/useAuthStore";
import { useCollectionsStore } from "../../../store/useCollectionsStore";
import { useToastStore } from "../../../store/useToastStore";
import type { CollectionDetail, CollectionSong } from "../../../types";

function TopNav() {
  return (
    <nav className="w-full px-6 md:px-16 h-20 flex justify-between items-center border-b border-white/5 bg-surface/30 backdrop-blur-xl shrink-0">
      <Link href="/" className="flex items-center gap-2">
        <span className="material-symbols-outlined text-primary-container text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
          graphic_eq
        </span>
        <span className="font-headline text-3xl font-semibold text-primary-container tracking-tight">
          Synesthesia
        </span>
      </Link>
      <Link href="/collections" className="text-sm text-on-surface-variant hover:text-primary">
        ← All collections
      </Link>
    </nav>
  );
}

function fmtTempo(t: number | null): string {
  return t ? `${Math.round(t)} BPM` : "—";
}

export default function CollectionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const router = useRouter();
  const token = useAuthStore((s) => s.token);

  const [detail, setDetail] = useState<CollectionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  // ``loadedId`` tracks the collection id whose fetch has settled; loading is
  // derived by comparing it to the requested ``id``. This avoids a synchronous
  // setState in the effect body (React 19 / react-hooks/set-state-in-effect).
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const loading = !!token && !!id && loadedId !== id;

  useEffect(() => {
    if (!id || !token) return;
    let cancelled = false;
    apiGet<CollectionDetail>(`/collections/${encodeURIComponent(id)}`)
      .then((r) => {
        if (cancelled) return;
        setError(null);
        setDetail(r);
        setNameDraft(r.name);
        setLoadedId(id);
      })
      .catch((err) => {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : "Could not load collection.";
        setError(message);
        useToastStore.getState().error("Collection unavailable", message);
        setLoadedId(id);
      });
    return () => { cancelled = true; };
  }, [id, token]);

  if (!token) {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <TopNav />
        <main className="flex-grow flex items-center justify-center px-4">
          <div className="glass-panel rounded-xl p-10 max-w-md text-center">
            <h1 className="font-headline text-2xl text-on-surface mb-2">Sign in to use collections</h1>
            <Link href="/login" className="inline-block mt-4 px-6 py-2.5 primary-gradient text-on-primary rounded-full font-semibold text-sm">
              Sign in
            </Link>
          </div>
        </main>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <TopNav />
        <main className="flex-grow px-6 md:px-16 py-10 max-w-[1024px] mx-auto w-full">
          <div className="glass-panel rounded-xl h-12 w-1/3 animate-pulse-glow mb-6" />
          <div className="flex flex-col gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="glass-panel rounded-xl h-16 animate-pulse-glow" />
            ))}
          </div>
        </main>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <TopNav />
        <main className="flex-grow flex items-center justify-center px-4">
          <div className="glass-panel rounded-xl p-8 max-w-md text-center">
            <h1 className="font-headline text-2xl text-error mb-2">Not available</h1>
            <p className="text-sm text-on-surface-variant mb-6">{error || "Collection not found."}</p>
            <Link href="/collections" className="text-primary hover:underline">← Back to collections</Link>
          </div>
        </main>
      </div>
    );
  }

  const d = detail;

  const saveName = async () => {
    const trimmed = nameDraft.trim();
    setEditingName(false);
    if (!trimmed || trimmed === d.name) {
      setNameDraft(d.name);
      return;
    }
    const prevName = d.name;
    setDetail({ ...d, name: trimmed });
    const ok = await useCollectionsStore.getState().rename(d.id, trimmed);
    if (!ok) {
      setDetail({ ...d, name: prevName });
      setNameDraft(prevName);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${d.name}"? This cannot be undone.`)) return;
    await useCollectionsStore.getState().remove(d.id);
    router.push("/collections");
  };

  const moveSong = async (index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (target < 0 || target >= d.songs.length) return;
    const prev = d;
    const songs = [...d.songs];
    [songs[index], songs[target]] = [songs[target], songs[index]];
    const songIds = songs.map((s) => s.job_id);
    setDetail({ ...d, songs, song_ids: songIds });
    const ok = await useCollectionsStore.getState().reorder(d.id, songIds);
    if (!ok) setDetail(prev);
  };

  const removeSong = async (jobId: string) => {
    const prev = d;
    const songs = d.songs.filter((s) => s.job_id !== jobId);
    setDetail({ ...d, songs, song_ids: songs.map((s) => s.job_id) });
    const ok = await useCollectionsStore.getState().removeSong(d.id, jobId);
    if (!ok) setDetail(prev);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <TopNav />
      <main className="flex-grow px-6 md:px-16 py-10 max-w-[1024px] mx-auto w-full">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-8">
          <div className="min-w-0 flex-grow">
            <span
              className={`text-[10px] uppercase font-semibold tracking-wider px-2 py-1 rounded inline-block mb-3 ${
                d.kind === "setlist"
                  ? "bg-primary/15 text-primary"
                  : "bg-secondary-container/15 text-on-secondary-container"
              }`}
            >
              {d.kind === "setlist" ? "Setlist" : "Collection"}
            </span>
            {editingName ? (
              <input
                type="text"
                value={nameDraft}
                autoFocus
                onChange={(e) => setNameDraft(e.target.value)}
                onBlur={saveName}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveName();
                  if (e.key === "Escape") { setNameDraft(d.name); setEditingName(false); }
                }}
                className="w-full bg-surface-container-high border border-white/10 rounded-md px-3 py-2 font-headline text-3xl text-on-surface focus:border-primary focus:outline-none"
              />
            ) : (
              <button
                type="button"
                onClick={() => { setNameDraft(d.name); setEditingName(true); }}
                className="group flex items-center gap-2 text-left"
                title="Rename"
              >
                <h1 className="font-headline text-4xl font-semibold text-on-surface">{d.name}</h1>
                <span className="material-symbols-outlined text-on-surface-variant opacity-0 group-hover:opacity-100 transition-opacity text-xl">
                  edit
                </span>
              </button>
            )}
            <p className="text-sm text-on-surface-variant mt-2">
              {d.songs.length} song{d.songs.length === 1 ? "" : "s"}
            </p>
          </div>
          <button
            type="button"
            onClick={handleDelete}
            className="px-4 py-2 glass-panel rounded-full text-sm text-error hover:border-error/40 shrink-0"
          >
            Delete
          </button>
        </div>

        {/* Song list */}
        {d.songs.length === 0 ? (
          <div className="glass-panel rounded-xl p-12 text-center">
            <span className="material-symbols-outlined text-5xl text-on-surface-variant mb-4 inline-block">
              music_off
            </span>
            <h2 className="font-headline text-xl text-on-surface mb-2">No songs yet</h2>
            <p className="text-sm text-on-surface-variant">
              Add songs from an analysis using the “Add to collection” button.
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {d.songs.map((s: CollectionSong, i) => (
              <li
                key={s.job_id}
                className="glass-panel rounded-xl p-4 flex items-center gap-3"
              >
                <span className="text-sm font-semibold text-on-surface-variant w-6 text-center shrink-0">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-grow">
                  <p className="text-on-surface line-clamp-1">{s.title || "Untitled"}</p>
                  <p className="text-sm text-on-surface-variant line-clamp-1">{s.artist || "Unknown artist"}</p>
                </div>
                <div className="hidden sm:flex items-center gap-2 shrink-0">
                  <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-1 rounded bg-secondary-container/15 text-on-secondary-container">
                    {s.key || "—"}
                  </span>
                  <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-1 rounded bg-white/5 text-on-surface-variant">
                    {fmtTempo(s.tempo)}
                  </span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => moveSong(i, -1)}
                    disabled={i === 0}
                    aria-label="Move up"
                    className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-white/5 disabled:opacity-25 text-on-surface-variant"
                  >
                    <span className="material-symbols-outlined text-lg">arrow_upward</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => moveSong(i, 1)}
                    disabled={i === d.songs.length - 1}
                    aria-label="Move down"
                    className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-white/5 disabled:opacity-25 text-on-surface-variant"
                  >
                    <span className="material-symbols-outlined text-lg">arrow_downward</span>
                  </button>
                  <Link
                    href={`/s/${s.job_id}`}
                    className="px-3 py-1.5 rounded-full glass-panel text-xs hover:border-primary/30 ml-1"
                  >
                    Open
                  </Link>
                  <button
                    type="button"
                    onClick={() => removeSong(s.job_id)}
                    aria-label="Remove from collection"
                    className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-error/10 text-on-surface-variant hover:text-error"
                  >
                    <span className="material-symbols-outlined text-lg">close</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
