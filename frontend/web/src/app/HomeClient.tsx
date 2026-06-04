"use client";

// HomeClient — the interactive shell for the / route.
// Extracted from app/page.tsx (Plan 2 F1) so the Next.js page boundary
// stays a Server Component. The whole tree under here is still rendered
// client-side because every panel uses Zustand hooks, but we no longer
// implicitly opt the page module out of server rendering. This also lets
// future server-fetched data (initial analysis, user prefs from D4) pass
// down as props without a hooks dance.

import React from "react";
import { useAppStore } from "../store/useAppStore";
import { useAnalysisStore } from "../store/useAnalysisStore";
import { UploadModal } from "../components/Upload/UploadModal";
import { AnalyzingView } from "../components/Analysis/AnalyzingView";
import { Header } from "../components/Layout/Header";
import { WaveformPlayer } from "../components/Player/WaveformPlayer";
import { ChordTimeline } from "../components/Analysis/ChordTimeline";
import { TheoryPanel } from "../components/Analysis/TheoryPanel";
import { PlayPanel } from "../components/Player/PlayPanel";
import { ChatPanel } from "../components/Chat/ChatPanel";
import { SettingsPanel } from "../components/Settings/SettingsPanel";
import { StemMixer } from "../components/Player/StemMixer";
import { BottomBar } from "../components/Player/BottomBar";
import { ToastContainer } from "../components/Layout/Toast";
import { LyricsPanel } from "../components/Lyrics/LyricsPanel";

const RIGHT_TABS = [
  { id: "play" as const, label: "PLAY" },
  { id: "theory" as const, label: "THEORY" },
  { id: "stems" as const, label: "STEMS" },
  { id: "lyrics" as const, label: "LYRICS" },
] as const;

export default function HomeClient() {
  const { activeTab, setActiveTab } = useAppStore();
  const { analysis, jobStatus } = useAnalysisStore();

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

  // Analyzing overlay
  if (isProcessing) {
    return (
      <>
        <UploadModal />
        <AnalyzingView />
        <ToastContainer />
      </>
    );
  }

  // Player View — Stitch 12-col grid layout
  return (
    <div className="flex flex-col h-screen bg-background pb-16">
      <Header />

      <div className="flex-grow overflow-hidden grid grid-cols-1 lg:grid-cols-12 gap-0">
        {/* Left Panel — Waveform, Chord Timeline (8 cols) */}
        <div className="lg:col-span-8 flex flex-col gap-0 p-6 lg:pr-3 overflow-y-auto hide-scrollbar">
          <WaveformPlayer />
          <div className="mt-4">
            <ChordTimeline />
          </div>
        </div>

        {/* Right Panel — Tabbed (4 cols) */}
        <div className="lg:col-span-4 flex flex-col glass-panel border-l border-white/5 border-t-0 border-r-0 border-b-0">
          {/* Tab Header */}
          <div className="flex border-b border-white/10 shrink-0">
            {RIGHT_TABS.map((tab) => (
              <button
                key={tab.id}
                className={`flex-1 py-4 text-center text-xs font-semibold tracking-widest transition-colors relative ${
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
              className={`flex-1 py-4 text-center text-xs font-semibold tracking-widest transition-colors relative ${
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
              className={`px-4 py-4 text-center transition-colors ${
                activeTab === "settings"
                  ? "text-on-surface"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
              onClick={() => setActiveTab("settings")}
            >
              <span className="material-symbols-outlined text-lg">settings</span>
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-grow overflow-hidden flex flex-col">
            {activeTab === "play" && <PlayPanel />}
            {activeTab === "theory" && <TheoryPanel />}
            {activeTab === "stems" && <StemMixer />}
            {activeTab === "lyrics" && <LyricsPanel />}
            {activeTab === "chat" && <ChatPanel />}
            {activeTab === "settings" && <SettingsPanel />}
          </div>
        </div>
      </div>

      <BottomBar />
      <ToastContainer />
    </div>
  );
}
