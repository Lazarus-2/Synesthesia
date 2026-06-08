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
