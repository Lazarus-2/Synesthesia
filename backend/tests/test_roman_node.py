"""G1.11: roman_analysis_node delegates to analyze_roman; no placeholder strings."""
from backend.graph.nodes import roman_analysis_node
from backend.schemas import ChordEvent, RomanAnalysis


def _make_state(chords, key="C major"):
    return {"key": key, "chords": chords}


def test_node_returns_roman_analysis_dict():
    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="G7"),
        ChordEvent(start=4.0, end=6.0, chord="Am"),
        ChordEvent(start=6.0, end=8.0, chord="F"),
    ]
    state = _make_state(chords)
    result = roman_analysis_node(state)
    assert "roman" in result
    roman = result["roman"]
    assert isinstance(roman, RomanAnalysis)


def test_node_no_placeholder_strings():
    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="D7"),   # chromatic -> was 'bdegree'
        ChordEvent(start=4.0, end=6.0, chord="G"),
        ChordEvent(start=6.0, end=8.0, chord="Bb"),   # borrowed -> was 'bdegree'
    ]
    state = _make_state(chords)
    result = roman_analysis_node(state)
    roman = result["roman"]
    for entry in roman.entries:
        assert "degree" not in entry.numeral, (
            f"Placeholder numeral found: {entry.numeral!r} for chord {entry.chord!r}"
        )
    for num in roman.progression:
        assert "degree" not in num, f"Placeholder in progression: {num!r}"


def test_node_entries_time_aligned():
    chords = [
        ChordEvent(start=0.0, end=1.5, chord="C"),
        ChordEvent(start=1.5, end=3.0, chord="G"),
    ]
    state = _make_state(chords)
    result = roman_analysis_node(state)
    roman = result["roman"]
    assert roman.entries[0].start == 0.0
    assert roman.entries[0].end == 1.5
    assert roman.entries[1].start == 1.5
    assert roman.entries[1].end == 3.0


def test_node_empty_chords_returns_none():
    state = _make_state([])
    result = roman_analysis_node(state)
    assert result.get("roman") is None


def test_node_legacy_fields_populated():
    """progression and function must be non-empty for TheoryPanel.tsx back-compat."""
    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="G"),
    ]
    state = _make_state(chords)
    result = roman_analysis_node(state)
    roman = result["roman"]
    assert roman.progression  # non-empty list
    assert roman.function     # non-empty list


def test_node_cadence_in_result():
    chords = [
        ChordEvent(start=0.0, end=2.0, chord="F"),
        ChordEvent(start=2.0, end=4.0, chord="G"),
        ChordEvent(start=4.0, end=6.0, chord="C"),
    ]
    state = _make_state(chords)
    result = roman_analysis_node(state)
    roman = result["roman"]
    cadence_types = [c["type"] for c in roman.cadences]
    assert "PAC" in cadence_types
