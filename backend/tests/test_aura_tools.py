"""Group B — @tool wrappers over the deterministic music tools (no LLM)."""

from __future__ import annotations

from langchain_core.tools import BaseTool


class TestGetChordVoicing:
    def test_returns_diagram_for_known_chord(self):
        from backend.chains.aura_tools import get_chord_voicing

        out = get_chord_voicing.invoke({"chord": "C", "instrument": "guitar"})
        assert isinstance(out, dict)
        assert out["chord"] == "C"
        assert out["instrument"] == "guitar"
        # C major on guitar -> frets present
        assert out["frets"] == [-1, 3, 2, 0, 1, 0]

    def test_seventh_chord_not_dropped(self):
        from backend.chains.aura_tools import get_chord_voicing

        out = get_chord_voicing.invoke({"chord": "G7", "instrument": "guitar"})
        assert out["chord"] == "G7"
        assert out["frets"] is not None

    def test_piano_voicing_uses_hands(self):
        from backend.chains.aura_tools import get_chord_voicing

        out = get_chord_voicing.invoke({"chord": "C", "instrument": "piano"})
        assert out["right_hand"] == ["C4", "E4", "G4"]

    def test_unknown_chord_returns_not_found(self):
        from backend.chains.aura_tools import get_chord_voicing

        out = get_chord_voicing.invoke({"chord": "ZZZ", "instrument": "guitar"})
        assert "found" in out["error"].lower()

    def test_is_a_langchain_tool_with_schema(self):
        from backend.chains.aura_tools import get_chord_voicing

        assert isinstance(get_chord_voicing, BaseTool)
        assert get_chord_voicing.name == "get_chord_voicing"
        assert get_chord_voicing.description
        schema = get_chord_voicing.args_schema.model_json_schema()
        assert "chord" in schema["properties"]
        assert "instrument" in schema["properties"]


class TestGetChordColor:
    def test_returns_hex_color(self):
        from backend.chains.aura_tools import get_chord_color_tool

        out = get_chord_color_tool.invoke({"chord": "C"})
        assert isinstance(out, dict)
        assert out["chord"] == "C"
        assert out["root"] == "C"
        assert out["color"].startswith("#")
        assert len(out["color"]) == 7

    def test_maj7_is_not_treated_as_minor(self):
        from backend.chains.aura_tools import get_chord_color_tool

        # parse_chord-backed: Cmaj7 root is C, not mis-parsed.
        out = get_chord_color_tool.invoke({"chord": "Cmaj7"})
        assert out["root"] == "C"
        # maj7 takes the extended/fluorescent branch, not the minor branch,
        # so it must differ from the plain minor color of the same root.
        from backend.tools.synesthesia_colors import get_chord_color as raw

        assert out["color"] == raw("Cmaj7")

    def test_no_chord_returns_dark(self):
        from backend.chains.aura_tools import get_chord_color_tool

        out = get_chord_color_tool.invoke({"chord": "N.C."})
        assert out["color"] == "#1A1A1A"

    def test_is_a_langchain_tool_with_schema(self):
        from langchain_core.tools import BaseTool

        from backend.chains.aura_tools import get_chord_color_tool

        assert isinstance(get_chord_color_tool, BaseTool)
        assert get_chord_color_tool.name == "get_chord_color"
        assert get_chord_color_tool.description
        schema = get_chord_color_tool.args_schema.model_json_schema()
        assert "chord" in schema["properties"]


class _FakeAnalysisRepo:
    """Stands in for AnalysisRepo.get — async, no Mongo."""

    def __init__(self, doc: dict | None):
        self._doc = doc

    async def get(self, job_id: str):
        return self._doc if (self._doc and self._doc.get("_id") == job_id) else None


_STORED_DOC = {
    "_id": "job-abc",
    "title": "Let It Be",
    "artist": "The Beatles",
    "key": "C major",
    "tempo": 72.0,
    "status": "ok",
    "chords": [
        {"start": 0.0, "end": 2.0, "chord": "C", "confidence": 0.9, "color": "#FF0000"},
        {"start": 2.0, "end": 4.0, "chord": "G", "confidence": 0.9, "color": "#FF7F00"},
        {"start": 4.0, "end": 6.0, "chord": "Am", "confidence": 0.9, "color": "#00FF00"},
    ],
    "sections": [{"name": "verse", "start": 0.0, "end": 6.0}],
    "roman": {"key": "C major", "progression": ["I", "V", "vi"], "function": []},
}


class TestGetSongAnalysis:
    def test_returns_compact_facts(self, monkeypatch):
        import backend.chains.aura_tools as at
        from backend.chains.aura_tools import get_song_analysis

        monkeypatch.setattr(at, "_resolve_analysis_repo", lambda: _FakeAnalysisRepo(_STORED_DOC))

        out = get_song_analysis.invoke({"job_id": "job-abc"})
        assert out["title"] == "Let It Be"
        assert out["key"] == "C major"
        assert out["tempo"] == 72.0
        assert out["status"] == "ok"
        # chords collapsed to bare symbols (de-duped, order preserved)
        assert out["chords"] == ["C", "G", "Am"]
        assert out["roman"] == ["I", "V", "vi"]
        assert out["sections"] == ["verse"]

    def test_missing_job_returns_not_found(self, monkeypatch):
        import backend.chains.aura_tools as at
        from backend.chains.aura_tools import get_song_analysis

        monkeypatch.setattr(at, "_resolve_analysis_repo", lambda: _FakeAnalysisRepo(None))

        out = get_song_analysis.invoke({"job_id": "nope"})
        assert "found" in out["error"].lower()

    def test_is_a_langchain_tool_with_schema(self):
        from langchain_core.tools import BaseTool

        from backend.chains.aura_tools import get_song_analysis

        assert isinstance(get_song_analysis, BaseTool)
        assert get_song_analysis.name == "get_song_analysis"
        assert get_song_analysis.description
        assert "job_id" in get_song_analysis.args_schema.model_json_schema()["properties"]


class TestFindSimilarSongs:
    def test_returns_ranked_matches(self, monkeypatch):
        import backend.chains.aura_tools as at
        from backend.chains.aura_tools import find_similar_songs

        monkeypatch.setattr(at, "_resolve_analysis_repo", lambda: _FakeAnalysisRepo(_STORED_DOC))

        out = find_similar_songs.invoke({"analysis_job_id": "job-abc"})
        assert isinstance(out, list)
        assert out, "expected at least one similar-song match"
        first = out[0]
        assert {"title", "artist", "progression", "score"} <= set(first)
        # scores are descending (find_similar already sorts)
        scores = [r["score"] for r in out]
        assert scores == sorted(scores, reverse=True)

    def test_missing_job_returns_not_found(self, monkeypatch):
        import backend.chains.aura_tools as at
        from backend.chains.aura_tools import find_similar_songs

        monkeypatch.setattr(at, "_resolve_analysis_repo", lambda: _FakeAnalysisRepo(None))

        out = find_similar_songs.invoke({"analysis_job_id": "nope"})
        assert isinstance(out, dict)
        assert "found" in out["error"].lower()

    def test_no_chords_returns_clear_message(self, monkeypatch):
        import backend.chains.aura_tools as at
        from backend.chains.aura_tools import find_similar_songs

        doc = {"_id": "job-empty", "key": "C major", "chords": []}
        monkeypatch.setattr(at, "_resolve_analysis_repo", lambda: _FakeAnalysisRepo(doc))

        out = find_similar_songs.invoke({"analysis_job_id": "job-empty"})
        assert isinstance(out, dict)
        assert "chord" in out["error"].lower()

    def test_is_a_langchain_tool_with_schema(self):
        from langchain_core.tools import BaseTool

        from backend.chains.aura_tools import find_similar_songs

        assert isinstance(find_similar_songs, BaseTool)
        assert find_similar_songs.name == "find_similar_songs"
        assert find_similar_songs.description
        props = find_similar_songs.args_schema.model_json_schema()["properties"]
        assert "analysis_job_id" in props


class TestToolsList:
    def test_tools_has_all_seven_in_order(self):
        from backend.chains.aura_tools import TOOLS

        names = [t.name for t in TOOLS]
        assert names == [
            "transpose_progression",
            "suggest_capo",
            "get_chord_voicing",
            "get_chord_color",
            "find_similar_songs",
            "get_song_analysis",
            "lookup_theory",
        ]

    def test_every_tool_has_name_description_and_schema(self):
        from langchain_core.tools import BaseTool

        from backend.chains.aura_tools import TOOLS

        for t in TOOLS:
            assert isinstance(t, BaseTool)
            assert t.name, f"{t} missing name"
            assert t.description, f"{t.name} missing description"
            assert t.args_schema is not None, f"{t.name} missing args_schema"

    def test_tool_names_are_unique(self):
        from backend.chains.aura_tools import TOOLS

        names = [t.name for t in TOOLS]
        assert len(names) == len(set(names))
