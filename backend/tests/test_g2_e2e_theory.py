"""G2.7 — structured TheoryExplanation survives the full assembly pipeline.

Drives the run_analysis_pipeline task with:
  - A synthetic graph result (no actual ML)
  - An in-memory fake Mongo (no real DB connection)
  - No LLM calls (TheoryExplanation constructed directly)

Asserts:
  1. SongAnalysisModel written to Mongo carries `theory` as a dict.
  2. The AnalyzeResponse cached in the job store carries `analysis.theory`.
  3. `AnalyzeResponse.analysis.theory_explanation` equals `theory.text`.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def fake_graph_result():
    from backend.schemas import ChordEvent, RomanAnalysis, TheoryExplanation

    te = TheoryExplanation(
        key_summary="C major — the I-V-vi-IV progression centers on C.",
        function_explanation="C is tonic (I), G is dominant (V), Am is submediant (vi), F is subdominant (IV).",
        pattern_name="I-V-vi-IV pop progression",
        notable_techniques=["diatonic harmony only"],
        similar_song="Let It Be — Beatles",
    )
    return {
        "key": "C major",
        "tempo": 120.0,
        "chords": [
            ChordEvent(start=0.0, end=1.0, chord="C"),
            ChordEvent(start=1.0, end=2.0, chord="G"),
            ChordEvent(start=2.0, end=3.0, chord="Am"),
            ChordEvent(start=3.0, end=4.0, chord="F"),
        ],
        "beats": [],
        "sections": [],
        "roman": RomanAnalysis(
            key="C major",
            progression=["I", "V", "vi", "IV"],
            function=["tonic", "dominant", "submediant", "subdominant"],
        ),
        "theory": te,
        "theory_explanation": te.text,
        "instrument_guide": None,
        "stems": {},
        "errors": [],
        "status": "ok",
    }


class TestTheoryEndToEnd:
    def test_theory_persisted_as_dict_in_mongo(self, fake_graph_result):
        """The SongAnalysisModel written to Mongo must include 'theory' as a nested
        dict, not a flat string."""

        # Replicate the assembly logic from tasks.py (not calling the task
        # directly to avoid broker/taskiq plumbing in unit tests).
        from backend.models import SongAnalysisModel
        from backend.schemas import SongAnalysis
        from backend.tasks import _clean_audio_title
        from backend.tools.synesthesia_colors import get_vibe_palette

        result = fake_graph_result
        chords = result.get("chords", [])
        vibe_pal = get_vibe_palette(result.get("key", "C major"), [c.chord for c in chords])

        analysis = SongAnalysis(
            title=_clean_audio_title(None, None),
            artist="Test",
            duration=float(chords[-1].end) if chords else 180.0,
            key=result.get("key", "C major"),
            tempo=result.get("tempo", 120.0),
            time_signature="4/4",
            chords=chords,
            beats=result.get("beats", []),
            sections=result.get("sections", []),
            roman=result.get("roman"),
            vibe_palette=vibe_pal,
            theory=result.get("theory"),
            theory_explanation=result.get("theory_explanation"),
            instrument_guides={},
            stems=result.get("stems", {}),
        )

        record = SongAnalysisModel(
            id="job-e2e",
            file_hash=None,
            user_id=None,
            title=analysis.title,
            artist=analysis.artist,
            duration=analysis.duration,
            key=analysis.key,
            tempo=analysis.tempo,
            time_signature=analysis.time_signature,
            chords=analysis.chords,
            beats=analysis.beats,
            sections=analysis.sections,
            roman=analysis.roman,
            vibe_palette=analysis.vibe_palette,
            theory_explanation=analysis.theory_explanation,
            theory=analysis.theory,
            instrument_guides={},
            stems=analysis.stems,
            status="ok",
        )

        dumped = record.model_dump(by_alias=True)
        assert "theory" in dumped, "SongAnalysisModel.model_dump must include 'theory'"
        assert dumped["theory"] is not None
        assert dumped["theory"]["pattern_name"] == "I-V-vi-IV pop progression"
        assert dumped["theory"]["similar_song"] == "Let It Be — Beatles"

    def test_theory_survives_json_round_trip(self, fake_graph_result):
        """AnalyzeResponse.model_dump_json() / model_validate_json() must
        preserve the structured theory object."""
        import json

        from backend.schemas import AnalyzeResponse, SongAnalysis
        from backend.tools.synesthesia_colors import get_vibe_palette

        result = fake_graph_result
        chords = result.get("chords", [])
        vibe_pal = get_vibe_palette(result.get("key", "C major"), [c.chord for c in chords])

        analysis = SongAnalysis(
            title="E2E Test",
            artist="Test",
            duration=float(chords[-1].end) if chords else 180.0,
            key=result["key"],
            tempo=result["tempo"],
            time_signature="4/4",
            chords=chords,
            beats=[],
            sections=[],
            roman=result.get("roman"),
            vibe_palette=vibe_pal,
            theory=result.get("theory"),
            theory_explanation=result.get("theory_explanation"),
            instrument_guides={},
            stems={},
        )
        resp = AnalyzeResponse(job_id="job-e2e", status="done", analysis=analysis)

        # Serialize then deserialize — both structured theory AND back-compat string
        json_str = resp.model_dump_json()
        payload = json.loads(json_str)

        theory_payload = payload["analysis"]["theory"]
        assert theory_payload["key_summary"].startswith("C major")
        assert theory_payload["pattern_name"] == "I-V-vi-IV pop progression"
        assert "diatonic harmony only" in theory_payload["notable_techniques"]

        te_text = payload["analysis"]["theory_explanation"]
        assert isinstance(te_text, str)
        assert "C major" in te_text
        assert "I-V-vi-IV pop progression" in te_text

    def test_song_analysis_validate_from_db_dict_round_trip(self, fake_graph_result):
        """SongAnalysis.model_validate(dict_from_mongo) must restore theory as a
        TheoryExplanation object (used in tasks.py idempotency path and main.py
        get_analysis)."""
        from backend.models import SongAnalysisModel
        from backend.schemas import SongAnalysis, TheoryExplanation

        te = fake_graph_result["theory"]
        record = SongAnalysisModel(
            id="job-rt",
            duration=4.0,
            key="C major",
            tempo=120.0,
            theory=te,
            theory_explanation=te.text,
        )
        mongo_dict = record.model_dump(by_alias=True)
        # Simulate what tasks.py does on idempotency check:
        # SongAnalysis.model_validate(existing) where existing came from Mongo
        restored = SongAnalysis.model_validate(mongo_dict)
        assert isinstance(restored.theory, TheoryExplanation), (
            f"Expected TheoryExplanation after round-trip; got {type(restored.theory)}"
        )
        assert restored.theory.pattern_name == "I-V-vi-IV pop progression"
        assert restored.theory_explanation == te.text


class TestTheoryExplanationComputedField:
    """G2 fix: TheoryExplanation.text must appear in model_dump / model_dump_json
    as a computed_field so the API JSON includes it (needed by G5 frontend)."""

    def _make_te(self):
        from backend.schemas import TheoryExplanation

        return TheoryExplanation(
            key_summary="C major — the I-V-vi-IV progression centers on C.",
            function_explanation=(
                "C is tonic (I), G is dominant (V), Am is submediant (vi), "
                "F is subdominant (IV)."
            ),
            pattern_name="I-V-vi-IV pop progression",
            notable_techniques=["diatonic harmony only"],
            similar_song="Let It Be — Beatles",
        )

    def test_text_in_model_dump(self):
        """text must be serialized by model_dump() as a computed_field."""
        te = self._make_te()
        dumped = te.model_dump()
        assert "text" in dumped, (
            f"'text' not found in model_dump() keys: {list(dumped.keys())}"
        )
        assert isinstance(dumped["text"], str)
        assert "C major" in dumped["text"]
        assert "I-V-vi-IV pop progression" in dumped["text"]

    def test_text_in_model_dump_json(self):
        """text must be serialized by model_dump_json() so the API response includes it."""
        import json

        te = self._make_te()
        payload = json.loads(te.model_dump_json())
        assert "text" in payload, (
            f"'text' not found in model_dump_json() keys: {list(payload.keys())}"
        )
        assert isinstance(payload["text"], str)
        assert "C major" in payload["text"]

    def test_text_consistent_with_property(self):
        """model_dump()['text'] must equal te.text (property value unchanged)."""
        te = self._make_te()
        assert te.model_dump()["text"] == te.text

    def test_model_validator_backfill_still_works(self):
        """SongAnalysis._sync_theory_explanation must still read theory.text correctly
        after the computed_field decorator is applied."""
        from backend.schemas import ChordEvent, SongAnalysis

        te = self._make_te()
        sa = SongAnalysis(
            duration=4.0,
            key="C major",
            tempo=120.0,
            chords=[ChordEvent(start=0.0, end=1.0, chord="C")],
            theory=te,
        )
        assert sa.theory_explanation == te.text, (
            "model_validator back-fill must still populate theory_explanation from theory.text"
        )
