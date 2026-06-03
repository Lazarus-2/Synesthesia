"use client";

// Public share page (Plan 3 B8). Renders a read-only summary of an analysis
// by job id. Server components could prefetch this on the server, but the
// existing API client is in client-land so we keep it client-only for now.

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiGet, ApiError } from "../../../lib/apiClient";
import type { AnalyzeResponse } from "../../../types";

export default function SharePage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params?.jobId;
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    apiGet<AnalyzeResponse>(`/share/${encodeURIComponent(jobId)}`)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load shared analysis."));
  }, [jobId]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="glass-panel rounded-xl p-8 max-w-md text-center">
          <h1 className="font-headline text-2xl text-error mb-2">Not available</h1>
          <p className="text-sm text-on-surface-variant mb-6">{error}</p>
          <Link href="/" className="text-primary hover:underline">
            ← Back to Synesthesia
          </Link>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-on-surface-variant text-sm">Loading shared analysis…</div>
      </div>
    );
  }

  const a = data.analysis;
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <nav className="w-full px-6 md:px-16 h-20 flex justify-between items-center border-b border-white/5 bg-surface/30 backdrop-blur-xl shrink-0">
        <Link href="/" className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary-container text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            graphic_eq
          </span>
          <span className="font-headline text-3xl font-semibold text-primary-container tracking-tight">
            Synesthesia
          </span>
        </Link>
        <span className="text-xs px-3 py-1 rounded-full bg-secondary-container/15 text-on-secondary-container uppercase tracking-wider">
          Shared analysis
        </span>
      </nav>

      <main className="flex-grow px-6 md:px-16 py-10 max-w-[1024px] mx-auto w-full">
        <h1 className="font-headline text-5xl font-semibold text-on-surface mb-2">
          {a?.title || "Untitled"}
        </h1>
        <p className="text-on-surface-variant mb-8">{a?.artist || "Unknown artist"}</p>

        <div className="flex flex-wrap gap-3 mb-10">
          <span className="px-4 py-2 rounded-full glass-panel">
            <span className="text-xs text-on-surface-variant uppercase tracking-wider mr-2">Key</span>
            <span className="font-semibold text-on-surface">{a?.key}</span>
          </span>
          <span className="px-4 py-2 rounded-full glass-panel">
            <span className="text-xs text-on-surface-variant uppercase tracking-wider mr-2">BPM</span>
            <span className="font-semibold text-on-surface">{Math.round(a?.tempo ?? 0)}</span>
          </span>
          {a?.time_signature && (
            <span className="px-4 py-2 rounded-full glass-panel">
              <span className="text-xs text-on-surface-variant uppercase tracking-wider mr-2">Meter</span>
              <span className="font-semibold text-on-surface">{a.time_signature}</span>
            </span>
          )}
        </div>

        {a?.theory_explanation && (
          <section className="glass-panel rounded-xl p-6 mb-8">
            <h2 className="font-headline text-2xl text-on-surface mb-4">Harmonic analysis</h2>
            <p className="text-sm text-on-surface-variant whitespace-pre-line">{a.theory_explanation}</p>
          </section>
        )}

        {a?.roman?.progression && a.roman.progression.length > 0 && (
          <section className="glass-panel rounded-xl p-6 mb-8">
            <h2 className="font-headline text-2xl text-on-surface mb-4">Progression</h2>
            <p className="text-xl font-headline tracking-wider text-primary">
              {a.roman.progression.join(" → ")}
            </p>
          </section>
        )}

        {a?.chords && a.chords.length > 0 && (
          <section className="glass-panel rounded-xl p-6 mb-8">
            <h2 className="font-headline text-2xl text-on-surface mb-4">Chords</h2>
            <div className="flex flex-wrap gap-2">
              {a.chords.slice(0, 32).map((c, i) => (
                <span
                  key={i}
                  className="text-sm font-semibold px-3 py-1.5 rounded-md"
                  style={{ background: `${c.color}33`, color: c.color }}
                >
                  {c.chord}
                </span>
              ))}
              {a.chords.length > 32 && (
                <span className="text-xs text-on-surface-variant self-center">
                  +{a.chords.length - 32} more
                </span>
              )}
            </div>
          </section>
        )}

        <div className="text-center mt-12">
          <Link
            href="/"
            className="px-6 py-3 primary-gradient text-on-primary rounded-full font-semibold text-sm"
          >
            Analyze your own song
          </Link>
        </div>
      </main>
    </div>
  );
}
