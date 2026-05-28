"use client";

import React, { useState } from "react";

interface Stem {
  id: string;
  label: string;
  icon: string;
  color: string;
}

const STEMS: Stem[] = [
  { id: "vocals", label: "Vocals", icon: "mic", color: "#c4abff" },
  { id: "drums", label: "Drums", icon: "album", color: "#ffb547" },
  { id: "bass", label: "Bass", icon: "speaker", color: "#ffafac" },
  { id: "melodics", label: "Melodics", icon: "piano", color: "#ffd9ab" },
];

export const StemMixer: React.FC = () => {
  const [volumes, setVolumes] = useState<Record<string, number>>({
    vocals: 80,
    drums: 100,
    bass: 70,
    melodics: 90,
  });
  const [muted, setMuted] = useState<Record<string, boolean>>({});

  const setVolume = (id: string, vol: number) => {
    setVolumes((prev) => ({ ...prev, [id]: vol }));
  };

  const toggleMute = (id: string) => {
    setMuted((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="flex flex-col gap-6 p-6 overflow-y-auto hide-scrollbar flex-grow">
      <h2 className="font-headline text-2xl font-medium text-white">Stems</h2>
      <p className="text-sm text-on-surface-variant -mt-2">
        Adjust individual instrument levels. Requires Demucs stem separation.
      </p>

      <div className="flex flex-col gap-4">
        {STEMS.map((stem) => {
          const vol = muted[stem.id] ? 0 : volumes[stem.id];
          return (
            <div
              key={stem.id}
              className="glass-panel rounded-xl p-4 flex items-center gap-4"
            >
              {/* Icon */}
              <button
                className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 transition-all ${
                  muted[stem.id]
                    ? "bg-white/5 opacity-40"
                    : "bg-white/10"
                }`}
                onClick={() => toggleMute(stem.id)}
                title={muted[stem.id] ? "Unmute" : "Mute"}
              >
                <span
                  className="material-symbols-outlined text-xl"
                  style={{ color: muted[stem.id] ? "#9e8e7c" : stem.color }}
                >
                  {muted[stem.id] ? "volume_off" : stem.icon}
                </span>
              </button>

              {/* Label + Slider */}
              <div className="flex-grow">
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-sm font-medium text-on-surface">
                    {stem.label}
                  </span>
                  <span className="text-xs text-on-surface-variant tabular-nums">
                    {vol}%
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={vol}
                  onChange={(e) => setVolume(stem.id, Number(e.target.value))}
                  className="stem-slider w-full"
                  disabled={muted[stem.id]}
                />
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-outline-variant text-center mt-4 italic">
        Stem separation powered by Demucs. Processing may take up to 60 seconds.
      </p>
    </div>
  );
};
