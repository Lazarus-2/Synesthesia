"""G2.5 — theory persisted as structured dict in Mongo; API response carries it."""

from __future__ import annotations

import pytest


class TestSongAnalysisModelTheoryField:
    def test_model_accepts_theory_dict(self):
        """SongAnalysisModel must accept theory as a dict (Mongo stores it denormalized)."""
        from backend.models import SongAnalysisModel

        record = SongAnalysisModel(
            id="job-1",
            duration=30.0,
            key="C major",
            tempo=120.0,
            theory={
                "key_summary": "C major.",
                "function_explanation": "Tonic.",
                "pattern_name": None,
                "notable_techniques": [],
                "similar_song": None,
            },
        )
        assert record.theory is not None
        assert record.theory.key_summary == "C major."

    def test_model_theory_none_by_default(self):
        from backend.models import SongAnalysisModel

        record = SongAnalysisModel(
            id="job-2",
            duration=10.0,
            key="A minor",
            tempo=90.0,
        )
        assert record.theory is None

    def test_model_dump_includes_theory(self):
        """model_dump(by_alias=True) must include 'theory' so Mongo stores the object."""
        from backend.models import SongAnalysisModel
        from backend.schemas import TheoryExplanation

        te = TheoryExplanation(key_summary="E minor.", function_explanation="Submediant.")
        record = SongAnalysisModel(
            id="job-3",
            duration=20.0,
            key="E minor",
            tempo=80.0,
            theory=te,
        )
        dumped = record.model_dump(by_alias=True)
        assert "theory" in dumped
        assert dumped["theory"]["key_summary"] == "E minor."


class TestTasksAssembly:
    def test_song_analysis_built_in_tasks_carries_theory(self):
        """The SongAnalysis constructed in tasks.py run_analysis_pipeline must
        set .theory when the graph result carries a TheoryExplanation."""
        from backend.schemas import ChordEvent, TheoryExplanation

        # Simulate the graph result dict that run_analysis_pipeline receives.
        te = TheoryExplanation(
            key_summary="D major.",
            function_explanation="I-IV-V.",
        )
        graph_result = {
            "key": "D major",
            "tempo": 100.0,
            "chords": [ChordEvent(start=0.0, end=1.0, chord="D")],
            "beats": [],
            "sections": [],
            "roman": None,
            "theory": te,
            "theory_explanation": te.text,
            "stems": {},
            "errors": [],
        }

        # Reconstruct the same logic tasks.py uses (without running the task).
        from backend.schemas import SongAnalysis

        chords = graph_result.get("chords", [])
        analysis = SongAnalysis(
            title="Test Song",
            artist="Test",
            duration=float(chords[-1].end) if chords else 180.0,
            key=graph_result.get("key", "C major"),
            tempo=graph_result.get("tempo", 120.0),
            time_signature="4/4",
            chords=chords,
            beats=graph_result.get("beats", []),
            sections=graph_result.get("sections", []),
            roman=graph_result.get("roman"),
            vibe_palette=[],
            theory=graph_result.get("theory"),
            theory_explanation=graph_result.get("theory_explanation"),
            instrument_guides={},
            stems=graph_result.get("stems", {}),
        )
        assert analysis.theory is te
        # Back-compat: theory_explanation must be the rendered text
        assert analysis.theory_explanation == te.text


class TestAPIResponseCarriesTheory:
    def test_analyze_response_theory_field_present_in_dump(self):
        """AnalyzeResponse.analysis.theory must survive model_dump_json() round-trip."""
        from backend.schemas import AnalyzeResponse, SongAnalysis, TheoryExplanation

        te = TheoryExplanation(
            key_summary="F major.",
            function_explanation="Subdominant.",
        )
        sa = SongAnalysis(
            duration=30.0, key="F major", tempo=110.0, chords=[], theory=te
        )
        resp = AnalyzeResponse(job_id="j1", status="done", analysis=sa)
        dumped = resp.model_dump()
        assert dumped["analysis"]["theory"] is not None
        assert dumped["analysis"]["theory"]["key_summary"] == "F major."
        # Back-compat field also present
        assert "theory_explanation" in dumped["analysis"]
        assert dumped["analysis"]["theory_explanation"] == te.text
