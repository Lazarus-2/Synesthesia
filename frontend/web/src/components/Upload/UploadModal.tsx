"use client";

import React, { useRef, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";
import { apiPostForm, ApiError } from "../../lib/apiClient";
import { useToastStore } from "../../store/useToastStore";
import type { AnalyzeResponse } from "../../types";
import { classifyUrl, PlatformBadge, type Platform } from "./PlatformBadge";
import { SearchPanel } from "./SearchPanel";

const INSTRUMENTS = ["guitar", "piano", "ukulele", "bass"] as const;
const DIFFICULTIES = ["beginner", "intermediate", "advanced"] as const;
type Instrument = (typeof INSTRUMENTS)[number];
type Difficulty = (typeof DIFFICULTIES)[number];
type InputMode = "upload" | "search";

const INSTRUMENT_ICONS: Record<Instrument, string> = {
  guitar: "music_note",
  piano: "piano",
  ukulele: "graphic_eq",
  bass: "speaker",
};

// Sample analysis cards — IDs must match the seed script
// (``scripts/seed_samples.py``). Each card links to ``/s/{job_id}`` which
// renders the read-only share page.
const SAMPLE_CARDS = [
  {
    id: "sample-blackbird",
    title: "Blackbird",
    artist: "The Beatles",
    key: "G Major",
    bpm: "96",
    color: "bg-secondary-container/80",
    icons: ["piano", "music_note"],
  },
  {
    id: "sample-wonderwall",
    title: "Wonderwall",
    artist: "Oasis",
    key: "F# Minor",
    bpm: "87",
    color: "bg-secondary-container/80",
    icons: ["music_note"],
  },
  {
    id: "sample-creep",
    title: "Creep",
    artist: "Radiohead",
    key: "G Major",
    bpm: "92",
    color: "bg-secondary-container/80",
    icons: ["music_note", "speaker"],
  },
];

export const UploadModal: React.FC = () => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [inputMode, setInputMode] = useState<InputMode>("upload");
  const [instrument, setInstrument] = useState<Instrument>("guitar");
  const [difficulty, setDifficulty] = useState<Difficulty>("beginner");
  const { analysis, startProgressStream } = useAnalysisStore();
  const { setAudioFileUrl } = usePlayerStore();

  // Live smart-detect for the URL input — shows a platform badge + ✓/⚠ as
  // the user types so they know whether the backend will accept the URL.
  const detectedPlatform: Platform = useMemo(() => classifyUrl(youtubeUrl), [youtubeUrl]);

  // All hooks declared at the top so the order is stable on every render.
  // Previously several useCallbacks lived after the early-return below,
  // which tripped react-hooks/rules-of-hooks.
  const submitAnalyze = useCallback(async (form: FormData, audioUrl?: string) => {
    setSubmitError(null);
    try {
      const data = await apiPostForm<AnalyzeResponse>("/analyze", form);
      // Uploads pass a local blob URL (instant playback); URL/search analyses
      // pass none — reset to null so the store fills it from the backend
      // /audio/{jobId} on done instead of reusing a previous song's audio.
      setAudioFileUrl(audioUrl ?? null);
      if (data.status === "done" && data.analysis) {
        useAnalysisStore.getState().setAnalysis(data.analysis);
      } else if (data.job_id) {
        startProgressStream(data.job_id);
      }
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message :
        err instanceof Error ? err.message : "Unknown error";
      const detail = err instanceof ApiError ? err.code : undefined;
      console.error("analyze error:", err);
      setSubmitError(message);
      useToastStore.getState().error("Upload failed", `${detail ? detail + ' — ' : ''}${message}`);
    }
  }, [startProgressStream, setAudioFileUrl]);

  const handleUpload = useCallback(async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("instrument", instrument);
    form.append("difficulty", difficulty);
    await submitAnalyze(form, URL.createObjectURL(file));
  }, [submitAnalyze, instrument, difficulty]);

  const handleYoutubeAnalyze = useCallback(async () => {
    const trimmed = youtubeUrl.trim();
    if (!trimmed) return;

    // Pre-flight validation (Plan 3 live-test report 2): when the user
    // pastes a local file path or a non-URL string the server's URL guard
    // rejects it anyway, but we get a clearer message by catching it here
    // and the user doesn't see "Analyzing…" → "Analysis failed" round-trip.
    let parsed: URL | null = null;
    try {
      parsed = new URL(trimmed);
    } catch {
      const message = "That doesn't look like a URL. Drop an audio file above or paste a YouTube link.";
      setSubmitError(message);
      useToastStore.getState().error("Invalid URL", message);
      return;
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      const message = `Only http(s) URLs are accepted (got ${parsed.protocol}).`;
      setSubmitError(message);
      useToastStore.getState().error("Invalid URL scheme", message);
      return;
    }
    // Frontend allowlist mirrors the backend SSRF guard exactly. YouTube
    // (regular + music) and Spotify URLs are accepted; everything else
    // is rejected early so the user doesn't wait for the round-trip.
    const platform = classifyUrl(trimmed);
    if (platform === "unknown") {
      const message = `${parsed.hostname} isn't supported. Paste a YouTube, YouTube Music, or Spotify URL — or upload an audio file.`;
      setSubmitError(message);
      useToastStore.getState().error("Unsupported host", message);
      return;
    }

    const form = new FormData();
    form.append("youtube_url", trimmed);
    form.append("instrument", instrument);
    form.append("difficulty", difficulty);
    await submitAnalyze(form);
  }, [youtubeUrl, submitAnalyze, instrument, difficulty]);

  // Search picks: synthesize a query string the backend resolves via
  // ytsearch1: under the hood, reusing the existing URL flow.
  const handleSearchPick = useCallback(async (query: string) => {
    const form = new FormData();
    // ``ytsearch1:`` prefix tells the backend's yt-dlp invocation to do a
    // YouTube search and grab the top result. Existing pipeline does the rest.
    form.append("youtube_url", `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`);
    form.append("instrument", instrument);
    form.append("difficulty", difficulty);
    await submitAnalyze(form);
  }, [submitAnalyze, instrument, difficulty]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }, [handleUpload]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
  }, [handleUpload]);

  // If analysis is already loaded, don't show landing.
  if (analysis) return null;

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col min-h-screen overflow-y-auto">
      {/* Top Nav */}
      <nav className="w-full px-16 h-20 flex justify-between items-center border-b border-white/5 bg-surface/30 backdrop-blur-xl shrink-0">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary-container text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            graphic_eq
          </span>
          <span className="font-headline text-4xl font-semibold text-primary-container tracking-tight">
            Synesthesia
          </span>
        </div>
        <div className="hidden md:flex items-center gap-8">
          <a href="/library" className="text-on-surface-variant hover:text-primary transition-colors">Library</a>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-grow flex flex-col items-center justify-center px-5 md:px-16 max-w-[1280px] mx-auto w-full relative z-10 py-12">
        {/* Hero */}
        <div className="text-center max-w-3xl mb-12">
          <h1 className="font-headline text-5xl md:text-[64px] md:leading-[1.1] font-semibold text-on-surface mb-6 tracking-tight">
            Hear any song. <br className="hidden md:block" />
            <span className="primary-gradient-text">Play any song.</span>
          </h1>
          <p className="text-lg text-on-surface-variant max-w-2xl mx-auto leading-relaxed">
            Studio-grade AI analysis extracts exact chords, stems, and structures from any audio file or YouTube link in seconds.
          </p>
        </div>

        {/* Upload & Input Zone */}
        <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-12 gap-6 mb-16">
          {/* Drag & Drop Area */}
          <div
            className={`md:col-span-12 glass-panel rounded-xl p-8 md:p-12 border-dashed border-2 transition-colors flex flex-col items-center justify-center text-center cursor-pointer group min-h-[300px] relative overflow-hidden ${
              isDragging ? "border-primary-container/70" : "border-outline/30 hover:border-primary/50"
            }`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            {/* Waveform Background Bars */}
            <div className="absolute inset-0 opacity-15 pointer-events-none flex items-center justify-center gap-1 w-full px-4" aria-hidden="true">
              {[8, 16, 24, 12, 32, 20, 40, 16, 28, 10].map((h, i) => (
                <div key={i} className="w-2 bg-primary rounded-full" style={{ height: `${h}px` }} />
              ))}
            </div>

            <div className="h-20 w-20 rounded-full glass-panel flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 relative z-10 shadow-[0_0_30px_rgba(255,181,71,0.15)]">
              <span className="material-symbols-outlined text-4xl text-primary" style={{ fontVariationSettings: "'FILL' 0" }}>
                upload_file
              </span>
            </div>
            <h3 className="font-headline text-2xl font-medium text-on-surface mb-2 relative z-10">
              Drag &amp; Drop Audio
            </h3>
            <p className="text-on-surface-variant relative z-10">
              MP3, WAV, FLAC or AIFF up to 50MB
            </p>

            <input
              ref={inputRef}
              type="file"
              accept="audio/*"
              onChange={handleFileChange}
              className="hidden"
            />
            {submitError && (
              <p className="mt-4 text-sm text-error relative z-10" role="alert">
                {submitError}
              </p>
            )}
          </div>

          {/* URL Input (with smart-detect platform badge) — only shown in upload mode */}
          {inputMode === "upload" && (
            <div className="md:col-span-12 glass-panel rounded-xl p-2 flex flex-col sm:flex-row items-center gap-2 glow-focus">
              <div className="flex items-center flex-grow pl-4 py-2 w-full">
                <span className="material-symbols-outlined text-outline mr-3">link</span>
                <input
                  className="bg-transparent border-none w-full text-on-surface focus:ring-0 focus:outline-none placeholder:text-outline-variant p-0"
                  placeholder="Paste a YouTube, YouTube Music, or Spotify URL..."
                  type="text"
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleYoutubeAnalyze()}
                />
                {youtubeUrl.trim() && (
                  <div className="mr-3 shrink-0">
                    <PlatformBadge platform={detectedPlatform} />
                  </div>
                )}
              </div>
              <button
                className="primary-gradient text-on-primary font-semibold text-sm px-6 py-4 rounded-lg w-full sm:w-auto whitespace-nowrap hover:opacity-90 transition-opacity flex items-center justify-center gap-2 tracking-wider uppercase disabled:opacity-50"
                onClick={handleYoutubeAnalyze}
                disabled={!youtubeUrl.trim() || detectedPlatform === "unknown"}
              >
                <span className="material-symbols-outlined text-lg">auto_awesome</span>
                Paste &amp; Analyze
              </button>
            </div>
          )}

          {/* Search mode — Deezer + MusicBrainz */}
          {inputMode === "search" && (
            <SearchPanel onPick={handleSearchPick} />
          )}

          {/* Mode toggle */}
          <div className="md:col-span-12 flex justify-center -mt-2">
            <div className="inline-flex rounded-full glass-panel p-1 text-xs">
              {(["upload", "search"] as const).map((m) => (
                <button
                  key={m}
                  className={`px-4 py-1.5 rounded-full uppercase tracking-wider font-semibold transition-colors ${
                    inputMode === m
                      ? "primary-gradient text-on-primary"
                      : "text-on-surface-variant hover:text-on-surface"
                  }`}
                  onClick={() => setInputMode(m)}
                >
                  {m === "upload" ? "Upload / URL" : "Search Songs"}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Instrument + difficulty chips — now interactive, drive analyze params */}
        <div className="flex flex-wrap items-center justify-center gap-4 mb-24">
          <span className="text-on-surface-variant text-xs uppercase tracking-wider font-medium">Instrument</span>
          {INSTRUMENTS.map((inst) => (
            <button
              key={inst}
              type="button"
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-xs font-medium transition-colors uppercase tracking-wider ${
                instrument === inst
                  ? "primary-gradient text-on-primary border border-transparent"
                  : "glass-panel text-on-surface hover:border-primary/30 border border-outline/20"
              }`}
              onClick={() => setInstrument(inst)}
              aria-pressed={instrument === inst}
            >
              <span className="material-symbols-outlined text-[16px]">{INSTRUMENT_ICONS[inst]}</span>
              {inst}
            </button>
          ))}
          <span className="text-on-surface-variant text-xs uppercase tracking-wider font-medium ml-4">Level</span>
          {DIFFICULTIES.map((d) => (
            <button
              key={d}
              type="button"
              className={`px-4 py-2 rounded-full text-xs font-medium transition-colors uppercase tracking-wider ${
                difficulty === d
                  ? "primary-gradient text-on-primary border border-transparent"
                  : "glass-panel text-on-surface hover:border-primary/30 border border-outline/20"
              }`}
              onClick={() => setDifficulty(d)}
              aria-pressed={difficulty === d}
            >
              {d}
            </button>
          ))}
        </div>

        {/* Sample Section */}
        <div className="w-full">
          <h4 className="font-headline text-2xl font-medium text-on-surface mb-8 text-center md:text-left">
            Try a Sample Analysis
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {SAMPLE_CARDS.map((card) => (
              <Link
                key={card.id}
                href={`/s/${card.id}`}
                className="glass-panel rounded-xl overflow-hidden group cursor-pointer hover:border-primary/30 transition-all flex flex-col"
              >
                <div className="h-40 w-full relative overflow-hidden bg-surface-container-high">
                  <div className="absolute inset-0 bg-gradient-to-b from-transparent to-background" />
                  <div className="absolute bottom-4 left-4 flex gap-2">
                    <span className={`${card.color} text-on-secondary-container px-2 py-1 rounded text-[10px] font-semibold uppercase tracking-wider backdrop-blur-md`}>
                      {card.key}
                    </span>
                    <span className="bg-surface/80 text-on-surface px-2 py-1 rounded text-[10px] font-semibold uppercase tracking-wider border border-white/10 backdrop-blur-md">
                      {card.bpm} BPM
                    </span>
                  </div>
                </div>
                <div className="p-6">
                  <h5 className="font-headline text-xl font-medium text-on-surface mb-1">{card.title}</h5>
                  <p className="text-on-surface-variant mb-4">{card.artist}</p>
                  <div className="flex items-center justify-between mt-auto">
                    <div className="flex -space-x-2">
                      {card.icons.map((ic, i) => (
                        <div key={i} className="w-6 h-6 rounded-full bg-surface-container border border-white/10 flex items-center justify-center">
                          <span className="material-symbols-outlined text-[12px] text-primary">{ic}</span>
                        </div>
                      ))}
                    </div>
                    <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">play_circle</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
          <p className="text-xs text-outline-variant text-center mt-4">
            First time? Run <code className="font-mono text-on-surface-variant">python scripts/seed_samples.py</code> to populate these samples.
          </p>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-surface-container-lowest w-full py-12 border-t border-white/5 mt-auto shrink-0">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 px-5 md:px-16 max-w-[1280px] mx-auto">
          <div className="flex flex-col">
            <span className="font-headline text-2xl font-medium text-on-surface mb-2">Synesthesia</span>
            <span className="text-xs text-on-surface-variant font-medium">
              © 2024 Synesthesia AI · ML-powered chords, key, stems &amp; theory.
            </span>
          </div>
          <div className="flex items-center gap-6">
            <a href="/library" className="text-xs text-on-surface-variant hover:text-primary-container transition-colors font-medium">Library</a>
            <a
              href="https://github.com/spotify/basic-pitch"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-on-surface-variant hover:text-primary-container transition-colors font-medium"
            >
              Built on open-source ML
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};
