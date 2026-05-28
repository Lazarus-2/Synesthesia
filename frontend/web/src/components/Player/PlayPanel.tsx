"use client";

import React, { useMemo } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePlayerStore } from "../../store/usePlayerStore";
import { ChordDiagram } from "../../types";

const FretboardVisual: React.FC<{ diagram?: ChordDiagram }> = ({ diagram }) => {
  if (!diagram || !diagram.frets) {
    return (
      <div className="w-full aspect-[3/4] bg-surface-container-highest rounded-lg border border-white/10 p-4 flex items-center justify-center text-on-surface-variant text-sm">
        No diagram available
      </div>
    );
  }

  const { frets, fingers } = diagram;
  
  // Find the minimum fret to determine if we need to show a specific fret range
  const playedFrets = frets.filter(f => f > 0);
  const minFret = playedFrets.length > 0 ? Math.min(...playedFrets) : 1;
  const maxFret = playedFrets.length > 0 ? Math.max(...playedFrets) : 4;
  
  // Determine if we show the nut (if minFret is 1 or 0)
  const showNut = minFret <= 1;
  const startFret = showNut ? 1 : minFret;
  
  return (
    <div className="w-full aspect-[3/4] bg-surface-container-highest rounded-lg border border-white/10 p-4 relative flex justify-center overflow-hidden">
      {/* Fret Marker if not starting at 1 */}
      {!showNut && (
        <div className="absolute top-2 left-2 text-xs font-bold text-on-surface-variant">
          {startFret}fr
        </div>
      )}

      {/* Nut */}
      {showNut && (
        <div className="absolute top-4 w-3/4 h-2 bg-surface-bright rounded-sm z-10" />
      )}

      {/* Strings (6 for guitar) */}
      <div className="absolute top-6 bottom-4 w-3/4 flex justify-between z-0">
        {[0, 1, 2, 3, 4, 5].map((s) => (
          <div key={s} className="w-px bg-white/20 h-full" />
        ))}
      </div>

      {/* Frets (Usually show 4-5 frets) */}
      <div className="absolute top-6 bottom-4 w-3/4 flex flex-col justify-evenly z-0">
        {[0, 1, 2, 3].map((f) => (
          <div key={f} className="w-full h-px bg-white/10" />
        ))}
      </div>

      {/* X/O markers and finger dots */}
      {frets.map((fret, stringIdx) => {
        const leftPct = (stringIdx / 5) * 100;
        
        // Muted string (X)
        if (fret === -1) {
          return (
            <div 
              key={`mute-${stringIdx}`} 
              className="absolute top-1 text-label-sm text-error font-bold z-20"
              style={{ left: `calc(12.5% + (75% * ${stringIdx / 5}))`, transform: "translateX(-50%)" }}
            >
              X
            </div>
          );
        }
        
        // Open string (O)
        if (fret === 0) {
          return (
            <div 
              key={`open-${stringIdx}`} 
              className="absolute top-1 text-label-sm text-primary-container font-bold z-20"
              style={{ left: `calc(12.5% + (75% * ${stringIdx / 5}))`, transform: "translateX(-50%)" }}
            >
              O
            </div>
          );
        }

        // Pressed fret
        const relativeFret = fret - startFret + 1;
        // Map to vertical percentage (roughly middle of the fret spaces)
        // 4 frets total, each is 25% height. Middle is at 12.5%, 37.5%, 62.5%, 87.5%
        const topPct = 6 + (relativeFret - 0.5) * ((100 - 10) / 4);
        
        const finger = fingers ? fingers[stringIdx] : null;

        return (
          <div 
            key={`dot-${stringIdx}`}
            className="absolute w-5 h-5 rounded-full bg-secondary-container shadow-[0_0_8px_#571bc1] z-20 flex items-center justify-center text-[10px] font-bold text-white transition-all duration-300 transform -translate-x-1/2 -translate-y-1/2"
            style={{ 
              top: `${topPct}%`, 
              left: `calc(12.5% + (75% * ${stringIdx / 5}))` 
            }}
          >
            {finger && finger > 0 ? finger : ""}
          </div>
        );
      })}
    </div>
  );
};

export const PlayPanel: React.FC = () => {
  const { analysis, instrumentGuide } = useAnalysisStore();
  const { currentTime } = usePlayerStore();

  const currentChordEvent = useMemo(() => {
    if (!analysis?.chords) return null;
    return analysis.chords.find(
      (c) => currentTime >= c.start && currentTime <= c.end
    );
  }, [analysis, currentTime]);

  if (!analysis) {
    return (
      <div className="flex-grow p-6 flex items-center justify-center text-on-surface-variant text-sm">
        Upload a song to see the play view
      </div>
    );
  }

  const chordName = currentChordEvent?.chord || analysis.chords?.[0]?.chord || "Waiting...";
  const diagram = instrumentGuide?.chord_diagrams?.find((d: ChordDiagram) => d.chord === chordName);
  
  // Parse strum pattern
  const strumPattern = instrumentGuide?.strum_pattern || "D . D U . U D U";
  const strums = strumPattern.split(" ");

  return (
    <div className="flex flex-col gap-6 p-6 overflow-y-auto hide-scrollbar flex-grow w-full">
      <div className="flex justify-between items-start w-full">
        <h2 className="font-headline text-3xl font-medium text-white tracking-wide">
          {chordName}
        </h2>
        {instrumentGuide?.capo !== undefined && (
          <div className="px-3 py-1 rounded-full bg-white/10 text-xs font-semibold tracking-wider text-on-surface border border-white/20">
            Capo {instrumentGuide.capo}
          </div>
        )}
      </div>

      <FretboardVisual diagram={diagram} />

      {/* Strumming Pattern */}
      <div className="bg-surface-variant/30 rounded-lg p-4 border border-white/5 w-full mt-2">
        <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-4">
          Strum Pattern
        </h3>
        <div className="flex justify-between items-center px-2 w-full">
          {strums.map((s, i) => {
            if (s === "D") {
              return (
                <span key={i} className="material-symbols-outlined text-primary-container text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                  south
                </span>
              );
            }
            if (s === "U") {
              return (
                <span key={i} className="material-symbols-outlined text-on-surface text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                  north
                </span>
              );
            }
            return (
              <span key={i} className="w-2 h-2 rounded-full bg-white/20" />
            );
          })}
        </div>
      </div>
    </div>
  );
};
