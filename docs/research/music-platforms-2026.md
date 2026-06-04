# Music Platform Integrations — 2026 Reality Check

> Captured during Plan v2 planning. Sources cited inline. Use this as the
> reference for any future "what API should I use?" decision — saves the
> two hours of WebSearch we burned to compile it.

Status legend: **[WORKING]** / **[DEGRADED]** / **[BROKEN]**

## 1. yt-dlp (May/Jun 2026) — [DEGRADED]

- **Default `player_client` is now `android_vr,web_safari`**; the roster
  is `web`, `web_safari`, `web_embedded`, `web_music`, `web_creator`,
  `mweb`, `ios`, `android`, `android_vr`, `tv`, `tv_downgraded`,
  `tv_simply`. Plain `android` is still listed but heavily SABR-throttled.
  ([yt-dlp #14515](https://github.com/yt-dlp/yt-dlp/issues/14515),
  [rapidseedbox 2026 guide](https://www.rapidseedbox.com/blog/yt-dlp-complete-guide))
- **External JS runtime now required.** yt-dlp downloads a solver script
  from `yt-dlp/ejs` and executes it via **Deno** (QuickJS works but ~10×
  slower; Node also works via `--js-runtimes node:$PATH`). Without it
  you get 403 / "signature solving failed". Pass `--remote-components ejs:github`
  to opt into the solver download. ([HN 45898407](https://news.ycombinator.com/item?id=45898407),
  [DeepWiki: JS challenge solving](https://deepwiki.com/yt-dlp/yt-dlp/3.4.2-javascript-challenge-solving))
- **`music.youtube.com` still not first-class.** Normalise to
  `www.youtube.com/watch?v=…` or pass a GVS PO Token. Tokens are
  short-lived and session-bound. ([Seal #2404](https://github.com/JunkFood02/Seal/issues/2404))
- **`web_safari` is the sweet spot** for combined audio+video formats;
  `tv` and `tv_simply` are useful fallbacks when SABR blocks `web`.
- **Practical 2026 bypass stack**: yt-dlp ≥ 2026.03.13 + Deno (or Node)
  + `--extractor-args "youtube:player_client=web_safari,tv,web_music"` +
  rotating PO token for music URLs. ([yt-dlp PyPI](https://pypi.org/project/yt-dlp),
  [DEV "Bypassing the 2026 Great Wall"](https://dev.to/ali_ibrahim/bypassing-the-2026-youtube-great-wall-a-guide-to-yt-dlp-v2rayng-and-sabr-blocks-1dk8))

## 2. Spotify Web API — [BROKEN for new apps]

- **`/audio-features` and `/audio-analysis` are gone for any app
  registered on/after 27 Nov 2024.** Existing apps in *extended* quota
  are grandfathered; everyone else gets 403. ([Spotify blog 2024-11-27](https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api))
- Also restricted for new apps: Related Artists, Recommendations,
  Featured Playlists, Category Playlists, algorithmic/editorial
  playlists, and **30-second `preview_url`** in multi-get SimpleTrack
  responses.
- **Feb 2026 tightened further:** Search `limit` capped at 10 (was 50),
  default 5; batch get-tracks/get-albums consolidated; fields removed
  include `popularity`, `external_ids`, `available_markets`,
  `followers`, user `country/email/product`. Playlist payload shape
  renamed (`tracks` → `items`). ([Feb 2026 changelog](https://developer.spotify.com/documentation/web-api/references/changes/february-2026))
- **Dev Mode now requires the app owner to hold an active Premium
  subscription** and is capped at **5 test users** (down from 25).
  Lapsed Premium = app stops working. ([TechCrunch 2026-02-06](https://techcrunch.com/2026/02/06/spotify-changes-developer-mode-api-to-require-premium-accounts-limits-test-users/))
- Rate limits are a 30-second rolling window; concrete numbers are no
  longer published — dev mode is "low", extended is "much higher".

**Decision for Synesthesia v2:** use Spotify only for track metadata +
ToS-clean iframe embed playback. Optional env-gated yt-dlp re-download
bridge for power users; default off.

## 3. MusicBrainz API — [WORKING]

- **Hard cap: 1 req/sec per IP**, returns HTTP 503 above that. Global
  ceiling 300 req/sec. ([MB rate limiting](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting))
- The ~50 req/sec lane only applies if your User-Agent matches a
  whitelisted app string. For our own app we're effectively at 1/sec —
  set a meaningful UA with contact info to avoid the "anonymous"
  penalty bucket.
- `musicbrainzngs` is the canonical Python client; current docs version
  0.7.1. Maintenance is slow but the library still works
  (`set_rate_limit()` baked in). ([musicbrainzngs docs](https://python-musicbrainzngs.readthedocs.io/en/latest/api/))
- REST endpoints return JSON (`?fmt=json`) — no formal JSON-LD endpoint,
  but the schema is standardised and stable.

## 4. AcoustID / Chromaprint — [WORKING]

- **`pyacoustid` 1.3.1 released 9 Apr 2026**, supports Python 3.10–3.14.
  ([pyacoustid PyPI](https://pypi.org/project/pyacoustid/))
- Chromaprint shipped FFmpeg 8.0 support and Linux ARM64 binaries in
  2026. Server still up and accepting submissions per release activity.
- Linux install: `apt install libchromaprint-tools` gives you `fpcalc`;
  or build with `cmake -DBUILD_TOOLS=ON`. Library transitively needs
  libavcodec.
- Free tier requires registering an application key on acoustid.org.

## 5. Spotify alternatives for metadata — [MOSTLY WORKING]

- **Deezer Public API**: no auth required, JSON, last doc refresh
  31 Mar 2026 — the easiest drop-in for artist art, bios, similar
  artists, top tracks. ([Navidrome integrations](https://www.navidrome.org/docs/usage/integration/external-services/))
- **Last.fm API**: alive, free API key, good for tags/similar/scrobble
  counts.
- **TheAudioDB**: free JSON, community-curated artwork + metadata,
  API-key registration.
- **Tidal / Apple Music**: still require business/developer
  relationships; not viable for a hobby/educational app.
- **GetSongBPM**: free tier still listed in 2026 guides; attribution
  backlink required, hit ratio variable.

**Decision for Synesthesia v2:** Deezer for search results (richest
metadata, no auth); MusicBrainz layered on top for canonical MBIDs.

## 6. Lyrics — [WORKING, with one clear winner]

- **LRCLIB.net is the answer**: ~3M synced lyrics, returns
  `syncedLyrics` (LRC format) and `plainLyrics` in JSON, **no API key,
  no rate limit**, public SQLite dumps available. ([LRCLIB docs](https://lrclib.net/docs))
- License is "grey" — fine for non-commercial / FOSS, due-diligence
  needed before commercial use. ([HN 39480390](https://news.ycombinator.com/item?id=39480390))
- **Genius API** returns referent/annotation metadata + a web URL for
  lyrics; **no synced timestamps** and ToS prohibits scraping the
  lyric body. Use for annotations, not playback sync.
- **Musixmatch** has full synced catalogue but is paid; free tier
  exists but heavily rate-limited and bans commercial use.

**Decision for Synesthesia v2:** LRCLIB exclusively for v1.

## 7. Open chord / tab / MIDI databases — [DEGRADED]

- **Hooktheory Trends API**: still exposes "next-chord probabilities" +
  "songs containing progression"; ~75k analysed songs; requires
  account, not CC0. ([Hooktheory API docs](https://www.hooktheory.com/api/trends/docs))
- No new CC0 chord-progression corpus surfaced in 2026 search;
  community scrapers of Hooktheory exist but legally murky.
- For permissively-licensed training/eval data, the academic standbys
  (Isophonics, JAAH, McGill Billboard, RWC) remain the realistic
  options — none refreshed in 2026.

## 8. Audio analysis ML beyond librosa — [MIXED]

- **`madmom` is effectively unmaintained.** Last release 0.16.1,
  Nov 2018. Still installs on modern Python with workarounds. ([madmom GitHub](https://github.com/CPJKU/madmom))
- **Essentia is actively shipping** — `2.1b6.dev1438` released
  19 May 2026, builds for CPython 3.14. Far broader feature set than
  librosa (key, beat, danceability, mood models). ([Essentia PyPI](https://pypi.org/project/essentia/))
- **Spleeter is dead**: no major release since 2022, still on TF 1.x.
  **Demucs** (`htdemucs_ft`, maintained by Meta) wins by 20–40% on SDR
  benchmarks.
- **Basic Pitch** (Spotify, MIT) is still the standard for polyphonic
  AMT/MIDI extraction; now exists in ONNX-portable form.

## 9. Browser-side audio — [WORKING]

- **Tone.js 15.x** is current; built-in `PitchShift` is a delay-line
  trick — fine for small intervals, audibly artefacted beyond ±5
  semitones. ([Tone.js PitchShift v15.0.4](https://tonejs.github.io/docs/15.0.4/classes/PitchShift.html))
- **SoundTouchJS** is alive; relicensed LGPL → MPL-2.0;
  `@soundtouchjs/audio-worklet` is the recommended path — pure
  AudioWorklet, supports `processOffline()` for buffer rendering,
  exposes `pitch / pitchSemitones / playbackRate` AudioParams. Use this
  for pitch-preserving time-stretch. ([npm](https://www.npmjs.com/package/@soundtouchjs/audio-worklet))
- **AudioWorklet is universal in 2026** (Chrome, Edge, Firefox, Safari).
  `ScriptProcessorNode` is officially deprecated.
- **Web MIDI API in Safari: still NOT supported**, no roadmap. Plan
  around this. ([caniuse: midi](https://caniuse.com/midi))

## 10. Surprising 2026 developments — [WORKING]

- **Chord recognition has moved past template-matching.** Open-source
  `ChordMini` stacks Chord-CNN-LSTM + BTC-SL/BTC-PL with LLM
  post-correction. This is the current "free + better than librosa
  templates" baseline. ([ChordMiniApp](https://github.com/ptnghia-j/ChordMiniApp))
- **BasicPitch in the browser is real.** `basicpitch.cpp` compiles
  the Spotify model to ONNXRuntime + WASM. ([sevagh/basicpitch.cpp](https://github.com/sevagh/basicpitch.cpp))
- **ONNX Runtime Web v2.6 + WebGPU** is now the standard path for
  shipping any audio ML model client-side without a backend.
- Real-time mic chord detection: `mxkrn/webchord` demonstrates it in
  pure browser. ([mxkrn/webchord](https://github.com/mxkrn/webchord))

## Critical 2026 issues that drove Plan v2

1. **Spotify `/audio-features` is dead for new apps** → don't use
   Spotify as a feature source. Use **Deezer + Last.fm + MusicBrainz +
   AcoustID** for metadata and **LRCLIB** for synced lyrics.
2. **yt-dlp needs PO tokens + Deno/Node JS runtime** → bake the runtime
   into setup, set `--extractor-args player_client=web_safari,tv,web_music`,
   normalise `music.youtube.com` → `www.youtube.com`, expect periodic
   extractor failure.
3. **madmom is unmaintained** → keep as a try/except, prefer Essentia
   for new work.
4. **Tone.js `PitchShift` smears past ±5 semitones** → use
   `@soundtouchjs/audio-worklet` for the slowdown control; Tone for
   the transpose stepper.
5. **Web MIDI on Safari/iOS will never work** → gate MIDI-controller
   features on platform detection; on-screen fallback elsewhere.
