"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useAuthStore } from "../../store/useAuthStore";
import { useFavoritesStore } from "../../store/useFavoritesStore";
import { useCollectionsStore } from "../../store/useCollectionsStore";
import { useToastStore } from "../../store/useToastStore";
import type { CollectionKind } from "../../types";

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
      <div className="flex items-center gap-5">
        <Link href="/library" className="text-sm text-on-surface-variant hover:text-primary">
          Library
        </Link>
        <Link href="/" className="text-sm text-on-surface-variant hover:text-primary">
          ← New analysis
        </Link>
      </div>
    </nav>
  );
}

export default function CollectionsClient() {
  const token = useAuthStore((s) => s.token);
  const items = useCollectionsStore((s) => s.items);
  const loading = useCollectionsStore((s) => s.loading);
  const loaded = useCollectionsStore((s) => s.loaded);

  const [name, setName] = useState("");
  const [kind, setKind] = useState<CollectionKind>("collection");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (token) useCollectionsStore.getState().fetchAll();
  }, [token]);

  if (!token) {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <TopNav />
        <main className="flex-grow flex items-center justify-center px-4">
          <div className="glass-panel rounded-xl p-10 max-w-md text-center">
            <span className="material-symbols-outlined text-5xl text-on-surface-variant mb-4 inline-block">
              queue_music
            </span>
            <h1 className="font-headline text-2xl text-on-surface mb-2">Sign in to use collections</h1>
            <p className="text-sm text-on-surface-variant mb-6">
              Collections and setlists are saved to your account.
            </p>
            <Link
              href="/login"
              className="inline-block px-6 py-2.5 primary-gradient text-on-primary rounded-full font-semibold text-sm"
            >
              Sign in
            </Link>
          </div>
        </main>
      </div>
    );
  }

  const handleCreate = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setCreating(true);
    const id = await useCollectionsStore.getState().create(trimmed, kind);
    setCreating(false);
    if (id) setName("");
  };

  const handleImportFavorites = async () => {
    const ids = useFavoritesStore.getState().ids;
    if (ids.length === 0) {
      useToastStore.getState().info("No favorites yet", "Star some songs first.");
      return;
    }
    await useCollectionsStore.getState().create("My Favorites", "collection", ids);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <TopNav />
      <main className="flex-grow px-6 md:px-16 py-10 max-w-[1280px] mx-auto w-full">
        <h1 className="font-headline text-4xl font-semibold text-on-surface mb-2">Collections</h1>
        <p className="text-sm text-on-surface-variant mb-8">
          Group analyzed songs into collections, or build an ordered setlist.
        </p>

        {/* Create row */}
        <div className="glass-panel rounded-xl p-4 mb-8 flex flex-col sm:flex-row gap-3 sm:items-center">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
            placeholder={kind === "setlist" ? "New setlist name…" : "New collection name…"}
            className="flex-grow bg-surface-container-high border border-white/10 rounded-md px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
          />
          <div className="inline-flex rounded-full glass-panel border border-white/10 p-0.5 shrink-0">
            {(["collection", "setlist"] as CollectionKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`px-3 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all ${
                  kind === k
                    ? "primary-gradient text-on-primary"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {k === "setlist" ? "Setlist" : "Collection"}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating || !name.trim()}
            className="px-5 py-2 primary-gradient text-on-primary rounded-full font-semibold text-sm disabled:opacity-40 shrink-0"
          >
            {creating ? "Creating…" : "Create"}
          </button>
          <button
            type="button"
            onClick={handleImportFavorites}
            className="px-4 py-2 glass-panel rounded-full text-sm hover:border-primary/30 shrink-0"
          >
            <span className="mr-1">★</span> Save favorites as a collection
          </button>
        </div>

        {loading && !loaded && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="glass-panel rounded-xl h-32 animate-pulse-glow" />
            ))}
          </div>
        )}

        {loaded && items.length === 0 && (
          <div className="glass-panel rounded-xl p-12 text-center">
            <span className="material-symbols-outlined text-5xl text-on-surface-variant mb-4 inline-block">
              queue_music
            </span>
            <h2 className="font-headline text-xl text-on-surface mb-2">No collections yet</h2>
            <p className="text-sm text-on-surface-variant">No collections yet — create one above.</p>
          </div>
        )}

        {items.length > 0 && (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/collections/${c.id}`}
                  className="glass-panel rounded-xl p-5 flex flex-col gap-3 hover:border-primary/30 transition-all h-full"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-headline text-lg text-on-surface line-clamp-2">{c.name}</p>
                    <span
                      className={`text-[10px] uppercase font-semibold tracking-wider px-2 py-1 rounded shrink-0 ${
                        c.kind === "setlist"
                          ? "bg-primary/15 text-primary"
                          : "bg-secondary-container/15 text-on-secondary-container"
                      }`}
                    >
                      {c.kind === "setlist" ? "Setlist" : "Collection"}
                    </span>
                  </div>
                  {c.description && (
                    <p className="text-sm text-on-surface-variant line-clamp-2">{c.description}</p>
                  )}
                  <p className="text-xs text-on-surface-variant mt-auto">
                    {c.song_count} song{c.song_count === 1 ? "" : "s"}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
