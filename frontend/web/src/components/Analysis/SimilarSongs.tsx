"use client";

import React from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import type { SimilarSong } from "../../types";

const SourceBadge: React.FC<{ source: string }> = ({ source }) => (
  <span className="text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-white/10 text-on-surface-variant">
    {source}
  </span>
);

const MatchBar: React.FC<{ match: number | null }> = ({ match }) => {
  if (match == null) return null;
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-grow h-1 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-primary/60 to-primary rounded-full"
          style={{ width: `${Math.round(match * 100)}%` }}
        />
      </div>
      <span className="text-[9px] text-on-surface-variant tabular-nums w-8 text-right">
        {Math.round(match * 100)}%
      </span>
    </div>
  );
};

const SimilarSongRow: React.FC<{ song: SimilarSong }> = ({ song }) => (
  <li className="flex items-center gap-3 py-3 border-b border-white/5 last:border-b-0">
    {/* Thumbnail — plain <img> because external URLs have unknown domains at
        build time and cannot be added to next.config remotePatterns.
        ESLint @next/next/no-img-element is suppressed intentionally. */}
    {song.image ? (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={song.image}
        alt={`${song.title} cover`}
        width={40}
        height={40}
        className="w-10 h-10 rounded-md object-cover flex-shrink-0 bg-surface-container-high"
      />
    ) : (
      <div className="w-10 h-10 rounded-md bg-surface-container-high flex items-center justify-center flex-shrink-0">
        <span className="material-symbols-outlined text-on-surface-variant text-lg">
          music_note
        </span>
      </div>
    )}

    {/* Text */}
    <div className="flex-grow min-w-0">
      <div className="flex items-center gap-2 flex-wrap">
        {song.url ? (
          <a
            href={song.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-semibold text-on-surface hover:text-primary transition-colors truncate"
          >
            {song.title}
          </a>
        ) : (
          <span className="text-sm font-semibold text-on-surface truncate">{song.title}</span>
        )}
        <SourceBadge source={song.source} />
      </div>
      <p className="text-xs text-on-surface-variant truncate">{song.artist}</p>
      <MatchBar match={song.match} />
    </div>

    {/* External link icon */}
    {song.url && (
      <a
        href={song.url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex-shrink-0 text-on-surface-variant hover:text-primary transition-colors"
        aria-label={`Open ${song.title} externally`}
      >
        <span className="material-symbols-outlined text-base">open_in_new</span>
      </a>
    )}
  </li>
);

export const SimilarSongs: React.FC = () => {
  const { analysis } = useAnalysisStore();

  if (!analysis?.similar_songs || analysis.similar_songs.length === 0) {
    return null;
  }

  return (
    <section className="glass-panel rounded-xl p-5">
      <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-3">
        Similar Songs
      </h3>
      <ul className="divide-y divide-white/5">
        {analysis.similar_songs.map((song, i) => (
          <SimilarSongRow key={i} song={song} />
        ))}
      </ul>
    </section>
  );
};
