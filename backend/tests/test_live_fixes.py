"""Regression tests for the live-session bug fixes.

A: youtube.com/results?search_query=… URLs must convert to a ytsearch1 target
   (yt-dlp can't download a results page) — backend.ingestion.url_resolver.
B: MusicBrainz query must match artist names, not just recording titles, and
   support a year filter — backend.search.build_mb_query + merged relevance sort.
"""

from __future__ import annotations

from backend.ingestion.url_resolver import youtube_search_query
from backend.search import build_mb_query


class TestYoutubeSearchQuery:
    def test_results_url_yields_query(self):
        url = "https://www.youtube.com/results?search_query=Creep%20Radiohead"
        assert youtube_search_query(url) == "Creep Radiohead"

    def test_plain_watch_url_is_none(self):
        assert youtube_search_query("https://www.youtube.com/watch?v=abc123") is None

    def test_youtu_be_short_url_is_none(self):
        assert youtube_search_query("https://youtu.be/abc123") is None

    def test_non_youtube_is_none(self):
        assert youtube_search_query("https://open.spotify.com/track/x") is None

    def test_empty_search_query_is_none(self):
        assert youtube_search_query("https://www.youtube.com/results?search_query=") is None

    def test_trailing_slash_results(self):
        url = "https://m.youtube.com/results/?search_query=blackbird"
        assert youtube_search_query(url) == "blackbird"


class TestBuildMbQuery:
    def test_matches_both_artist_and_recording(self):
        q = build_mb_query("radiohead")
        assert "artist:(radiohead)" in q
        assert "recording:(radiohead)" in q
        assert " OR " in q

    def test_extracts_year_filter(self):
        q = build_mb_query("creep 1992")
        assert "date:1992" in q
        # the year is stripped from the text terms
        assert "recording:(creep)" in q
        assert "1992" not in q.split("date:")[0]

    def test_no_year_no_date_filter(self):
        q = build_mb_query("blackbird beatles")
        assert "firstreleasedate" not in q

    def test_strips_lucene_specials(self):
        # A user pasting quotes/colons must not produce a malformed query.
        q = build_mb_query('the "best": song?')
        assert ":" not in q.replace("recording:", "").replace("artist:", "")
        assert "?" not in q

    def test_year_only_query_is_safe(self):
        q = build_mb_query("2019")
        assert "date:2019" in q
        # still has a recording/artist clause (falls back to the raw text)
        assert "recording:(" in q


class TestMergedRelevanceSort:
    async def test_sorts_by_score_descending(self, monkeypatch):
        import backend.search as s

        async def fake_dz(q, limit=10):
            return []

        async def fake_mb(q, limit=10):
            return [
                {"source": "musicbrainz", "title": "Low", "artist": "A", "score": 40, "mbid": "1"},
                {"source": "musicbrainz", "title": "High", "artist": "B", "score": 95, "mbid": "2"},
            ]

        monkeypatch.setattr(s, "search_deezer", fake_dz)
        monkeypatch.setattr(s, "search_musicbrainz", fake_mb)
        out = await s.merged_search("x", limit=10)
        assert [r["title"] for r in out] == ["High", "Low"]

    async def test_deezer_rank_outranks_low_mb_score(self, monkeypatch):
        import backend.search as s

        async def fake_dz(q, limit=10):
            return [
                {"source": "deezer", "title": "Popular", "artist": "P", "rank": 800000, "deezer_id": 9}
            ]

        async def fake_mb(q, limit=10):
            return [
                {"source": "musicbrainz", "title": "Obscure", "artist": "O", "score": 50, "mbid": "3"}
            ]

        monkeypatch.setattr(s, "search_deezer", fake_dz)
        monkeypatch.setattr(s, "search_musicbrainz", fake_mb)
        out = await s.merged_search("x", limit=10)
        assert out[0]["title"] == "Popular"
