"use client";

import React from "react";
import { ConfidenceDot } from "../Analysis/ConfidenceDot";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { useAppStore } from "../../store/useAppStore";
import { useFavoritesStore } from "../../store/useFavoritesStore";

export const Header: React.FC = () => {
  const { analysis, jobId } = useAnalysisStore();
  // ``useAppStore`` is intentionally not consumed here yet — kept as a
  // re-mount anchor for the planned ``setActiveTab("library")`` action when
  // the library page (Plan 3 A7) ships its breadcrumb in the header.
  void useAppStore;
  // Subscribe to the ids array so the icon re-renders on toggle. ``has()``
  // is a selector but doesn't trigger a re-render on its own.
  const favoriteIds = useFavoritesStore((s) => s.ids);
  const isFavorite = jobId ? favoriteIds.includes(jobId) : false;

  if (!analysis) return null;

  return (
    <header className="w-full px-3 sm:px-6 lg:px-16 py-3 sm:py-5 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 sm:gap-4 glass-panel border-b-0 border-white/5 sticky top-0 z-40 shrink-0">
      <div className="flex items-center gap-2 sm:gap-4 lg:gap-6 min-w-0 w-full sm:w-auto">
        <button
          className="w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center hover:bg-white/5 transition-colors group shrink-0"
          onClick={() => {
            // Close any in-flight progress SSE first, else its onDone could
            // later overwrite analysis/audioFileUrl for the song we're leaving.
            useAnalysisStore.getState().stopProgressStream();
            useAnalysisStore.getState().setAnalysis(null);
            useAnalysisStore.getState().setJobStatus("idle");
          }}
        >
          <span
            className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors"
            style={{ fontVariationSettings: "'wght' 300" }}
          >
            arrow_back_ios_new
          </span>
        </button>
        <div className="flex flex-col min-w-0">
          <h1 className="font-headline text-xl sm:text-2xl lg:text-4xl font-semibold tracking-tight text-white mb-0.5 truncate">
            {analysis.title || "Untitled"}
          </h1>
          <p className="text-on-surface-variant text-xs sm:text-sm truncate">
            {analysis.artist || "Unknown Artist"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1.5 sm:gap-3 lg:gap-4 overflow-x-auto hide-scrollbar shrink-0 max-w-full -mx-3 px-3 sm:mx-0 sm:px-0">
        {/* Key Badge */}
        <div className="px-3 py-1 rounded-full bg-white/5 border border-white/10 flex items-center gap-2 shrink-0">
          <span className="text-xs text-secondary-container tracking-wider uppercase font-medium">
            Key
          </span>
          <span className="text-sm font-semibold text-on-surface">
            {analysis.key || "—"}
          </span>
          <ConfidenceDot value={analysis.key_confidence} label="Key detection" />
        </div>
        {/* Tempo Badge */}
        <div className="px-3 py-1 rounded-full bg-white/5 border border-white/10 flex items-center gap-2 shrink-0">
          <span className="text-xs text-on-surface-variant tracking-wider uppercase font-medium">
            BPM
          </span>
          <span className="text-sm font-semibold text-on-surface">
            {Math.round(analysis.tempo) || "—"}
          </span>
          <ConfidenceDot value={analysis.tempo_confidence} label="Tempo detection" />
        </div>
        {/* Time Signature Badge */}
        <div className="px-3 py-1 rounded-full bg-white/5 border border-white/10 flex items-center gap-2 shrink-0">
          <span className="text-xs text-on-surface-variant tracking-wider uppercase font-medium">
            Time
          </span>
          <span className="text-sm font-semibold text-on-surface">
            {analysis.time_signature || "—"}
          </span>
          <ConfidenceDot value={analysis.time_signature_confidence} label="Meter detection" />
        </div>
        {/* Favorite Button */}
        <button
          className="w-10 h-10 sm:w-12 sm:h-12 rounded-full glass-panel flex items-center justify-center hover:inner-glow-focus transition-all group ml-1 sm:ml-2 shrink-0 disabled:opacity-40"
          onClick={() => {
            if (!jobId) return;
            const fav = useFavoritesStore.getState();
            if (fav.has(jobId)) fav.remove(jobId);
            else fav.add(jobId);
          }}
          disabled={!jobId}
          aria-pressed={isFavorite}
          aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
        >
          <span
            className="material-symbols-outlined text-primary-container"
            style={{
              fontVariationSettings: `'FILL' ${isFavorite ? 1 : 0}, 'wght' 400`,
            }}
          >
            favorite
          </span>
        </button>
      </div>
    </header>
  );
};
