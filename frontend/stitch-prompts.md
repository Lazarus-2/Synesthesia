# Google Stitch Prompts for SoundBreak UI

Paste these into [stitch.withgoogle.com](https://stitch.withgoogle.com).

Stitch works best when you give it: **(1) app context**, **(2) explicit screens**, **(3) a clear visual identity**, and **(4) named components**. The prompts below are structured exactly that way.

---

## MAIN PROMPT (paste this)

```
App: SoundBreak — an AI music breakdown web app.

What it does: A user uploads any song or pastes a YouTube link. The app analyzes
the audio with AI and shows the chords, key, tempo, song structure (verse/chorus),
isolated stems (vocals, drums, bass, other), and step-by-step playing guides for
guitar, piano, ukulele, and bass at their chosen skill level. Built for musicians
who want to learn songs by ear, fast.

Audience: Bedroom musicians aged 18-40. Think Spotify-meets-Ableton-meets-Duolingo.

Visual identity:
- Dark, premium, studio-grade feel — like Linear or Arc browser, but warmer.
- Background: deep midnight navy (#0B0F1A) with subtle noise/grain texture.
- Primary accent: warm amber gradient (#FFB547 → #FF6B6B) — feels like vinyl + brass.
- Secondary accent: electric violet (#8B5CF6) for AI/intelligence moments.
- Soft glass-morphism cards (blurred translucent panels) over the dark base.
- Typography: "Inter" for UI, "Instrument Serif" for big display headings and chord names.
- Generous whitespace, large radii (16-24px), subtle inner glow on focused elements.
- Micro-illustrations: minimal line-drawn music icons (guitar headstock, piano keys,
  waveforms) in a single accent color.

Screens to design:

1. LANDING / UPLOAD
   - Centered hero with serif headline: "Hear any song. Play any song."
   - Big drag-and-drop upload zone (waveform illustration inside).
   - Below it: a YouTube URL input with a "Paste & Analyze" gradient button.
   - Tiny row of 4 instrument chips: Guitar, Piano, Ukulele, Bass — user picks one.
   - A "Try a sample" row showing 3 example song cards (Beatles, Oasis, Radiohead).
   - Top nav: logo, "Library", "Pricing", avatar circle.
   - Footer: minimal, three columns.

2. ANALYZING (loading state)
   - Centered animated waveform that pulses with an amber glow.
   - Step indicator showing the AI pipeline:
     "1. Listening ✓   2. Detecting chords ✓   3. Separating instruments ...
     4. Generating your guide"
   - Friendly status text under it: "Isolating the bass line — about 20s left."
   - Subtle constellation of dots floating in the background.

3. PLAYER (the core screen — most important)
   - Top bar: song title, artist, key badge (e.g. "C major"), tempo badge ("120 BPM"),
     and a "♥ Save" icon. Logo in the corner.
   - LEFT 65% column:
     a) Large waveform player (WaveSurfer-style) with playhead, region markers
        in amber per chord change. Play/pause is a big circular button below.
     b) Chord timeline strip directly under the waveform: horizontal scroll of
        chord tiles (Cmaj7, G, Am, F...) that highlight in sync with the playhead.
        Current chord is enlarged with a soft glow.
     c) Song-structure ribbon at the very top of the waveform: colored segments
        labeled "Intro · Verse · Chorus · Verse · Chorus · Bridge · Outro".
   - RIGHT 35% column (tabbed card):
     Tab 1 "PLAY"  - shows the current chord as a big chord diagram (guitar fretboard
                     or piano keys depending on instrument). Below: strum/picking pattern
                     ("D DU UDU"), capo suggestion ("Capo 2"), and a "next chord in 4s"
                     ghost preview.
     Tab 2 "THEORY" - shows roman numeral analysis (I - V - vi - IV) with a 1-paragraph
                     AI-written explanation of the progression. A small "Why does this
                     work?" expandable callout.
     Tab 3 "STEMS" - 4 vertical mixer sliders labeled Vocals, Drums, Bass, Other, each
                     with a mute button and a tiny waveform thumbnail.
   - Bottom bar: speed control (0.5x / 0.75x / 1x), loop section toggle, transpose
     +/- buttons, and a "Practice mode" button.

4. INSTRUMENT GUIDE (modal or full screen)
   - All chord diagrams for the song laid out as a grid of cards.
   - Each card: the chord name (large serif), the fretboard/keyboard diagram,
     finger numbers, a "Hard?" badge if it's a barre chord.
   - Top of the page: instrument switcher pill (Guitar / Piano / Ukulele / Bass)
     and difficulty pill (Beginner / Intermediate / Advanced).
   - A "Make it easier" button that suggests a capo or simpler voicings.

5. LIBRARY
   - Grid of saved-song cards (album art, title, artist, key, last-practiced date).
   - Filter chips at the top: "By key", "By difficulty", "Recently practiced",
     "Mastered".
   - One row of "Similar to songs you've practiced" with horizontal scroll.

Components I want named in the design system:
- `WaveformPlayer`, `ChordTile`, `ChordDiagram`, `StemMixer`, `InstrumentChip`,
  `KeyBadge`, `TempoBadge`, `SongStructureRibbon`, `TheoryCallout`,
  `PipelineStepIndicator`, `GradientCTA`, `GlassCard`.

Tone of all microcopy: confident, musician-friendly, never condescending.
Examples: "Detecting the groove…" "Here's the secret to this progression."
"Capo on 2 turns this into easy open chords."

Constraints:
- Mobile-responsive — also design the PLAYER screen for a 390px-wide phone:
  collapse the right column into a bottom drawer with tabs.
- WCAG AA contrast.
- No stock photography. Use abstract waveform art and minimal line illustrations only.
```

---

## Aesthetic Variants

Swap the **Visual identity** block in the main prompt with one of these for a different vibe.

### Variant A — "Vinyl Studio" (warm, analog, premium)

```
Visual identity:
- Inspired by a recording-studio control room at night.
- Cream off-white base (#F5EFE6) with deep oxblood (#5B1A1A) accents, brass gold
  (#C9A961), and matte black control elements.
- Paper-grain texture overlay, very subtle.
- Typography: "Editorial New" or "GT Sectra" serif for headings, "Söhne Mono"
  for chord names and timecodes.
- Hardware-inspired UI: knobs, VU meters, segmented LED-style displays.
- Looks like a love letter to analog gear (Neve consoles, vintage Rhodes pianos).
```

### Variant B — "Cyberpunk Synesthesia" (loud, neon, music-as-color)

```
Visual identity:
- Pitch-black background with chromatic-aberration glows in cyan (#00F0FF),
  magenta (#FF00C8), and lime (#B6FF00).
- Each chord type has its own color (major = warm, minor = cool, dom7 = neon
  pink) — the entire timeline pulses through those hues as the song plays.
- Typography: "Space Grotesk" for everything; chord names are huge, lowercase,
  letter-spaced.
- Heavy use of grids, scanlines, and motion blur.
- Feels like Blade Runner 2049 meets Ableton Live.
```

### Variant C — "Paper Songbook" (soft, friendly, Duolingo-warm)

```
Visual identity:
- Warm paper background (#FAF6F0), forest green (#1F5E3A) and tomato red
  (#E2542C) accents.
- Hand-drawn doodle illustrations of instruments, treble clefs, beat lines.
- Typography: "Fraunces" for headings (warm, friendly serif), "Inter" for body.
- Soft drop shadows, rounded everything (24px+ radii), playful icons.
- Feels like a beautifully designed printed songbook, but interactive.
- Microcopy is encouraging and slightly cheeky.
```

### Variant D — "Brutalist Beat" (bold, editorial, design-forward)

```
Visual identity:
- Stark monochrome (pure black, pure white) with one electric accent (#FF3D00
  hazard orange) used VERY sparingly.
- Massive typography (display serif at 96px+) — chord names dominate the screen.
- Asymmetric layouts, hard edges, no rounded corners.
- Inspired by Pentagram, Bauhaus, and album covers from Joy Division / The xx.
- Function over decoration. Every pixel earns its place.
```

---

## Tips for Working With Stitch

1. **Run the main prompt first.** Stitch usually generates the landing + 2-3 other screens. Note which screens it skipped.
2. **Refine per-screen.** After the first generation, ask Stitch:
   *"Redesign just the PLAYER screen with the right-column tabs expanded by default."*
3. **Iterate on one element at a time.** *"Make the chord tiles bigger and add a small instrument-icon badge to each."*
4. **Export to Figma** at the end so your real frontend dev (or you, in Phase 4) can use the design tokens and component names.
5. **Save prompt variants.** Generate one of each aesthetic above and pick the strongest before committing.

---

## After Stitch — Bridging to Code

When you get to **Phase 4** of the SoundBreak build (see `06-Projects/05-Project-SoundBreak.md`):

1. Export the Stitch design to Figma.
2. Use the component names from the prompt (`WaveformPlayer`, `ChordTile`, etc.) as your React component names — they'll already match.
3. The schemas in `backend/schemas.py` (`ChordEvent`, `InstrumentGuide`, `SongAnalysis`) map 1:1 to the data each component renders. No frontend modeling needed.
