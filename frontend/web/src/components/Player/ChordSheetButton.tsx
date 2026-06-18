"use client";

import React from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePracticeStore } from "../../store/usePracticeStore";
import { transposeChord } from "../../lib/music";
import type { RomanEntry } from "../../types";

/** Escape text destined for the printable popup's innerHTML. */
function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Exports a clean, printable chord sheet (title/artist/key/tempo + the chord
 * progression grouped by section, with Roman numerals + timestamps) into a new
 * window and triggers the browser print dialog — so the user can print or
 * "Save as PDF" with no extra dependency. Honours the current transpose.
 */
export const ChordSheetButton: React.FC = () => {
  const { analysis } = useAnalysisStore();
  const transpose = usePracticeStore((s) => s.transpose);

  if (!analysis?.chords || analysis.chords.length === 0) return null;

  const handleExport = () => {
    const chords = analysis.chords;
    const sections = analysis.sections ?? [];
    const entries: RomanEntry[] = analysis.roman?.entries ?? [];

    const romanFor = (start: number): string => {
      const e = entries.find((en) => Math.abs(en.start - start) < 0.15);
      return e?.numeral ?? "";
    };
    const labelFor = (chord: string): string =>
      transpose !== 0 ? transposeChord(chord, transpose) : chord;

    // Group chords by the section their start falls into (chords outside any
    // section land in a trailing "—" group so nothing is dropped).
    const groups: { name: string; chords: typeof chords }[] = [];
    if (sections.length > 0) {
      for (const sec of sections) {
        groups.push({
          name: sec.name,
          chords: chords.filter((c) => c.start >= sec.start - 0.05 && c.start < sec.end - 0.05),
        });
      }
      const covered = new Set(groups.flatMap((g) => g.chords.map((c) => c.start)));
      const leftover = chords.filter((c) => !covered.has(c.start));
      if (leftover.length) groups.push({ name: "—", chords: leftover });
    } else {
      groups.push({ name: "Progression", chords });
    }

    const cell = (chord: (typeof chords)[number]): string => {
      const rn = romanFor(chord.start);
      return `<div class="cell">
        <div class="chord">${esc(labelFor(chord.chord))}</div>
        ${rn ? `<div class="roman">${esc(rn)}</div>` : ""}
        <div class="t">${fmtTime(chord.start)}</div>
      </div>`;
    };

    const body = groups
      .filter((g) => g.chords.length > 0)
      .map(
        (g) => `<section class="grp">
          <h2>${esc(g.name)}</h2>
          <div class="grid">${g.chords.map(cell).join("")}</div>
        </section>`
      )
      .join("");

    const title = analysis.title || "Untitled";
    const artist = analysis.artist || "Unknown Artist";
    const meta = [
      analysis.key ? `Key: ${analysis.key}` : "",
      analysis.tempo ? `${Math.round(analysis.tempo)} BPM` : "",
      analysis.time_signature ? `${analysis.time_signature}` : "",
      transpose !== 0 ? `Transposed ${transpose > 0 ? "+" : ""}${transpose} st` : "",
    ]
      .filter(Boolean)
      .join(" · ");

    const html = `<!doctype html><html><head><meta charset="utf-8">
      <title>${esc(title)} — Chord Sheet</title>
      <style>
        :root { color-scheme: light; }
        * { box-sizing: border-box; }
        body { font-family: Georgia, "Times New Roman", serif; color: #111; margin: 32px; }
        header { border-bottom: 2px solid #111; padding-bottom: 10px; margin-bottom: 18px; }
        h1 { font-size: 26px; margin: 0 0 2px; }
        .artist { font-size: 15px; color: #444; margin: 0 0 6px; }
        .meta { font-size: 12px; color: #555; letter-spacing: .02em; }
        .grp { margin-bottom: 18px; break-inside: avoid; }
        .grp h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .12em; color: #b26a00;
                  border-bottom: 1px solid #ddd; padding-bottom: 4px; margin: 0 0 10px; }
        .grid { display: flex; flex-wrap: wrap; gap: 8px; }
        .cell { min-width: 64px; text-align: center; border: 1px solid #e2e2e2; border-radius: 6px;
                padding: 8px 10px; }
        .chord { font-family: "Courier New", monospace; font-weight: 700; font-size: 17px; }
        .roman { font-size: 11px; color: #7a3d00; margin-top: 2px; }
        .t { font-size: 9px; color: #999; margin-top: 3px; }
        footer { margin-top: 24px; font-size: 10px; color: #999; border-top: 1px solid #eee; padding-top: 8px; }
        @media print { body { margin: 14mm; } }
      </style></head>
      <body>
        <header>
          <h1>${esc(title)}</h1>
          <p class="artist">${esc(artist)}</p>
          <div class="meta">${esc(meta)}</div>
        </header>
        ${body}
        <footer>Generated by Synesthesia · ${chords.length} chords</footer>
        <script>window.onload = function(){ setTimeout(function(){ window.print(); }, 150); };</script>
      </body></html>`;

    const win = window.open("", "_blank", "width=820,height=1000");
    if (!win) {
      // Popup blocked — fall back to a data-URL download of the sheet.
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title.replace(/[^a-z0-9]+/gi, "_")}_chord_sheet.html`;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    win.document.open();
    win.document.write(html);
    win.document.close();
  };

  return (
    <button
      onClick={handleExport}
      title="Export a printable chord sheet (print or Save as PDF)"
      aria-label="Export printable chord sheet"
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-full glass-panel text-xs font-medium text-on-surface-variant hover:text-primary hover:border-primary/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <span className="material-symbols-outlined text-[18px]">print</span>
      Chord sheet
    </button>
  );
};
