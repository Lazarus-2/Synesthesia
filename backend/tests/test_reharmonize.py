"""Theory Lab: deterministic reharmonization module + endpoint tests."""

from backend.theory.reharmonize import reharmonize

# music21 uses '-' for flats; normalise either spelling to a pitch class so
# enharmonic-spelling assertions don't depend on flat-vs-sharp choice.
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
                  "Cb": "B", "Fb": "E", "B#": "C", "E#": "F"}
_M21_FLATS = {"D-": "C#", "E-": "D#", "G-": "F#", "A-": "G#", "B-": "A#",
              "C-": "B", "F-": "E"}
_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _root_of(chord: str) -> str:
    """Extract a 1-2 char root token (letter + optional accidental)."""
    if len(chord) >= 2 and chord[1] in ("b", "#", "-"):
        return chord[:2]
    return chord[:1]


def _pc(root: str) -> int:
    """Pitch class of a root token, normalising flats (b or -) to sharps."""
    root = _M21_FLATS.get(root, root)
    root = _FLAT_TO_SHARP.get(root, root)
    return _NOTES.index(root)


def _types(suggestions: list[dict]) -> set[str]:
    return {s["type"] for s in suggestions}


# ---------------------------------------------------------------------------
# Module-level deterministic suggestions
# ---------------------------------------------------------------------------

def test_tritone_sub_on_dominant_seventh():
    out = reharmonize("C major", "C7")
    trit = [s for s in out if s["type"] == "tritone_sub"]
    assert trit, f"expected a tritone_sub for C7, got types {_types(out)}"
    # C7 tritone sub is built on F#/Gb (pitch class 6)
    assert _pc(_root_of(trit[0]["chord"])) == _pc("F#")


def test_no_tritone_sub_on_maj7():
    out = reharmonize("C major", "Cmaj7")
    assert "tritone_sub" not in _types(out), (
        "maj7 is not a dominant — must not yield a tritone substitution"
    )


def test_no_tritone_sub_on_minor_seventh():
    out = reharmonize("C major", "Dm7")
    assert "tritone_sub" not in _types(out)


def test_secondary_dominant_uses_next_chord():
    # V7/F is C7 (a perfect fifth above F).
    out = reharmonize("C major", "Dm7", next_chord="F")
    sec = [s for s in out if s["type"] == "secondary_dominant"]
    assert sec, f"expected a secondary_dominant given next_chord=F, got {_types(out)}"
    assert _pc(_root_of(sec[0]["chord"])) == _pc("C")
    assert sec[0]["chord"].rstrip("-").endswith("7") or "7" in sec[0]["chord"]


def test_no_secondary_dominant_without_next_chord():
    out = reharmonize("C major", "C")
    assert "secondary_dominant" not in _types(out)


def test_modal_interchange_major_to_minor():
    out = reharmonize("C major", "C")
    mi = [s for s in out if s["type"] == "modal_interchange"]
    assert mi, f"expected modal_interchange for a major chord, got {_types(out)}"
    # major chord -> minor counterpart on same root
    assert mi[0]["chord"].rstrip("0123456789").endswith("m") or "m" in mi[0]["chord"]
    assert _pc(_root_of(mi[0]["chord"])) == _pc("C")


def test_modal_interchange_minor_to_major():
    out = reharmonize("A minor", "Am")
    mi = [s for s in out if s["type"] == "modal_interchange"]
    assert mi, f"expected modal_interchange for a minor chord, got {_types(out)}"
    # minor chord -> major counterpart (no 'm' suffix)
    chord = mi[0]["chord"]
    assert not chord.rstrip("0123456789").endswith("m")
    assert _pc(_root_of(chord)) == _pc("A")


def test_relative_sub_major_to_relative_minor():
    out = reharmonize("C major", "C")
    rel = [s for s in out if s["type"] == "relative_sub"]
    assert rel, f"expected relative_sub for C, got {_types(out)}"
    # C major's relative substitute is Am
    assert _pc(_root_of(rel[0]["chord"])) == _pc("A")
    assert rel[0]["chord"].rstrip("0123456789").endswith("m")


def test_relative_sub_minor_to_relative_major():
    out = reharmonize("A minor", "Am")
    rel = [s for s in out if s["type"] == "relative_sub"]
    assert rel, f"expected relative_sub for Am, got {_types(out)}"
    # Am's relative major substitute is C
    assert _pc(_root_of(rel[0]["chord"])) == _pc("C")


def test_diatonic_third_substitution():
    out = reharmonize("C major", "C")
    dt = [s for s in out if s["type"] == "diatonic_third"]
    assert dt, f"expected diatonic_third for C (I->iii), got {_types(out)}"
    # I -> iii in C major is Em (pitch class E)
    assert _pc(_root_of(dt[0]["chord"])) == _pc("E")


def test_diatonic_third_spells_diminished_degree():
    # Regression: vii° in C major is B diminished (B-D-F), NOT Bm.
    # The integer RomanNumeral constructor raised the third and produced "Bm".
    out = reharmonize("C major", "G7")
    dt = [s for s in out if s["type"] == "diatonic_third"]
    assert dt, f"expected diatonic_third for G7 (V->vii), got {_types(out)}"
    chord = dt[0]["chord"]
    assert chord != "Bm", "vii° must not be mis-spelled as a minor triad"
    assert chord[:1] == "B", f"expected a B-rooted chord, got {chord!r}"
    lowered = chord.lower()
    assert ("dim" in lowered) or chord.endswith("o") or "°" in chord, (
        f"diatonic third of G7 must be diminished, got {chord!r}"
    )


def test_diatonic_third_diminished_in_flat_key():
    # Bb major, F7 (V7) -> vii° is A diminished, not "Am".
    out = reharmonize("Bb major", "F7")
    dt = [s for s in out if s["type"] == "diatonic_third"]
    assert dt, f"expected diatonic_third for F7 in Bb, got {_types(out)}"
    chord = dt[0]["chord"]
    assert chord != "Am"
    assert chord[:1] == "A"
    lowered = chord.lower()
    assert ("dim" in lowered) or chord.endswith("o") or "°" in chord, (
        f"diatonic third of F7 in Bb must be diminished, got {chord!r}"
    )


def test_diatonic_third_minor_degree_unchanged():
    # I -> iii in C major must remain Em (correct minor degree).
    out = reharmonize("C major", "C")
    dt = [s for s in out if s["type"] == "diatonic_third"]
    assert dt, f"expected diatonic_third for C, got {_types(out)}"
    assert dt[0]["chord"] == "Em"


def test_malformed_chord_returns_empty():
    # Unparseable chord input must not crash; returns [].
    assert reharmonize("C major", "???") == []


def test_slash_chord_does_not_raise():
    # A slash chord should produce suggestions without raising.
    out = reharmonize("C major", "G/B")
    assert isinstance(out, list)
    for s in out:
        assert set(s.keys()) >= {"type", "label", "chord", "explanation"}


def test_no_chord_returns_empty():
    assert reharmonize("C major", "N.C.") == []
    assert reharmonize("C major", "N") == []
    assert reharmonize("C major", "") == []


def test_flat_key_tritone_spelling():
    # F major, C7 (the V7) -> tritone sub built on F#/Gb (pitch class 6).
    out = reharmonize("F major", "C7")
    trit = [s for s in out if s["type"] == "tritone_sub"]
    assert trit, f"expected tritone_sub for C7 in F, got {_types(out)}"
    assert _pc(_root_of(trit[0]["chord"])) == _pc("F#")


def test_all_suggestions_have_required_keys():
    out = reharmonize("C major", "G7", next_chord="C")
    assert out, "expected at least one suggestion"
    for s in out:
        assert set(s.keys()) >= {"type", "label", "chord", "explanation"}
        assert all(isinstance(s[k], str) for k in ("type", "label", "chord", "explanation"))


def test_deterministic():
    a = reharmonize("C major", "G7", next_chord="C")
    b = reharmonize("C major", "G7", next_chord="C")
    assert a == b


# ---------------------------------------------------------------------------
# Endpoint tests (no auth, no db)
# ---------------------------------------------------------------------------

def test_endpoint_returns_suggestions(api_client):
    resp = api_client.post(
        "/api/v1/theory/reharmonize",
        json={"key": "C major", "chord": "C7"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "suggestions" in body
    assert isinstance(body["suggestions"], list)
    assert body["suggestions"], "expected non-empty suggestions for C7"
    for s in body["suggestions"]:
        assert set(s.keys()) >= {"type", "label", "chord", "explanation"}


def test_endpoint_empty_chord_400(api_client):
    resp = api_client.post(
        "/api/v1/theory/reharmonize",
        json={"key": "C major", "chord": ""},
    )
    assert resp.status_code == 400


def test_endpoint_next_chord_secondary_dominant(api_client):
    resp = api_client.post(
        "/api/v1/theory/reharmonize",
        json={"key": "C major", "chord": "Dm7", "next_chord": "F"},
    )
    assert resp.status_code == 200, resp.text
    types = {s["type"] for s in resp.json()["suggestions"]}
    assert "secondary_dominant" in types
