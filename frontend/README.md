# SoundBreak Frontend (Phase 4)

Next.js + Tailwind playground for the waveform player, chord timeline, and instrument guides.

Build this after the backend is stable (end of Module 4).

## Stack

- Next.js 14 (app router)
- Tailwind CSS
- WaveSurfer.js (waveform + region timing)
- Tone.js (multi-stem sync playback)
- react-chords / chords-db (guitar diagrams)
- Zustand (client state)

## Bootstrap

```bash
npx create-next-app@latest web --typescript --tailwind --app
cd web
npm install wavesurfer.js tone @tonaljs/tonal zustand react-chords chords-db
```

## Key components to build

| Component | Responsibility |
|---|---|
| `WaveformPlayer` | wavesurfer + region markers per chord |
| `ChordTimeline` | scrollable chord boxes synced to playhead |
| `InstrumentSwitcher` | pick guitar/piano/uke/bass |
| `ChordDiagram` | render fret/note diagram from `ChordDiagram` schema |
| `TheoryPanel` | show LLM explanation + roman numerals |
| `StemMixer` | 4 sliders (vocals/drums/bass/other) when ENABLE_STEMS=true |

Backend returns everything in the `AnalyzeResponse` schema -- frontend is just a renderer.
