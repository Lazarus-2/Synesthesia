"""Unit tests for backend.ingestion.acoustid_enrich.

We can't depend on the AcoustID API in unit tests (network + free-tier
key + flaky), so we mock everything below the API boundary. Tests
exercise the three graceful-fail paths (no fpcalc, no API key, no
match) plus the happy path.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.ingestion import acoustid_enrich


def test_fingerprint_file_returns_none_when_fpcalc_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(acoustid_enrich, "_fpcalc_available", lambda: False)
    assert acoustid_enrich.fingerprint_file(tmp_path / "x.wav") is None


def test_lookup_mbid_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("ACOUSTID_API_KEY", raising=False)
    assert acoustid_enrich.lookup_mbid(180, "abc") is None


def test_lookup_mbid_returns_none_when_no_results(monkeypatch):
    monkeypatch.setenv("ACOUSTID_API_KEY", "fake-key")
    with patch("acoustid.lookup", return_value={}), patch(
        "acoustid.parse_lookup_result", return_value=iter([])
    ):
        assert acoustid_enrich.lookup_mbid(180, "abc") is None


def test_lookup_mbid_filters_low_confidence_matches(monkeypatch):
    monkeypatch.setenv("ACOUSTID_API_KEY", "fake-key")
    low_score = iter([(0.4, "mbid-1", "Maybe Song", "Maybe Artist")])
    with patch("acoustid.lookup", return_value={}), patch(
        "acoustid.parse_lookup_result", return_value=low_score
    ):
        assert acoustid_enrich.lookup_mbid(180, "abc") is None


def test_lookup_mbid_happy_path(monkeypatch):
    monkeypatch.setenv("ACOUSTID_API_KEY", "fake-key")
    good_match = iter([(0.95, "mbid-42", "Blackbird", "The Beatles")])
    with patch("acoustid.lookup", return_value={}), patch(
        "acoustid.parse_lookup_result", return_value=good_match
    ):
        got = acoustid_enrich.lookup_mbid(138, "abc")
    assert got == {
        "mbid": "mbid-42",
        "title": "Blackbird",
        "artist": "The Beatles",
        "score": pytest.approx(0.95),
    }


def test_enrich_upload_returns_empty_when_no_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(acoustid_enrich, "_fpcalc_available", lambda: False)
    assert acoustid_enrich.enrich_upload(tmp_path / "x.wav") == {}


def test_enrich_upload_returns_metadata_on_match(monkeypatch):
    monkeypatch.setenv("ACOUSTID_API_KEY", "fake-key")
    monkeypatch.setattr(acoustid_enrich, "_fpcalc_available", lambda: True)
    monkeypatch.setattr(acoustid_enrich, "fingerprint_file", lambda _p: (138, "abc"))
    good_match = iter([(0.95, "mbid-42", "Blackbird", "The Beatles")])
    with patch("acoustid.lookup", return_value={}), patch(
        "acoustid.parse_lookup_result", return_value=good_match
    ):
        got = acoustid_enrich.enrich_upload("anything.wav")
    assert got == {
        "title": "Blackbird",
        "artist": "The Beatles",
        "mbid": "mbid-42",
    }
