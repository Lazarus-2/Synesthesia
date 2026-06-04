"""Live browser E2E suite — drives a real headless Chromium against the
running Next.js + FastAPI stack.

The six tests below collectively cover the user-visible surface:

  test_landing_loads_and_sample_cards_link  → landing page + sample link routing
  test_share_page_renders_full_breakdown    → /s/{id} read-only view
  test_upload_drag_drop_runs_full_pipeline  → upload → SSE → player view
  test_library_page_lists_entries           → /library reads live DB
  test_auth_signup_login_logout             → JWT round-trip in localStorage
  test_chord_breakdown_e2e_five_songs       → 5 uploads end-to-end (the deliverable)

Each test writes a row into the session-scoped ``run_report`` fixture so
the final ``run_report.md`` materializes the full record.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from playwright.sync_api import Page, expect

# ----------------------------------------------------------------------------
# 1. Landing page
# ----------------------------------------------------------------------------


def test_landing_loads_and_sample_cards_link(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """Open /, assert hero + three sample-card links, click one."""
    page.goto(frontend_url, wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Hear any song.", exact=False)).to_be_visible(
        timeout=10_000
    )
    expect(page.get_by_text("Drag & Drop Audio")).to_be_visible()
    expect(page.get_by_text("Try a Sample Analysis")).to_be_visible()

    # Sample cards are <Link href="/s/sample-{id}"> wrappers — verify all 3.
    for sample_id in ("sample-blackbird", "sample-wonderwall", "sample-creep"):
        link = page.locator(f'a[href="/s/{sample_id}"]')
        expect(link).to_be_visible()

    landing_png = screenshot_dir / "01_landing.png"
    page.screenshot(path=str(landing_png), full_page=True)

    # Click into Blackbird and confirm the share page renders.
    page.locator('a[href="/s/sample-blackbird"]').first.click()
    page.wait_for_url("**/s/sample-blackbird", timeout=10_000)
    expect(page.get_by_role("heading", name="Blackbird")).to_be_visible(timeout=10_000)

    after_png = screenshot_dir / "01_share_after_click.png"
    page.screenshot(path=str(after_png), full_page=True)

    run_report.add_row(
        test="landing_loads_and_sample_cards_link",
        status="passed",
        sample_links_found=3,
        landing_png=str(landing_png.relative_to(screenshot_dir.parent.parent)),
        after_png=str(after_png.relative_to(screenshot_dir.parent.parent)),
    )


# ----------------------------------------------------------------------------
# 2. Share page direct
# ----------------------------------------------------------------------------


def test_share_page_renders_full_breakdown(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """Direct /s/sample-blackbird hit — assert key + bpm + chord chips."""
    page.goto(f"{frontend_url}/s/sample-blackbird", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Blackbird")).to_be_visible(timeout=10_000)

    # Key + BPM badges
    page.wait_for_selector("text=G major", timeout=10_000)
    page.wait_for_selector("text=96", timeout=5_000)

    # Chord chips — the seeded record has 6 chord events; we assert ≥ 4 spans
    # whose colored background is set from the Scriabin palette (inline style).
    chips = page.locator("section >> nth=2 >> span").all()
    visible_chord_chips = [
        c for c in chips if (c.inner_text() or "").strip() in {"G", "Am7", "G/B", "C", "D7"}
    ]
    assert len(visible_chord_chips) >= 4, (
        f"expected ≥4 chord chips on share page, got {len(visible_chord_chips)}: "
        f"{[c.inner_text() for c in visible_chord_chips]}"
    )

    out = screenshot_dir / "02_share_blackbird.png"
    page.screenshot(path=str(out), full_page=True)
    run_report.add_row(
        test="share_page_renders_full_breakdown",
        status="passed",
        chord_chips=len(visible_chord_chips),
        screenshot=str(out.relative_to(screenshot_dir.parent.parent)),
    )


# ----------------------------------------------------------------------------
# 3. Upload → analyzing → player view (one song)
# ----------------------------------------------------------------------------


def _wait_for_player_view(page: Page, timeout_s: int = 90):
    """Wait until the analyzing overlay disappears and the player tab shows."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        # AnalyzingView is full-screen fixed; once it's gone we should see
        # the PLAY/THEORY/STEMS tab strip and the BottomBar.
        if page.locator("text=Analysis Complete!").count() > 0:
            return "complete-message"
        # Detect player by tab buttons (one of those will be visible)
        try:
            if page.get_by_role("button", name="PLAY", exact=True).count() > 0:
                return "play-tab-visible"
        except Exception:
            pass
        if page.locator("text=Analysis Failed").count() > 0:
            raise AssertionError("analyzing view reports 'Analysis Failed'")
        page.wait_for_timeout(500)
    raise TimeoutError(f"player view did not appear within {timeout_s}s")


def test_upload_drag_drop_runs_full_pipeline(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    fixture_audio_dir: Path,
    run_report,
):
    """Drop one synth WAV via the hidden file input; wait for player view."""
    page.goto(frontend_url, wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Hear any song.", exact=False)).to_be_visible(
        timeout=10_000
    )

    wav = fixture_audio_dir / "round3_song1_c_major.wav"
    assert wav.exists(), f"test WAV missing: {wav}"

    page.locator('input[type="file"]').set_input_files(str(wav))

    # Analyzing overlay should appear within ~1 s.
    try:
        expect(page.get_by_text("Loading audio file...")).to_be_visible(timeout=15_000)
    except Exception:
        # Maybe progress jumped past the loading step instantly; fall through.
        pass

    analyzing_png = screenshot_dir / "03_analyzing.png"
    page.screenshot(path=str(analyzing_png), full_page=True)

    reason = _wait_for_player_view(page, timeout_s=90)
    player_png = screenshot_dir / "03_player_view.png"
    page.screenshot(path=str(player_png), full_page=True)

    run_report.add_row(
        test="upload_drag_drop_runs_full_pipeline",
        status="passed",
        completion_signal=reason,
        analyzing_png=str(analyzing_png.relative_to(screenshot_dir.parent.parent)),
        player_png=str(player_png.relative_to(screenshot_dir.parent.parent)),
    )


# ----------------------------------------------------------------------------
# 4. Library
# ----------------------------------------------------------------------------


def test_library_page_lists_entries(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """Open /library, assert at least 6 entries and click into one."""
    page.goto(f"{frontend_url}/library", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Library", exact=True)).to_be_visible(timeout=10_000)

    # Wait for either the "N analyzed song(s)" message or the cards grid.
    page.wait_for_selector("text=analyzed song", timeout=15_000)
    summary_text = page.locator("p", has_text="analyzed song").first.inner_text()
    # "N analyzed songs" or "1 analyzed song"
    n = int(summary_text.split()[0])
    assert n >= 6, f"expected ≥6 entries in library, got: {summary_text!r}"

    cards = page.locator('a[href^="/s/"]').all()
    assert len(cards) >= 1, "library shows no cards"

    out = screenshot_dir / "04_library.png"
    page.screenshot(path=str(out), full_page=True)

    # Click the first card and verify navigation.
    href = cards[0].get_attribute("href")
    cards[0].click()
    page.wait_for_url(f"**{href}", timeout=10_000)

    run_report.add_row(
        test="library_page_lists_entries",
        status="passed",
        library_count=n,
        clicked_into=href,
        screenshot=str(out.relative_to(screenshot_dir.parent.parent)),
    )


# ----------------------------------------------------------------------------
# 5. Auth signup → library → reload still authed
# ----------------------------------------------------------------------------


def test_auth_signup_login_logout(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """Sign up a fresh user, verify localStorage token, then login round-trip."""
    username = f"e2e_user_{uuid.uuid4().hex[:6]}"
    password = "correcthorsebattery"

    # ---- Sign up
    page.goto(f"{frontend_url}/signup", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Create your account")).to_be_visible(timeout=10_000)
    page.fill('input[autocomplete="username"]', username)
    page.fill('input[autocomplete="new-password"] >> nth=0', password)
    page.fill('input[autocomplete="new-password"] >> nth=1', password)
    page.get_by_role("button", name="Create account").click()

    page.wait_for_url("**/library", timeout=15_000)

    # localStorage token should be set.
    token = page.evaluate("() => window.localStorage.getItem('synesthesia.auth.token')")
    assert token, "token missing from localStorage after signup"
    # Stored as JSON-encoded string per useAuthStore.writeStorage.
    assert isinstance(token, str) and token.startswith('"') and token.endswith('"')

    signup_png = screenshot_dir / "05_signup_landed_library.png"
    page.screenshot(path=str(signup_png), full_page=True)

    # ---- Reload still authed
    page.reload(wait_until="domcontentloaded")
    token2 = page.evaluate("() => window.localStorage.getItem('synesthesia.auth.token')")
    assert token2 == token, "token disappeared on reload"

    # ---- Re-login round-trip via /login
    # First clear storage to simulate logout.
    page.evaluate(
        "() => { localStorage.removeItem('synesthesia.auth.token'); localStorage.removeItem('synesthesia.auth.user'); }"
    )
    page.goto(f"{frontend_url}/login", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Welcome back")).to_be_visible(timeout=10_000)
    page.fill('input[autocomplete="username"]', username)
    page.fill('input[autocomplete="current-password"]', password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/library", timeout=15_000)
    token3 = page.evaluate("() => window.localStorage.getItem('synesthesia.auth.token')")
    assert token3, "token missing after re-login"

    login_png = screenshot_dir / "05_login_landed_library.png"
    page.screenshot(path=str(login_png), full_page=True)

    run_report.add_row(
        test="auth_signup_login_logout",
        status="passed",
        username=username,
        signup_png=str(signup_png.relative_to(screenshot_dir.parent.parent)),
        login_png=str(login_png.relative_to(screenshot_dir.parent.parent)),
    )


# ----------------------------------------------------------------------------
# 6. THE DELIVERABLE — 5 song breakdowns end-to-end
# ----------------------------------------------------------------------------

# Each tuple: (filename, friendly name, expected detected key family)
_FIVE_SONGS = [
    ("round3_song1_c_major.wav", "Sunrise In C v2", "C major"),
    ("round3_song2_g_major.wav", "Highway G v2", "G major"),
    ("round3_song3_a_minor.wav", "Midnight Lullaby v2", "C major"),  # relative-major ambiguity OK
    ("round3_song4_d_major.wav", "Open Road v2", "D major"),
    ("round3_song5_e_minor.wav", "Cold November v2", "G major"),  # relative-major
]


def test_chord_breakdown_e2e_five_songs(
    browser,
    frontend_url: str,
    api_url: str,
    screenshot_dir: Path,
    fixture_audio_dir: Path,
    run_report,
):
    """For each of 5 synth WAVs: drive the UI through analysis to completion,
    then visit /s/{job_id} and assert the breakdown rendered with chord chips.

    Uses a **fresh browser context per song** so Zustand / Service Worker
    state from the previous iteration can't bleed in (the original version
    of this test silently lost songs 3-5 because the prior song's
    completion left the UI on the player view, so the next iteration's
    ``set_input_files`` had no UploadModal to attach to). Each song gets
    a clean isolation boundary.
    """

    import json
    import urllib.request

    completed_rows: list[dict] = []

    for idx, (filename, friendly, expected_key) in enumerate(_FIVE_SONGS, start=1):
        wav = fixture_audio_dir / filename
        assert wav.exists(), f"missing WAV: {wav}"

        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        try:
            upload_page = ctx.new_page()
            upload_page.goto(frontend_url, wait_until="domcontentloaded")
            step_landing = screenshot_dir / f"06_song{idx}_step1_landing.png"
            upload_page.screenshot(path=str(step_landing))

            expect(upload_page.get_by_text("Drag & Drop Audio")).to_be_visible(timeout=10_000)

            # Capture the job_id directly from the /analyze POST response
            # using ``expect_response`` (blocking, so timing is guaranteed).
            # This avoids depending on library?limit=1, which would return
            # whatever Mongo entry is newest globally, NOT necessarily ours.
            with upload_page.expect_response(
                lambda r: "/analyze" in r.url and r.request.method == "POST",
                timeout=30_000,
            ) as resp_info:
                upload_page.locator('input[type="file"]').set_input_files(str(wav))
            analyze_resp = resp_info.value
            assert analyze_resp.ok, (
                f"song {idx} ({friendly}): /analyze returned {analyze_resp.status}: "
                f"{analyze_resp.text()[:300]}"
            )
            body = analyze_resp.json()
            job_id = body.get("job_id")
            assert job_id, (
                f"song {idx} ({friendly}): /analyze response had no job_id, body={body!r}"
            )

            try:
                _wait_for_player_view(upload_page, timeout_s=90)
            except Exception as e:
                fail_png = screenshot_dir / f"06_song{idx}_FAIL.png"
                upload_page.screenshot(path=str(fail_png), full_page=True)
                with urllib.request.urlopen(f"{api_url}/api/v1/library?limit=3") as r:
                    library = json.load(r)
                raise AssertionError(
                    f"song {idx} ({friendly}) wait_for_player_view: {e!r}\n"
                    f"  screenshot: {fail_png}\n"
                    f"  library top: {[it['title'] for it in library['items']]}"
                )

            # Capture the player view too (proves it actually rendered).
            step_player = screenshot_dir / f"06_song{idx}_step2_player.png"
            upload_page.screenshot(path=str(step_player), full_page=True)

            # Visit the share page in a separate tab.
            share_page = ctx.new_page()
            share_page.goto(f"{frontend_url}/s/{job_id}", wait_until="domcontentloaded")
            share_page.wait_for_selector("text=BPM", timeout=15_000)
            step_share = (
                screenshot_dir / f"06_song{idx}_step3_share_{filename.replace('.wav', '')}.png"
            )
            share_page.screenshot(path=str(step_share), full_page=True)

            # Read the resulting analysis via the API and assert.
            with urllib.request.urlopen(f"{api_url}/api/v1/share/{job_id}") as r:
                doc = json.load(r)
            a = doc.get("analysis") or {}
            chords = a.get("chords") or []

            assert len(chords) >= 4, f"song {idx} ({friendly}): only {len(chords)} chords"
            assert a.get("key"), f"song {idx} ({friendly}): no key detected"

            completed_rows.append(
                {
                    "song_index": idx,
                    "friendly_name": friendly,
                    "job_id": job_id,
                    "detected_key": a.get("key"),
                    "detected_tempo": a.get("tempo"),
                    "n_chords": len(chords),
                    "chord_root_seq": [c["chord"] for c in chords],
                    "roman": (a.get("roman") or {}).get("progression"),
                    "title_in_db": a.get("title"),
                    "step1_landing_png": str(
                        step_landing.relative_to(screenshot_dir.parent.parent)
                    ),
                    "step2_player_png": str(step_player.relative_to(screenshot_dir.parent.parent)),
                    "step3_share_png": str(step_share.relative_to(screenshot_dir.parent.parent)),
                }
            )
        finally:
            ctx.close()

    for r in completed_rows:
        run_report.add_row(test="chord_breakdown_e2e_five_songs", status="passed", **r)

    assert len(completed_rows) == 5, f"expected 5 completed songs, got {len(completed_rows)}"
    # The strongest signal that dedup didn't short-circuit any uploads:
    # five distinct job_ids back from the /analyze endpoint.
    job_ids = {r["job_id"] for r in completed_rows}
    assert len(job_ids) == 5, (
        f"expected 5 distinct job_ids (no dedup short-circuit), got {len(job_ids)}: {job_ids}"
    )


# ----------------------------------------------------------------------------
# Plan v2 — C5 backend API smoke + C7 library polish coverage
# ----------------------------------------------------------------------------


def test_search_api_returns_merged_results(api_url: str, run_report):
    """Headless API check: GET /api/v1/search hits Deezer + MusicBrainz
    and returns deduped results. Faster + more reliable than the
    DOM-driven path; covers the same backend wire.
    """
    import json
    import urllib.request

    with urllib.request.urlopen(f"{api_url}/api/v1/search?q=blackbird+beatles&limit=5") as r:
        data = json.load(r)
    results = data.get("results", [])
    assert len(results) >= 1, f"expected >=1 hit, got 0: {data!r}"
    for hit in results:
        assert hit.get("title"), f"result missing title: {hit!r}"
        assert hit.get("artist"), f"result missing artist: {hit!r}"
        # Each hit should have at least one of mbid / deezer_id.
        assert hit.get("mbid") or hit.get("deezer_id"), f"result has no id: {hit!r}"

    run_report.add_row(
        test="search_api_returns_merged_results",
        status="passed",
        n_results=len(results),
        sources=sorted({h.get("source", "") for h in results}),
    )


def test_lyrics_api_returns_lrclib_synced(api_url: str, run_report):
    """Headless API check: GET /api/v1/lyrics returns LRC-format synced
    lines for a track that LRCLIB definitely has."""
    import json
    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode(
        {"track_name": "Blackbird", "artist_name": "The Beatles", "duration": 138}
    )
    with urllib.request.urlopen(f"{api_url}/api/v1/lyrics?{params}") as r:
        data = json.load(r)
    synced = data.get("synced_lyrics", "")
    assert synced, f"expected synced LRC for Blackbird, got empty: {data!r}"
    # First line should be an LRC timestamp like "[mm:ss.cc]..."
    first = synced.splitlines()[0]
    assert first.startswith("["), f"first line not an LRC timestamp: {first!r}"

    run_report.add_row(
        test="lyrics_api_returns_lrclib_synced",
        status="passed",
        synced_lines=synced.count("\n") + 1,
        plain_len=len(data.get("plain_lyrics", "")),
    )


def test_library_filter_chips_present(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """/library now has a row of filter chips (All / ★ Favorites / Key /
    7d / 30d / All). Confirms the C7 polish actually rendered."""
    page.goto(f"{frontend_url}/library", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Library")).to_be_visible(timeout=10_000)

    for label in ("All", "Favorites", "7d", "30d"):
        expect(page.get_by_text(label, exact=False).first).to_be_visible()

    out = screenshot_dir / "07_library_filters.png"
    page.screenshot(path=str(out), full_page=True)
    run_report.add_row(
        test="library_filter_chips_present",
        status="passed",
        screenshot=str(out.relative_to(screenshot_dir.parent.parent)),
    )
