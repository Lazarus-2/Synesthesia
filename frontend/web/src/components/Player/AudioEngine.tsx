"use client";

import { useEffect, useRef } from "react";
import { usePracticeStore } from "../../store/usePracticeStore";
import { usePlayerStore } from "../../store/usePlayerStore";

/** Audio-engine bridge.
 *
 *  Routes the WaveSurfer-driven ``<audio>`` element through a SoundTouch
 *  AudioWorklet:
 *
 *      MediaElementAudioSourceNode → SoundTouch worklet → AudioDestinationNode
 *
 *  The worklet does BOTH jobs the practice tools need:
 *    - ``pitchSemitones``  → transpose (±, pitch only, tempo unchanged)
 *    - ``playbackRate``    → pitch-PRESERVED time-stretch (the pitch-lock slow-
 *                            down). When pitch-lock is off we leave it at 1 and
 *                            let ``wavesurfer.setPlaybackRate`` shift pitch the
 *                            old way.
 *
 *  The worklet is created via Tone's ``createAudioWorkletNode`` (not the global
 *  ``new AudioWorkletNode``, which throws on Tone's standardized-audio-context),
 *  so it's compatible with the same context the source lives on. Tone's context
 *  is resumed by the play button's ``Tone.start()``. If the worklet can't load
 *  we fall back to wiring the source straight to the destination so playback is
 *  never silent (``createMediaElementSource`` has already detached the element
 *  from the speakers, so the source MUST reach a destination).
 *
 *  Renders nothing (mounted once at the top of HomeClient).
 */
export const AudioEngine: React.FC = () => {
  const wavesurfer = usePlayerStore((s) => s.wavesurfer);
  const transpose = usePracticeStore((s) => s.transpose);
  const pitchLock = usePracticeStore((s) => s.pitchLock);
  const playbackRate = usePracticeStore((s) => s.playbackRate);

  const graphRef = useRef<{
    src: MediaElementAudioSourceNode;
    soundTouchNode: AudioWorkletNode | null;
    rawAudio: HTMLMediaElement;
    cleanup: () => void;
  } | null>(null);

  // Build the graph once per audio element.
  useEffect(() => {
    if (!wavesurfer) return;
    const media: HTMLMediaElement | undefined = (
      wavesurfer as unknown as { getMediaElement?: () => HTMLMediaElement }
    ).getMediaElement?.();
    if (!media) return;
    if (graphRef.current?.rawAudio === media) return; // already built

    let cancelled = false;

    (async () => {
      const tone = await import("tone");
      if (cancelled) return;

      const toneCtx = tone.getContext();
      const rawCtx = toneCtx.rawContext as unknown as AudioContext;

      let src: MediaElementAudioSourceNode;
      try {
        src = rawCtx.createMediaElementSource(media);
      } catch (err) {
        // Already has a source (e.g. hot-reload) — element keeps its default
        // route; we just can't apply FX this session.
        console.warn("AudioEngine: createMediaElementSource failed:", err);
        return;
      }

      // Load + build the SoundTouch worklet via Tone so it joins the same graph.
      let soundTouchNode: AudioWorkletNode | null = null;
      try {
        await toneCtx.addAudioWorkletModule("/soundtouch-processor.js");
        if (cancelled) return;
        soundTouchNode = toneCtx.createAudioWorkletNode("soundtouch-processor", {
          numberOfInputs: 1,
          numberOfOutputs: 1,
          outputChannelCount: [2],
        });
      } catch (err) {
        console.warn("AudioEngine: SoundTouch worklet unavailable, FX disabled:", err);
        soundTouchNode = null;
      }

      // Wire src → [soundtouch] → destination, falling back to direct output so
      // audio is never lost if the worklet graph can't connect.
      const dest = rawCtx.destination;
      const stNode = soundTouchNode as unknown as AudioNode | null;
      let wired = false;
      if (stNode) {
        try {
          src.connect(stNode);
          stNode.connect(dest);
          wired = true;
        } catch (err) {
          console.warn("AudioEngine: soundtouch wiring failed, routing direct:", err);
          try { src.disconnect(); } catch { /* */ }
          try { stNode.disconnect(); } catch { /* */ }
          soundTouchNode = null;
        }
      }
      if (!wired) {
        try {
          src.connect(dest);
        } catch (err) {
          console.error("AudioEngine: direct output failed; playback may be silent:", err);
        }
      }

      // Seed the transpose param at its current value.
      if (soundTouchNode) {
        const ps = soundTouchNode.parameters.get("pitchSemitones");
        if (ps) ps.value = transpose;
      }

      graphRef.current = {
        src,
        soundTouchNode,
        rawAudio: media,
        cleanup: () => {
          try { src.disconnect(); } catch { /* */ }
          try { (soundTouchNode as unknown as AudioNode | null)?.disconnect(); } catch { /* */ }
        },
      };
    })();

    return () => {
      cancelled = true;
    };
  }, [wavesurfer]); // transpose/rate handled by their own live-update effects below

  // Live transpose → pitchSemitones (pitch only; tempo unchanged).
  useEffect(() => {
    const node = graphRef.current?.soundTouchNode;
    const ps = node?.parameters.get("pitchSemitones");
    if (ps) ps.value = transpose;
  }, [transpose]);

  // Pitch-lock slowdown → playbackRate (pitch PRESERVED). When pitch-lock is
  // off, keep the worklet at 1.0 and let wavesurfer.setPlaybackRate shift pitch.
  useEffect(() => {
    const node = graphRef.current?.soundTouchNode;
    const pr = node?.parameters.get("playbackRate");
    if (pr) pr.value = pitchLock ? playbackRate : 1.0;
  }, [pitchLock, playbackRate]);

  // Tear down only when the wavesurfer (audio element) actually changes.
  useEffect(() => {
    return () => {
      const g = graphRef.current;
      const liveMedia = (
        wavesurfer as unknown as { getMediaElement?: () => HTMLMediaElement } | null
      )?.getMediaElement?.();
      if (g && g.rawAudio !== liveMedia) {
        g.cleanup();
        graphRef.current = null;
      }
    };
  }, [wavesurfer]);

  return null;
};
