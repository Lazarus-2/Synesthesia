"use client";

import { useEffect, useRef } from "react";
import { usePracticeStore } from "../../store/usePracticeStore";
import { usePlayerStore } from "../../store/usePlayerStore";

type Tone = typeof import("tone");

/** Audio-engine bridge.
 *
 *  Headlessly intercepts the WaveSurfer-driven ``<audio>`` element's
 *  Web Audio output and routes it through:
 *
 *      MediaElementAudioSourceNode
 *           │
 *           ▼
 *      SoundTouchNode  (pitch-preserving time-stretch — only when pitchLock)
 *           │
 *           ▼
 *      Tone.PitchShift (semitone transpose, fine for ±5 semitones)
 *           │
 *           ▼
 *      AudioDestinationNode
 *
 *  Once a ``MediaElementAudioSourceNode`` is created from an
 *  ``HTMLMediaElement``, the spec says the element's default output to
 *  the speakers is disconnected — only the graph plays. So WaveSurfer's
 *  ``audio.play()`` still drives playback; we just intercept the signal
 *  on the way out.
 *
 *  Renders nothing (mounted once at the top of HomeClient). Reads
 *  ``transpose`` + ``pitchLock`` + ``playbackRate`` from the practice
 *  store and reflects them on the live AudioParams.
 */
export const AudioEngine: React.FC = () => {
  const wavesurfer = usePlayerStore((s) => s.wavesurfer);
  const transpose = usePracticeStore((s) => s.transpose);
  const pitchLock = usePracticeStore((s) => s.pitchLock);
  const playbackRate = usePracticeStore((s) => s.playbackRate);

  // Holds the live graph + a flag so we only build once per audio element.
  const graphRef = useRef<{
    ctx: AudioContext;
    src: MediaElementAudioSourceNode;
    soundTouchNode: AudioWorkletNode | null;
    pitchShift: { pitch: number; disconnect: () => void; connect: (n: AudioNode) => void } | null;
    rawAudio: HTMLMediaElement;
    cleanup: () => void;
  } | null>(null);

  // Build the graph the first time we see a wavesurfer with a media element.
  useEffect(() => {
    if (!wavesurfer) return;
    // WaveSurfer v7's media backend exposes the underlying <audio> via this method.
    const media: HTMLMediaElement | undefined = (wavesurfer as unknown as {
      getMediaElement?: () => HTMLMediaElement;
    }).getMediaElement?.();
    if (!media) return;
    if (graphRef.current?.rawAudio === media) return;  // already built

    let cancelled = false;

    (async () => {
      // Lazy-load Tone so the bundle doesn't pay for it on the landing page.
      const tone = await import("tone");
      if (cancelled) return;

      // Reuse Tone's AudioContext so PitchShift attaches cleanly.
      const ctx = tone.getContext().rawContext as AudioContext;

      // Some Browsers (Safari) keep the context suspended until a user
      // gesture. WaveSurfer's play button is a gesture; if we end up
      // suspended at construction time, Tone.start() inside its click
      // handler resumes us.

      let src: MediaElementAudioSourceNode;
      try {
        src = ctx.createMediaElementSource(media);
      } catch (err) {
        // ``createMediaElementSource`` throws ``InvalidStateError`` if the
        // element already has a source attached (e.g. from a hot-reload).
        // Bail quietly — playback still works via the element's default
        // route; we just won't be able to modulate pitch this session.
        console.warn("AudioEngine: createMediaElementSource failed:", err);
        return;
      }

      // PitchShift in cents — ``pitch`` is semitones; range fine for ±5.
      const pitchShift = new tone.PitchShift({
        pitch: transpose,
        windowSize: 0.1,
      });

      // SoundTouch worklet — only built once we need pitch-lock to avoid
      // burning audio CPU when the toggle is off.
      let soundTouchNode: AudioWorkletNode | null = null;
      try {
        await ctx.audioWorklet.addModule("/soundtouch-processor.js");
        soundTouchNode = new AudioWorkletNode(ctx, "soundtouch-processor");
      } catch (err) {
        // Worklet may fail in legacy contexts or if the processor file
        // path is wrong. Pitch-lock toggle silently falls back to the
        // existing wavesurfer.setPlaybackRate behaviour.
        console.warn("AudioEngine: SoundTouch worklet unavailable:", err);
      }

      // Wire the output graph. ``createMediaElementSource`` has already
      // detached the <audio> element from the speakers, so the source MUST end
      // up connected to a destination or playback is silent. We try richer
      // graphs first and fall back: standardized-audio-context (Tone 15) refuses
      // to connect nodes created outside its graph — notably a *native*
      // ``AudioWorkletNode`` — throwing "a value with the given key could not be
      // found". That used to abort wiring entirely and leave the source dangling
      // (the "play does nothing" bug). Each strategy below is attempted in order;
      // the first that connects without throwing wins.
      const pitchShiftNode = pitchShift as unknown as AudioNode;
      const strategies: Array<[string, () => void]> = [];
      if (soundTouchNode) {
        // Full chain: source → SoundTouch (pitch-lock) → PitchShift → out.
        strategies.push(["soundtouch+pitch", () => {
          src.connect(soundTouchNode!);
          soundTouchNode!.connect(pitchShiftNode);
          pitchShift.toDestination();
        }]);
      }
      // Pitch only: source → PitchShift → out (transpose stepper still works).
      // Tone nodes are NOT raw AudioNodes, so ``src.connect(pitchShift)`` throws
      // inside standardized-audio-context ("value with the given key could not
      // be found"). ``Tone.connect`` bridges a standardized/native source into a
      // Tone node correctly.
      strategies.push(["pitch", () => {
        tone.connect(src, pitchShift);
        pitchShift.toDestination();
      }]);
      // Last resort: source → destination (plain playback, no FX) so audio is
      // always audible even if the Tone graph is unusable in this browser.
      strategies.push(["direct", () => {
        src.connect(ctx.destination);
      }]);

      let wired = "";
      for (const [name, wire] of strategies) {
        try {
          wire();
          wired = name;
          break;
        } catch (err) {
          console.warn(`AudioEngine: '${name}' wiring failed, trying next:`, err);
          try { src.disconnect(); } catch { /* */ }
          try { soundTouchNode?.disconnect(); } catch { /* */ }
          try { pitchShift.disconnect(); } catch { /* */ }
        }
      }
      // The worklet is only in the graph if the full chain wired; otherwise drop
      // the reference so the pitch-lock toggle doesn't try to use a dead node.
      if (wired !== "soundtouch+pitch") soundTouchNode = null;
      if (!wired) {
        console.error("AudioEngine: all wiring strategies failed; playback may be silent");
      }

      graphRef.current = {
        ctx,
        src,
        soundTouchNode,
        // Tone's PitchShift exposes ``.pitch`` directly + a disconnect.
        pitchShift: {
          get pitch() { return pitchShift.pitch; },
          set pitch(v: number) { pitchShift.pitch = v; },
          disconnect: () => pitchShift.disconnect(),
          connect: (n: AudioNode) => pitchShift.connect(n),
        },
        rawAudio: media,
        cleanup: () => {
          try { src.disconnect(); } catch { /* */ }
          try { soundTouchNode?.disconnect(); } catch { /* */ }
          try { pitchShift.disconnect(); pitchShift.dispose(); } catch { /* */ }
        },
      };
    })();

    return () => {
      cancelled = true;
      // Don't tear down the graph on unmount — the same wavesurfer
      // instance may be reused. Tear down only when wavesurfer changes.
    };
  }, [wavesurfer, transpose]);

  // Live-tune transpose semitones.
  useEffect(() => {
    const g = graphRef.current;
    if (g?.pitchShift) g.pitchShift.pitch = transpose;
  }, [transpose]);

  // Live-tune SoundTouch rate (pitch-preserving) when pitchLock is on.
  // When off, write rate=1 to the worklet AND let wavesurfer's default
  // ``setPlaybackRate`` shift pitch through the <audio> element itself.
  useEffect(() => {
    const g = graphRef.current;
    if (!g) return;
    const wantPitchPreservingRate = pitchLock ? playbackRate : 1.0;
    const node = g.soundTouchNode;
    if (node) {
      const tempo = node.parameters.get("tempo");
      const rate = node.parameters.get("rate");
      if (tempo) tempo.value = wantPitchPreservingRate;
      if (rate) rate.value = 1.0;
    }
    // When pitchLock is OFF we want the audio element itself to handle
    // the rate change (so wavesurfer's existing setPlaybackRate calls
    // still apply). We do NOT touch ``media.playbackRate`` here — the
    // BottomBar speed handler already calls ``wavesurfer.setPlaybackRate``.
  }, [pitchLock, playbackRate]);

  // Tear down on wavesurfer swap.
  useEffect(() => {
    return () => {
      const g = graphRef.current;
      if (g && g.rawAudio !== (wavesurfer as unknown as { getMediaElement?: () => HTMLMediaElement } | null)?.getMediaElement?.()) {
        g.cleanup();
        graphRef.current = null;
      }
    };
  }, [wavesurfer]);

  return null;
};
