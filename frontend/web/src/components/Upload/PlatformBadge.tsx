"use client";

import React from "react";

/** Detect the music platform from a pasted URL.
 *
 *  Mirrors the backend's ``backend.ingestion.url_resolver.classify_url``
 *  so the smart-detect badge stays in sync with what the server accepts.
 */
export type Platform = "youtube" | "youtube_music" | "spotify" | "unknown";

export function classifyUrl(input: string): Platform {
  const url = input.trim();
  if (!url) return "unknown";
  if (url.startsWith("spotify:track:")) return "spotify";
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    if (host === "music.youtube.com") return "youtube_music";
    if (host === "open.spotify.com" || host === "embed.spotify.com") return "spotify";
    if (
      host === "youtube.com" ||
      host === "www.youtube.com" ||
      host === "m.youtube.com" ||
      host === "youtu.be"
    ) {
      return "youtube";
    }
    return "unknown";
  } catch {
    return "unknown";
  }
}

const _LABELS: Record<Platform, { label: string; icon: string; tint: string }> = {
  youtube:       { label: "YouTube",       icon: "smart_display",  tint: "text-red-400 border-red-400/40 bg-red-400/10" },
  youtube_music: { label: "YouTube Music", icon: "library_music",  tint: "text-red-300 border-red-300/40 bg-red-300/10" },
  spotify:       { label: "Spotify",       icon: "graphic_eq",     tint: "text-green-400 border-green-400/40 bg-green-400/10" },
  unknown:       { label: "Unknown",       icon: "help",           tint: "text-on-surface-variant border-outline/30 bg-surface-container-high" },
};

export const PlatformBadge: React.FC<{ platform: Platform }> = ({ platform }) => {
  const cfg = _LABELS[platform];
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold uppercase tracking-wider border ${cfg.tint}`}
    >
      <span className="material-symbols-outlined text-[14px]">{cfg.icon}</span>
      {cfg.label}
    </span>
  );
};
