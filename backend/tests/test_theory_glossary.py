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
