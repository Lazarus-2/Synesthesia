"use client";

// HomeClient — the interactive shell for the / route.
// Extracted from app/page.tsx (Plan 2 F1) so the Next.js page boundary
// stays a Server Component. The whole tree under here is still rendered
// client-side because every panel uses Zustand hooks, but we no longer
// implicitly opt the page module out of server rendering. This also lets
// future server-fetched data (initial analysis, user prefs from D4) pass
// down as props without a hooks dance.

import React, { useEffect } from "react";
import { useAppStore } from "../store/useAppStore";
import { useAnalysisStore } from "../store/useAnalysisStore";
import { useAuthStore } from "../store/useAuthStore";
import { UploadModal } from "../components/Upload/UploadModal";
import { AnalyzingView } from "../components/Analysis/AnalyzingView";
import { Header } from "../components/Layout/Header";
import { WaveformPlayer } from "../components/Player/WaveformPlayer";
import { ChordTimeline } from "../components/Analysis/ChordTimeline";
import { TheoryPanel } from "../components/Analysis/TheoryPanel";
import { ComparePanel } from "../components/Analysis/ComparePanel";
import { PlayPanel } from "../components/Player/PlayPanel";
import { ChatPanel } from "../components/Chat/ChatPanel";
import { SettingsPanel } from "../components/Settings/SettingsPanel";
import { StemMixer } from "../components/Player/StemMixer";
import { BottomBar } from "../components/Player/BottomBar";
import { ToastContainer } from "../components/Layout/Toast";
import { LyricsPanel } from "../components/Lyrics/LyricsPanel";
import { AuraRing } from "../components/Synesthesia/AuraRing";
import { ReharmSandbox } from "../components/Player/ReharmSandbox";
import { AudioEngine } from "../components/Player/AudioEngine";

const RIGHT_TABS = [
  { id: "play" as const, label: "PLAY" },
  { id: "theory" as const, label: "THEORY" },
  { id: "stems" as const, label: "STEMS" },
  { id: "lyrics" as const, label: "LYRICS" },
] as const;

export default function HomeClient() {
  const { activeTab, setActiveTab } = useAppStore();
  const { analysis, jobStatus } = useAnalysisStore();
  const loadAuth = useAuthStore((s) => s.loadFromStorage);

  // Rehydrate the JWT from localStorage once on mount so an authed user who
  // hard-reloads the player keeps the chat tab unlocked (no sign-in flash).
  useEffect(() => {
    loadAuth();
  }, [loadAuth]);

  // Show analyzing overlay when processing
  const isProcessing = jobStatus === "queued" || jobStatus === "processing" || jobStatus === "error";

  // Landing page (no analysis loaded)
  if (!analysis && !isProcessing) {
    return (
      <>
        <UploadModal />
        <ToastContainer />
      </>
    );
  }

  // Analyzing overlay. Render ONLY AnalyzingView — UploadModal is an opaque
  // fixed z-50 layer and (since `analysis` is still null while processing) it
  // would render ON TOP of the z-40 AnalyzingView, hiding the progress bar.
  if (isProcessing) {
    return (
      <>
        <AnalyzingView />
        <ToastContainer />
      </>
    );
  }

  // Player View — Stitch 12-col grid layout
  return (
    <div className="relative flex flex-col h-screen bg-background pb-16">
      {/* Scriabin Aura Ring — fixed full-screen glow behind the UI. */}
      <AuraRing />

      <div className="relative z-10 flex flex-col h-full">
      <Header />

      {/* On mobile the two panels STACK and the whole area scrolls (with bottom
          padding so content clears the fixed transport bar); on lg+ it's a
          fixed-height 12-col split where each panel scrolls independently. */}
      <div className="flex-grow grid grid-cols-1 lg:grid-cols-12 gap-0 overflow-y-auto lg:overflow-hidden pb-24 lg:pb-0">
        {/* Left Panel — Waveform, Chord Timeline (8 cols) */}
        <div className="lg:col-span-8 flex flex-col gap-0 p-4 lg:p-6 lg:pr-3 lg:overflow-y-auto hide-scrollbar reveal-up">
          <WaveformPlayer />
          <div className="mt-4">
            <ChordTimeline />
          </div>
        </div>

        {/* Right Panel — Tabbed (4 cols). Mobile: a tall, self-contained panel
            below the waveform; lg+: fills the column height. */}
        <div
          className="lg:col-span-4 flex flex-col glass-panel border-t border-l-0 lg:border-l lg:border-t-0 border-white/5 border-r-0 border-b-0 min-h-[70vh] lg:min-h-0 reveal-up"
          style={{ animationDelay: "0.12s" }}
        >
          {/* Tab Header */}
          <div role="tablist" aria-label="Analysis panels" className="flex border-b border-white/10 shrink-0">
            {RIGHT_TABS.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls="analysis-tabpanel"
                className={`flex-1 py-4 text-center text-xs font-semibold tracking-widest transition-colors relative focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${
                  activeTab === tab.id
                    ? "text-on-surface"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
                {activeTab === tab.id && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary-container" />
                )}
              </button>
            ))}
            {/* Extra tabs outside the "Play/Theory/Stems" group */}
            <button
              role="tab"
              aria-selected={activeTab === "compare"}
              aria-controls="analysis-tabpanel"
              className={`flex-1 py-4 text-center text-xs font-semibold tracking-widest transition-colors relative focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${
                activeTab === "compare"
                  ? "text-on-surface"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
              onClick={() => setActiveTab("compare")}
            >
              COMPARE
              {activeTab === "compare" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary-container" />
              )}
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "chat"}
              aria-controls="analysis-tabpanel"
              className={`flex-1 py-4 text-center text-xs font-semibold tracking-widest transition-colors relative focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${
                activeTab === "chat"
                  ? "text-on-surface"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
              onClick={() => setActiveTab("chat")}
            >
              CHAT
              {activeTab === "chat" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-secondary-container" />
              )}
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "settings"}
              aria-controls="analysis-tabpanel"
              aria-label="Settings"
              className={`px-4 py-4 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${
                activeTab === "settings"
                  ? "text-on-surface"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
              onClick={() => setActiveTab("settings")}
            >
              <span className="material-symbols-outlined text-lg">settings</span>
            </button>
          </div>

          {/* Tab Content — keyed by tab so each panel fades in on switch */}
          <div id="analysis-tabpanel" role="tabpanel" key={activeTab} className="flex-grow overflow-hidden flex flex-col fade-in">
            {activeTab === "play" && <PlayPanel />}
            {activeTab === "theory" && <TheoryPanel />}
            {activeTab === "stems" && <StemMixer />}
            {activeTab === "lyrics" && <LyricsPanel />}
            {activeTab === "compare" && <ComparePanel />}
            {activeTab === "chat" && <ChatPanel />}
            {activeTab === "settings" && <SettingsPanel />}
          </div>
        </div>
      </div>

      <BottomBar />
      <ToastContainer />
      </div>
      <ReharmSandbox />
      <AudioEngine />
    </div>
  );
}
