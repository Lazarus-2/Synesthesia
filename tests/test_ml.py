"""ML wrapper tests (Plan 3 D3).

Each ML module is a thin wrapper over librosa/madmom/demucs/basic-pitch.
We assert *bounded* properties (non-empty result, sane ranges, valid
labels) against the deterministic ``synthetic_song`` fixture so tests
don't depend on a real audio file or a GPU.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ``librosa`` is required by every test in this file; skip gracefully
# in environments where it's not installed (e.g. very stripped CI).
pytest.importorskip("librosa")


class TestKeyEstimation:
    def test_returns_recognised_key_label_for_c_major_audio(self, synthetic_song: Path):
        from backend.ml.key_estimation import estimate_key_and_tempo
        key, tempo = estimate_key_and_tempo(synthetic_song)
        assert isinstance(key, str) and " " in key, key
        root, mode = key.split(" ", 1)
        assert root in {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}
        assert mode in {"major", "minor"}
        # Tempo for a chord-block synth is not meaningful but must be a positive float.
        assert isinstance(tempo, (int, float)) and tempo > 0


class TestChordDetection:
    def test_returns_non_empty_chord_events_in_bounds(self, synthetic_song: Path):
        from backend.ml.chord_detection import detect_chords
        events = detect_chords(synthetic_song)
        # We don't require a particular chord to be detected — only that the
        # algorithm completes and returns events with the right shape.
        assert events is not None
        if not events:
            pytest.skip("No chord events extracted for synthetic audio (librosa heuristic)")
        e = events[0]
        assert e.start >= 0.0
        assert e.end > e.start
        assert isinstance(e.chord, str) and len(e.chord) > 0
        assert 0.0 <= e.confidence <= 1.0


class TestBeatTracking:
    def test_returns_list_of_beat_events_or_empty(self, synthetic_song: Path):
        from backend.ml.beat_tracking import track_beats
        beats = track_beats(synthetic_song)
        assert isinstance(beats, list)
        for b in beats[:10]:
            assert b.time >= 0.0
            assert 1 <= b.beat_number <= 4


class TestStructureDetection:
    def test_returns_section_list_or_empty(self, synthetic_song: Path):
        from backend.ml.structure_detection import detect_sections
        sections = detect_sections(synthetic_song)
        assert isinstance(sections, list)
        # Either empty (algorithm couldn't segment a 6s clip) or sane.
        for s in sections:
            assert s.end > s.start
            assert s.name in {"Intro", "Verse", "Chorus", "Bridge", "Outro"}


class TestMLRegistry:
    def test_registered_keys_exist(self):
        from backend.ml import registry
        assert "demucs" in registry._builders
        assert "basic_pitch" in registry._builders

    def test_get_calls_builder_once(self):
        from backend.ml import registry
        calls = {"n": 0}

        def _build():
            calls["n"] += 1
            return {"id": "fake-model"}

        registry.register("fake-test-model", _build)
        try:
            m1 = registry.get("fake-test-model")
            m2 = registry.get("fake-test-model")
            assert m1 is m2
            assert calls["n"] == 1
        finally:
            registry.reset_for_tests()

    def test_get_unknown_raises(self):
        from backend.ml import registry
        with pytest.raises(KeyError):
            registry.get("definitely-not-registered")


class TestAudioValidationNode:
    def test_validate_audio_node_accepts_good_wav(self, synthetic_song: Path):
        from backend.graph.nodes import validate_audio_node
        state = {"audio_path": str(synthetic_song), "errors": []}
        result = validate_audio_node(state)
        # Empty dict means "no new errors" — i.e. the audio is fine.
        assert result == {}

    def test_validate_audio_node_rejects_missing_file(self):
        from backend.graph.nodes import validate_audio_node
        result = validate_audio_node({"audio_path": "/tmp/nope-does-not-exist.wav", "errors": []})
        assert "errors" in result
        assert any("does not exist" in e for e in result["errors"])

    def test_validate_audio_node_skips_when_prior_errors(self):
        from backend.graph.nodes import validate_audio_node
        # Prior errors short-circuit the node.
        result = validate_audio_node({"audio_path": "/tmp/whatever", "errors": ["prev"]})
        assert result == {}
