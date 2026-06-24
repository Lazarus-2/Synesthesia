"use client";

import React, { useState } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { useToastStore } from "../../store/useToastStore";
import { apiGet, ApiError } from "../../lib/apiClient";
import { compareAnalyses, type ComparisonResult, type KeyRelationship } from "../../lib/compare";
import { getChordColor } from "../../lib/music";
import type { SongAnalysis } from "../../types";

// Minimal library item shape — mirrors backend ``LibraryEntry`` (only the
// fields the picker renders).
interface LibraryItem {
  job_id: string;
  title: string | null;
  artist: string | null;
  key: string;
  tempo: number;
}

const REL_LABEL: Record<KeyRelationship, string> = {
  same: "Same key",
  relative: "Relative key",
  parallel: "Parallel key",
  different: "Different key",
};

const REL_CLS: Record<KeyRelationship, string> = {
  same: "bg-secondary-container/15 text-on-secondary-container border-secondary-container/30",
  relative: "bg-primary/10 text-primary border-primary/30",
  parallel: "bg-tertiary/10 text-on-surface-variant border-tertiary/30",
  different: "bg-white/5 text-on-surface-variant border-white/10",
};

function ChordChip({ chord }: { chord: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-white/5 border border-white/10 text-on-surface"
    >
      <span
        className="w-2 h-2 rounded-full"
        style={{ backgroundColor: getChordColor(chord) }}
        aria-hidden
      />
      {chord}
    </span>
  );
}

function NumeralChip({ numeral }: { numeral: string }) {
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20">
      {numeral}
    </span>
  );
}

function SongColumn({ label, song }: { label: string; song: { title?: string; artist?: string; key: string; tempo: number } }) {
  return (
    <div className="flex-1 min-w-0">
      <p className="text-[10px] uppercase font-semibold tracking-widest text-on-surface-variant mb-1">
        {label}
      </p>
      <p className="font-headline text-base text-on-surface line-clamp-1">
        {song.title || "Untitled"}
      </p>
      <p className="text-xs text-on-surface-variant line-clamp-1">
        {song.artist || "Unknown artist"}
      </p>
    </div>
  );
}

export const ComparePanel: React.FC = () => {
  const analysisA = useAnalysisStore((s) => s.analysis);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [songBLoading, setSongBLoading] = useState(false);
  const [songB, setSongB] = useState<SongAnalysis | null>(null);

  if (!analysisA) {
    return (
      <div className="flex-grow p-6 flex items-center justify-center text-on-surface-variant text-sm">
        Analyze a song first.
      </div>
    );
  }

  const openPicker = async () => {
    setPickerOpen(true);
    if (items !== null || listLoading) return;
    setListLoading(true);
    try {
      const resp = await apiGet<{ items: LibraryItem[] }>("/library?limit=100");
      setItems(resp.items ?? []);
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Could not load library.";
      useToastStore.getState().error("Library failed to load", message);
      setItems([]);
    } finally {
      setListLoading(false);
    }
  };

  const pickSong = async (jobId: string) => {
    setSongBLoading(true);
    setPickerOpen(false);
    try {
      const resp = await apiGet<{ analysis?: SongAnalysis }>(`/analyze/${encodeURIComponent(jobId)}`);
      if (!resp.analysis) throw new ApiError(404, "Analysis not available for that song.");
      setSongB(resp.analysis);
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Could not load that song.";
      useToastStore.getState().error("Compare failed", message);
    } finally {
      setSongBLoading(false);
    }
  };

  const result: ComparisonResult | null = songB ? compareAnalyses(analysisA, songB) : null;

  return (
    <div className="flex flex-col gap-6 p-6 overflow-y-auto hide-scrollbar flex-grow">
      <div className="flex items-center justify-between">
        <h2 className="font-headline text-2xl font-medium text-white">Compare</h2>
        <button
          type="button"
          onClick={openPicker}
          className="px-3 py-1.5 rounded-full text-xs font-semibold tracking-wide glass-panel border border-white/10 text-on-surface-variant hover:text-on-surface hover:border-primary/30 transition-colors"
        >
          {songB ? "Change song B" : "Pick a song"}
        </button>
      </div>

      {/* Song-B picker list */}
      {pickerOpen && (
        <div className="glass-panel rounded-xl border border-white/10 max-h-72 overflow-y-auto hide-scrollbar">
          {listLoading && (
            <div className="p-4 text-sm text-on-surface-variant">Loading library…</div>
          )}
          {!listLoading && items && items.length === 0 && (
            <div className="p-4 text-sm text-on-surface-variant">No songs in your library yet.</div>
          )}
          {!listLoading && items && items.length > 0 && (
            <ul className="divide-y divide-white/5">
              {items.map((it) => (
                <li key={it.job_id}>
                  <button
                    type="button"
                    onClick={() => pickSong(it.job_id)}
                    className="w-full text-left px-4 py-3 hover:bg-white/5 transition-colors flex items-center gap-3"
                  >
                    <div className="flex-grow min-w-0">
                      <p className="text-sm text-on-surface line-clamp-1">{it.title || "Untitled"}</p>
                      <p className="text-xs text-on-surface-variant line-clamp-1">
                        {it.artist || "Unknown artist"}
                      </p>
                    </div>
                    <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-1 rounded bg-secondary-container/15 text-on-secondary-container shrink-0">
                      {it.key}
                    </span>
                    <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-1 rounded bg-white/5 text-on-surface-variant shrink-0">
                      {Math.round(it.tempo)} BPM
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {songBLoading && (
        <div className="glass-panel rounded-xl h-40 animate-pulse-glow" />
      )}

      {!songB && !songBLoading && !pickerOpen && (
        <div className="flex-grow flex items-center justify-center text-on-surface-variant text-sm text-center">
          Pick a second song to compare against the current analysis.
        </div>
      )}

      {result && songB && (
        <>
          {/* Header columns */}
          <div className="flex items-start gap-4 bg-surface-container-high rounded-lg p-4 border border-white/5">
            <SongColumn label="Song A" song={analysisA} />
            <span className="material-symbols-outlined text-on-surface-variant pt-4">compare_arrows</span>
            <SongColumn label="Song B" song={songB} />
          </div>

          {/* Key */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest">
                Key
              </h3>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${REL_CLS[result.keyRelationship]}`}
              >
                {REL_LABEL[result.keyRelationship]}
              </span>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <span className="flex-1 text-on-surface">{analysisA.key}</span>
              <span className="flex-1 text-on-surface">{songB.key}</span>
            </div>
          </div>

          {/* Tempo */}
          <div>
            <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
              Tempo
            </h3>
            <div className="flex items-center gap-4 text-sm">
              <span className="flex-1 text-on-surface">{Math.round(analysisA.tempo)} BPM</span>
              <span className="flex-1 text-on-surface">
                {Math.round(songB.tempo)} BPM
                <span className="ml-2 text-xs text-on-surface-variant">
                  ({result.tempoDelta >= 0 ? "+" : ""}{result.tempoDelta})
                </span>
              </span>
            </div>
          </div>

          {/* Meter + Form */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
                Meter
              </h3>
              <div className="flex items-center gap-2 text-sm text-on-surface">
                <span>{analysisA.time_signature ?? "4/4"}</span>
                <span className="text-on-surface-variant">vs</span>
                <span>{songB.time_signature ?? "4/4"}</span>
                {result.sameMeter && (
                  <span className="material-symbols-outlined text-sm text-secondary-container">check</span>
                )}
              </div>
            </div>
            <div>
              <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
                Form
              </h3>
              <div className="flex flex-col text-sm text-on-surface">
                <span>{result.formA}</span>
                <span className="text-on-surface-variant">{result.formB}</span>
              </div>
            </div>
          </div>

          {/* Shared chords */}
          <div>
            <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
              Shared chords ({result.sharedChords.length})
            </h3>
            {result.sharedChords.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {result.sharedChords.map((c) => (
                  <ChordChip key={c} chord={c} />
                ))}
              </div>
            ) : (
              <p className="text-xs text-on-surface-variant">No chords in common.</p>
            )}
          </div>

          {/* Shared numerals */}
          <div>
            <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
              Shared progressions ({result.sharedNumerals.length})
            </h3>
            {result.sharedNumerals.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {result.sharedNumerals.map((n) => (
                  <NumeralChip key={n} numeral={n} />
                ))}
              </div>
            ) : (
              <p className="text-xs text-on-surface-variant">No Roman numerals in common.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
};
