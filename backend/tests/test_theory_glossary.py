"""Tests for the theory glossary data + the lookup_theory @tool (Group A)."""

from pathlib import Path

import yaml

_YAML_PATH = (
    Path(__file__).resolve().parents[1] / "knowledge" / "theory_glossary.yaml"
)


def _raw_entries() -> list[dict]:
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, list), "glossary YAML must be a top-level list"
    return raw


class TestGlossaryData:
    def test_yaml_exists_and_is_a_list(self):
        entries = _raw_entries()
        assert len(entries) >= 50, "expected ~50 curated entries"

    def test_every_entry_has_required_fields(self):
        for e in _raw_entries():
            assert set(("term", "aliases", "explanation", "snippet_id")) <= set(e), e
            assert isinstance(e["term"], str) and e["term"].strip(), e
            assert isinstance(e["aliases"], list), e
            assert all(isinstance(a, str) for a in e["aliases"]), e

    def test_explanations_non_empty(self):
        for e in _raw_entries():
            assert isinstance(e["explanation"], str)
            assert e["explanation"].strip(), f"empty explanation for {e['term']!r}"

    def test_snippet_ids_unique(self):
        ids = [e["snippet_id"] for e in _raw_entries()]
        assert len(ids) == len(set(ids)), "snippet_id values must be unique"
        assert all(isinstance(i, str) and i.strip() for i in ids)

    def test_core_topics_present(self):
        # Smoke that the curation actually covers the spec §4/§7 spine.
        terms = {e["term"].lower() for e in _raw_entries()}
        for required in (
            "secondary dominant",
            "circle of fifths",
            "cadence",
            "dorian mode",
            "perfect fifth",
        ):
            assert required in terms, f"missing core topic: {required}"


from backend.tools.theory_glossary import load_glossary


class TestLoadGlossary:
    def test_returns_list_of_dicts(self):
        entries = load_glossary()
        assert isinstance(entries, list)
        assert len(entries) >= 50
        assert all(isinstance(e, dict) for e in entries)

    def test_entries_carry_contract_fields(self):
        for e in load_glossary():
            assert {"term", "aliases", "explanation", "snippet_id"} <= set(e)

    def test_is_cached_same_object(self):
        # load_glossary() is cached: repeated calls return the identical object,
        # so callers (the @tool, on every invocation) never re-read the YAML.
        assert load_glossary() is load_glossary()

    def test_snippet_ids_unique_via_loader(self):
        ids = [e["snippet_id"] for e in load_glossary()]
        assert len(ids) == len(set(ids))


from backend.tools.theory_glossary import lookup_theory


def _invoke(term: str) -> str:
    # @tool produces a StructuredTool; call it the same way the agent will.
    return lookup_theory.invoke({"term": term})


class TestLookupTheory:
    def test_is_a_langchain_tool(self):
        # The agent registers this by name; keep the contract stable.
        assert lookup_theory.name == "lookup_theory"

    def test_exact_term_match_returns_cited_explanation(self):
        out = _invoke("secondary dominant")
        assert out.startswith("[theory:fn-secondary-dominant]")
        assert "tonicizes" in out.lower() or "dominant" in out.lower()

    def test_case_insensitive_term(self):
        assert _invoke("Circle Of Fifths").startswith("[theory:prog-circle-of-fifths]")

    def test_alias_match(self):
        # "ii-V-I" is an alias of the "two five one" entry.
        out = _invoke("ii-V-I")
        assert out.startswith("[theory:prog-ii-v-i]")

    def test_alias_match_case_insensitive(self):
        # "PAC" alias -> perfect authentic cadence.
        assert _invoke("pac").startswith("[theory:cad-authentic]")

    def test_substring_match_against_term(self):
        # "tritone" is a substring of no other term but the query carries extra
        # words; substring matching still locates the entry.
        out = _invoke("what is a tritone")
        assert out.startswith("[theory:int-tritone]")

    def test_substring_match_against_alias(self):
        # "amen" is an alias substring of the plagal cadence entry.
        out = _invoke("the amen cadence at the end")
        assert out.startswith("[theory:cad-plagal]")

    def test_exact_match_beats_substring(self):
        # "dominant" is an exact term (fn-dominant); it must NOT return the
        # longer "secondary dominant" entry just because it appears earlier.
        assert _invoke("dominant").startswith("[theory:fn-dominant]")

    def test_not_found_is_clear_message(self):
        out = _invoke("xylophone tuning quantum")
        assert "[theory:" not in out
        assert "couldn't find" in out.lower() or "no glossary entry" in out.lower()

    def test_empty_query_is_not_found(self):
        out = _invoke("")
        assert "[theory:" not in out

    def test_return_type_is_str(self):
        assert isinstance(_invoke("cadence"), str)


class TestGlossaryReachability:
    def test_every_term_resolves_to_its_own_snippet(self):
        # Exact-term lookup of each entry must return that entry's own citation.
        # Guards against duplicate terms shadowing one another.
        for e in load_glossary():
            out = lookup_theory.invoke({"term": e["term"]})
            assert out.startswith(f"[theory:{e['snippet_id']}]"), (
                f"{e['term']!r} resolved to the wrong entry: {out[:40]}"
            )

    def test_terms_are_unique(self):
        terms = [e["term"].lower() for e in load_glossary()]
        assert len(terms) == len(set(terms)), "duplicate term keys shadow lookups"


# ---------------------------------------------------------------------------
# Regression tests for Group A review fixes
# ---------------------------------------------------------------------------


class TestC1TritoneResolution:
    """C1: tritone explanation must describe inward resolution."""

    def test_tritone_says_inward_not_outward(self):
        out = _invoke("tritone")
        assert out.startswith("[theory:int-tritone]")
        assert "inward" in out.lower(), "tritone explanation should say 'inward'"
        assert "outward" not in out.lower(), "stale 'outward' wording must be removed"

    def test_tritone_mentions_leading_tone_and_seventh(self):
        out = _invoke("tritone")
        # The new copy specifically mentions leading tone rising and seventh falling
        assert "leading tone" in out.lower() or "half step" in out.lower()


class TestI1HalfDiminishedAlias:
    """I1: 'half diminished seventh' must resolve to chq-m7b5, NOT chq-dim7."""

    def test_half_diminished_seventh_resolves_to_m7b5(self):
        out = _invoke("half diminished seventh")
        assert out.startswith("[theory:chq-m7b5]"), (
            f"'half diminished seventh' resolved to wrong entry: {out[:60]}"
        )

    def test_half_diminished_seventh_hyphenated(self):
        out = _invoke("half-diminished seventh")
        assert out.startswith("[theory:chq-m7b5]"), (
            f"'half-diminished seventh' resolved to wrong entry: {out[:60]}"
        )

    def test_half_diminished_seventh_not_dim7(self):
        out = _invoke("half diminished seventh")
        assert "[theory:chq-dim7]" not in out


class TestI2WholeWordMatching:
    """I2: whole-word lookup prevents generic-word false matches."""

    def test_diatonic_does_not_cite_tonic(self):
        # "diatonic" contains "tonic" as a substring but not as a whole word
        out = _invoke("diatonic")
        assert "[theory:fn-tonic]" not in out, (
            "'diatonic' must not cite the tonic entry"
        )

    def test_picardy_third_does_not_cite_major_third(self):
        # "Picardy third" contains "third" but that is not a word-boundary match
        # for "M3" or "3rd"; the query should return not-found or a correct entry,
        # but never int-m3.
        out = _invoke("Picardy third")
        assert "[theory:int-m3]" not in out, (
            "'Picardy third' must not cite the major-third interval entry"
        )

    def test_the_fourth_measure_does_not_cite_perfect_fourth(self):
        out = _invoke("the fourth measure")
        assert "[theory:int-p4]" not in out, (
            "'the fourth measure' must not cite the perfect-fourth entry"
        )

    def test_tritone_real_lookup_still_works(self):
        out = _invoke("tritone")
        assert out.startswith("[theory:int-tritone]")

    def test_secondary_dominant_real_lookup_still_works(self):
        out = _invoke("secondary dominant")
        assert out.startswith("[theory:fn-secondary-dominant]")

    def test_ii_v_i_real_lookup_still_works(self):
        out = _invoke("ii-V-I")
        assert out.startswith("[theory:prog-ii-v-i]")

    def test_amen_cadence_real_lookup_still_works(self):
        out = _invoke("amen cadence")
        assert out.startswith("[theory:cad-plagal]")

    def test_dorian_mode_real_lookup_still_works(self):
        out = _invoke("dorian mode")
        assert out.startswith("[theory:mode-dorian]")


class TestI3ToolDescription:
    """I3: @tool docstring must guide the agent correctly."""

    def test_description_mentions_canonical_label(self):
        desc = lookup_theory.description.lower()
        assert "canonical" in desc or "label" in desc or "short" in desc

    def test_description_mentions_not_found_behavior(self):
        desc = lookup_theory.description.lower()
        assert "general knowledge" in desc or "not a cited fact" in desc

    def test_description_lists_concept_types(self):
        desc = lookup_theory.description.lower()
        # Should mention multiple concept types
        assert "interval" in desc
        assert "cadence" in desc or "progression" in desc


class TestM2LoadGlossaryValidation:
    """m2: load_glossary must validate entries at load time."""

    def test_all_entries_have_non_empty_term(self):
        # Indirectly verified: load_glossary() would raise if any entry was bad
        entries = load_glossary()
        for e in entries:
            assert e["term"].strip(), f"empty term: {e!r}"

    def test_all_entries_have_non_empty_explanation(self):
        entries = load_glossary()
        for e in entries:
            assert e["explanation"].strip(), f"empty explanation for {e['term']!r}"

    def test_all_entries_have_non_empty_snippet_id(self):
        entries = load_glossary()
        for e in entries:
            assert e["snippet_id"].strip(), f"empty snippet_id for {e['term']!r}"

    def test_all_entries_have_list_aliases(self):
        entries = load_glossary()
        for e in entries:
            assert isinstance(e["aliases"], list), (
                f"aliases must be a list for {e['term']!r}"
            )


class TestM5AuthenticCadenceIAC:
    """m5: authentic cadence entry must mention IAC."""

    def test_authentic_cadence_mentions_iac(self):
        out = _invoke("perfect authentic cadence")
        assert out.startswith("[theory:cad-authentic]")
        assert "iac" in out.lower() or "imperfect authentic" in out.lower(), (
            "authentic cadence entry should mention IAC"
        )
