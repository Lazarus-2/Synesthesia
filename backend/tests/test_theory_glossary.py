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
