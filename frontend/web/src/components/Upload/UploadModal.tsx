"use client";

import React, { useRef, useState, useCallback } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const UploadModal: React.FC = () => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const { analysis, startProgressStream } = useAnalysisStore();
  const { setAudioFileUrl } = usePlayerStore();

  // If analysis is already loaded, don't show landing
  if (analysis) return null;

  const handleUpload = useCallback(async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("instrument", "guitar");
    form.append("difficulty", "beginner");

    try {
      const res = await fetch(`${API}/analyze`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      const data = await res.json();

      // Set audio URL for player
      setAudioFileUrl(URL.createObjectURL(file));

      if (data.status === "done" && data.analysis) {
        useAnalysisStore.getState().setAnalysis(data.analysis);
      } else if (data.job_id) {
        startProgressStream(data.job_id);
      }
    } catch (err) {
      console.error("Upload error:", err);
    }
  }, [startProgressStream, setAudioFileUrl]);

  const handleYoutubeAnalyze = useCallback(async () => {
    if (!youtubeUrl.trim()) return;
    const form = new FormData();
    form.append("youtube_url", youtubeUrl.trim());
    form.append("instrument", "guitar");
    form.append("difficulty", "beginner");

    try {
      const res = await fetch(`${API}/analyze`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`Analyze failed: ${res.status}`);
      const data = await res.json();

      if (data.status === "done" && data.analysis) {
        useAnalysisStore.getState().setAnalysis(data.analysis);
      } else if (data.job_id) {
        startProgressStream(data.job_id);
      }
    } catch (err) {
      console.error("YouTube analyze error:", err);
    }
  }, [youtubeUrl, startProgressStream]);

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
          <a href="#" className="text-on-surface-variant hover:text-primary transition-colors">Library</a>
          <a href="#" className="text-on-surface-variant hover:text-primary transition-colors">Pricing</a>
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
          </div>

          {/* YouTube URL Input */}
          <div className="md:col-span-12 glass-panel rounded-xl p-2 flex flex-col sm:flex-row items-center gap-2 glow-focus">
            <div className="flex items-center flex-grow pl-4 py-2 w-full">
              <span className="material-symbols-outlined text-outline mr-3">link</span>
              <input
                className="bg-transparent border-none w-full text-on-surface focus:ring-0 focus:outline-none placeholder:text-outline-variant p-0"
                placeholder="Paste YouTube or SoundCloud URL..."
                type="text"
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleYoutubeAnalyze()}
              />
            </div>
            <button
              className="primary-gradient text-on-primary font-semibold text-sm px-6 py-4 rounded-lg w-full sm:w-auto whitespace-nowrap hover:opacity-90 transition-opacity flex items-center justify-center gap-2 tracking-wider uppercase"
              onClick={handleYoutubeAnalyze}
              disabled={!youtubeUrl.trim()}
            >
              <span className="material-symbols-outlined text-lg">auto_awesome</span>
              Paste &amp; Analyze
            </button>
          </div>
        </div>

        {/* Instrument Chips */}
        <div className="flex flex-wrap items-center justify-center gap-3 mb-24">
          <span className="text-on-surface-variant text-xs uppercase tracking-wider mr-2 font-medium">Detecting for:</span>
          {[
            { icon: "music_note", label: "Guitar" },
            { icon: "piano", label: "Piano" },
            { icon: "graphic_eq", label: "Ukulele" },
            { icon: "speaker", label: "Bass" },
          ].map(({ icon, label }) => (
            <div key={label} className="flex items-center gap-2 px-4 py-2 rounded-full glass-panel">
              <span className="material-symbols-outlined text-[16px] text-primary">{icon}</span>
              <span className="text-xs font-medium text-on-surface">{label}</span>
            </div>
          ))}
        </div>

        {/* Sample Section */}
        <div className="w-full">
          <h4 className="font-headline text-2xl font-medium text-on-surface mb-8 text-center md:text-left">
            Try a Sample Analysis
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { title: "Blackbird", artist: "The Beatles", key: "G Major", bpm: "120", color: "bg-secondary-container/80", icons: ["piano", "music_note"] },
              { title: "Wonderwall", artist: "Oasis", key: "E Minor", bpm: "94", color: "bg-secondary-container/80", icons: ["music_note"] },
              { title: "Creep", artist: "Radiohead", key: "C Major", bpm: "78", color: "bg-secondary-container/80", icons: ["music_note", "speaker"] },
            ].map((card) => (
              <div key={card.title} className="glass-panel rounded-xl overflow-hidden group cursor-pointer hover:border-primary/30 transition-all flex flex-col">
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
              </div>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-surface-container-lowest w-full py-12 border-t border-white/5 mt-auto shrink-0">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 px-5 md:px-16 max-w-[1280px] mx-auto">
          <div className="flex flex-col mb-8 md:mb-0">
            <span className="font-headline text-2xl font-medium text-on-surface mb-4">Synesthesia</span>
            <span className="text-xs text-on-surface-variant font-medium">© 2024 Synesthesia AI. Studio-Grade Analysis.</span>
          </div>
          <div className="flex flex-col gap-3">
            <a href="#" className="text-xs text-on-surface-variant hover:text-primary-container transition-colors font-medium">Terms of Service</a>
            <a href="#" className="text-xs text-on-surface-variant hover:text-primary-container transition-colors font-medium">Privacy Policy</a>
            <a href="#" className="text-xs text-on-surface-variant hover:text-primary-container transition-colors font-medium">Documentation</a>
          </div>
          <div className="flex flex-col gap-3">
            <a href="#" className="text-xs text-on-surface-variant hover:text-primary-container transition-colors font-medium">Support</a>
            <a href="#" className="text-xs text-on-surface-variant hover:text-primary-container transition-colors font-medium">API</a>
            <a href="#" className="text-xs text-on-surface-variant hover:text-primary-container transition-colors font-medium">Community</a>
          </div>
        </div>
      </footer>
    </div>
  );
};
