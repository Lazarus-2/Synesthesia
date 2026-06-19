"""G2.1 — TheoryExplanation lives in schemas.py; .text is computed from fields."""

from __future__ import annotations


class TestTheoryExplanationInSchemas:
    def test_import_from_schemas(self):
        """TheoryExplanation must be importable from backend.schemas."""
        from backend.schemas import TheoryExplanation  # noqa: F401

    def test_required_fields_present(self):
        from backend.schemas import TheoryExplanation

        te = TheoryExplanation(
            key_summary="Song is in C major.",
            function_explanation="C is tonic, G is dominant.",
        )
        assert te.key_summary == "Song is in C major."
        assert te.function_explanation == "C is tonic, G is dominant."
        assert te.pattern_name is None
        assert te.notable_techniques == []
        assert te.similar_song is None

    def test_text_field_is_computed_from_structured_fields(self):
        """The .text property must render the same Markdown _flatten used to produce."""
        from backend.schemas import TheoryExplanation

        te = TheoryExplanation(
            key_summary="Key: G major.",
            function_explanation="Tonic, dominant, etc.",
            pattern_name="I-V-vi-IV",
            notable_techniques=["modal mixture", "secondary dominant"],
            similar_song="Let It Be — Beatles",
        )
        text = te.text
        assert "G major" in text
        assert "**Pattern:** I-V-vi-IV" in text
        assert "modal mixture" in text
        assert "secondary dominant" in text
        assert "Let It Be" in text

    def test_text_field_minimal(self):
        """With only required fields, .text contains at least key_summary and function_explanation."""
        from backend.schemas import TheoryExplanation

        te = TheoryExplanation(
            key_summary="Key: A minor.",
            function_explanation="Am is tonic.",
        )
        assert "A minor" in te.text
        assert "Am is tonic" in te.text
        # No pattern/technique/similar lines
        assert "**Pattern:**" not in te.text
        assert "**Notable techniques:**" not in te.text

    def test_song_analysis_carries_theory_typed_field(self):
        """SongAnalysis must accept a `theory: TheoryExplanation | None` field."""
        from backend.schemas import SongAnalysis, TheoryExplanation

        te = TheoryExplanation(
            key_summary="C major.",
            function_explanation="Tonic.",
        )
        sa = SongAnalysis(
            duration=30.0,
            key="C major",
            tempo=120.0,
            chords=[],
            theory=te,
        )
        assert sa.theory is te

    def test_song_analysis_theory_explanation_backcompat(self):
        """SongAnalysis.theory_explanation must equal theory.text when theory is set."""
        from backend.schemas import SongAnalysis, TheoryExplanation

        te = TheoryExplanation(
            key_summary="D major.",
            function_explanation="I-V-vi-IV.",
            pattern_name="Pop progression",
        )
        sa = SongAnalysis(
            duration=30.0,
            key="D major",
            tempo=100.0,
            chords=[],
            theory=te,
        )
        # Back-compat: .theory_explanation should equal the rendered text
        assert sa.theory_explanation == te.text

    def test_song_analysis_legacy_theory_explanation_str_still_accepted(self):
        """Existing callers that set theory_explanation=str must still work (no TypeErrors)."""
        from backend.schemas import SongAnalysis

        sa = SongAnalysis(
            duration=30.0,
            key="E minor",
            tempo=90.0,
            chords=[],
            theory_explanation="Some old string explanation.",
        )
        assert sa.theory_explanation == "Some old string explanation."
        assert sa.theory is None


class TestAPISerializationContract:
    def test_analyze_response_json_includes_theory_object(self):
        """The JSON the API emits must include 'theory' as a nested object with
        the structured fields so the frontend can read them individually."""
        import json

        from backend.schemas import AnalyzeResponse, SongAnalysis, TheoryExplanation

        te = TheoryExplanation(
            key_summary="A major.",
            function_explanation="I-IV-V.",
            pattern_name="Blues",
            notable_techniques=["secondary dominant V/IV"],
            similar_song="Johnny B. Goode — Chuck Berry",
        )
        sa = SongAnalysis(
            duration=180.0, key="A major", tempo=140.0, chords=[], theory=te
        )
        resp = AnalyzeResponse(job_id="x", status="done", analysis=sa)
        payload = json.loads(resp.model_dump_json())

        theory_obj = payload["analysis"]["theory"]
        assert theory_obj["pattern_name"] == "Blues"
        assert "secondary dominant V/IV" in theory_obj["notable_techniques"]
        assert theory_obj["similar_song"] == "Johnny B. Goode — Chuck Berry"

        # Back-compat: flat string also present
        assert "theory_explanation" in payload["analysis"]
        assert isinstance(payload["analysis"]["theory_explanation"], str)
