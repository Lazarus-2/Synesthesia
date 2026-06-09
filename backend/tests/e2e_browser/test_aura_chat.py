"""Live-browser E2E for the AURA chat panel (Phase 2, Group F).

Drives real Chromium against the running Next.js + FastAPI stack. We do NOT
exercise a live LLM here — we intercept the ``/chat/stream`` request so the
test asserts the *frontend contract* (request shape, headers, SSE-frame
handling) deterministically, then fulfil it with a scripted SSE body.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, expect

# A scripted SSE body matching the Phase-2 tagged protocol: context → tool
# (start) → chunk × N → tool (end) → done. Mirrors stream_aura's frames.
_SCRIPTED_SSE = (
    "event: context\n"
    'data: {"title": "Blackbird", "artist": "The Beatles", "key": "G major", "bpm": 92, "status": "ok"}\n\n'
    "event: tool\n"
    'data: {"phase": "start", "name": "get_chord_voicing"}\n\n'
    "event: chunk\n"
    'data: {"text": "The G chord "}\n\n'
    "event: chunk\n"
    'data: {"text": "anchors the verse."}\n\n'
    "event: tool\n"
    'data: {"phase": "end", "name": "get_chord_voicing"}\n\n'
    "event: done\n"
    'data: {"session_id": "sess-e2e-123"}\n\n'
)


def _seed_loaded_analysis(page: Page, frontend_url: str) -> None:
    """Open a sample share-derived player so the chat tab has an analysis."""
    page.goto(f"{frontend_url}/s/sample-blackbird", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Blackbird")).to_be_visible(timeout=10_000)


def test_chat_sendmessage_request_shape(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """sendMessage POSTs {message, analysis_job_id, session_id, tutor_mode}
    with an Authorization: Bearer header, and stores the returned session_id."""
    captured: dict = {}

    def _handle(route):
        req = route.request
        captured["headers"] = req.headers
        captured["body"] = req.post_data_json
        route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream"},
            body=_SCRIPTED_SSE,
        )

    # Seed an auth token + a KNOWN job id into localStorage so the analysis
    # store hydrates with a predictable value.  The store reads jobId from
    # localStorage on startup via the route (sample-blackbird sets it), but we
    # also inject a sentinel directly so we can assert the request body carries
    # THAT exact value rather than merely checking that the key is present.
    KNOWN_JOB_ID = "job-e2e-blackbird-001"
    page.add_init_script(
        "window.localStorage.setItem('synesthesia.auth.token', JSON.stringify('jwt-e2e-token'));"
        "window.localStorage.setItem('synesthesia.auth.user', JSON.stringify({user_id:'u1',username:'tester'}));"
        # Pre-seed a known jobId so the analysis store picks it up on hydration.
        f"window.localStorage.setItem('synesthesia.analysis.jobId', JSON.stringify('{KNOWN_JOB_ID}'));"
    )
    _seed_loaded_analysis(page, frontend_url)

    page.route("**/api/v1/chat/stream", _handle)

    # Navigate to the player (chat tab lives there) and switch to CHAT.
    page.goto(frontend_url, wait_until="domcontentloaded")
    # The sample route stores jobId; open the player by clicking the sample card.
    page.goto(f"{frontend_url}/s/sample-blackbird", wait_until="domcontentloaded")
    page.get_by_role("button", name="CHAT").click()

    page.get_by_placeholder("Ask about chords, theory, techniques...").fill("Why G?")
    page.get_by_role("button", name="send").click()

    page.wait_for_function("() => window.localStorage.getItem('synesthesia.auth.token') !== null")
    page.wait_for_timeout(1500)  # let the SSE flush

    assert captured, "chat/stream was never called"
    body = captured["body"]
    assert body["message"] == "Why G?"
    # Assert the KNOWN job id was forwarded — not just that the key exists.
    # (If the store didn't hydrate from localStorage the value would be null,
    # which would silently pass an "in body" check but break server grounding.)
    assert body.get("analysis_job_id") == KNOWN_JOB_ID, (
        f"expected analysis_job_id={KNOWN_JOB_ID!r}, got {body.get('analysis_job_id')!r}"
    )
    assert "session_id" in body
    assert body["tutor_mode"] is False
    assert "history" not in body, "client must STOP sending history (server-owned now)"
    auth = captured["headers"].get("authorization", "")
    assert auth == "Bearer jwt-e2e-token", f"missing/incorrect bearer header: {auth!r}"

    # The store must persist the server-returned session_id for the next turn.
    sess = page.evaluate(
        "() => JSON.parse(window.localStorage.getItem('synesthesia.chat.session') || 'null')"
    )
    assert sess == "sess-e2e-123", f"session_id not persisted: {sess!r}"

    shot = screenshot_dir / "F1_chat_request_shape.png"
    page.screenshot(path=str(shot), full_page=True)
    run_report.add_row(
        test="chat_sendmessage_request_shape",
        status="passed",
        bearer=True,
        session_persisted="sess-e2e-123",
    )


def test_chat_context_and_tool_frames_render(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """The 'context' frame drives the Discussing chip; the 'tool' frame drives
    a transient status pill; both require consumeSse to route the new events."""
    def _handle(route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream"},
            body=_SCRIPTED_SSE,
        )

    page.add_init_script(
        "window.localStorage.setItem('synesthesia.auth.token', JSON.stringify('jwt-e2e-token'));"
        "window.localStorage.setItem('synesthesia.auth.user', JSON.stringify({user_id:'u1',username:'tester'}));"
    )
    page.route("**/api/v1/chat/stream", _handle)

    _seed_loaded_analysis(page, frontend_url)
    page.get_by_role("button", name="CHAT").click()
    page.get_by_placeholder("Ask about chords, theory, techniques...").fill("Why G?")
    page.get_by_role("button", name="send").click()

    # Tool pill is transient — assert it appears during the stream.
    expect(page.get_by_text("get_chord_voicing", exact=False)).to_be_visible(timeout=5_000)
    # Streamed reply text lands.
    expect(page.get_by_text("anchors the verse.", exact=False)).to_be_visible(timeout=5_000)

    shot = screenshot_dir / "F2_context_tool_frames.png"
    page.screenshot(path=str(shot), full_page=True)
    run_report.add_row(test="chat_context_and_tool_frames_render", status="passed")


def test_chat_discussing_chip_and_tutor_toggle(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """A loaded song shows a 'Discussing: …' chip; the Tutor toggle flips
    tutor_mode in the outgoing request."""
    captured: dict = {}

    def _handle(route):
        captured["body"] = route.request.post_data_json
        route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream"},
            body=_SCRIPTED_SSE,
        )

    page.add_init_script(
        "window.localStorage.setItem('synesthesia.auth.token', JSON.stringify('jwt-e2e-token'));"
        "window.localStorage.setItem('synesthesia.auth.user', JSON.stringify({user_id:'u1',username:'tester'}));"
    )
    page.route("**/api/v1/chat/stream", _handle)

    _seed_loaded_analysis(page, frontend_url)
    page.get_by_role("button", name="CHAT").click()

    # Discussing chip is built from the loaded analysis (title/key/bpm).
    expect(page.get_by_text("Discussing:", exact=False)).to_be_visible(timeout=5_000)
    expect(page.get_by_text("Blackbird", exact=False)).to_be_visible()

    # Flip Tutor mode on, then send.
    page.get_by_role("switch", name="Tutor mode").click()
    page.get_by_placeholder("Ask about chords, theory, techniques...").fill("Teach me G")
    page.get_by_role("button", name="send").click()
    page.wait_for_timeout(1200)
    assert captured["body"]["tutor_mode"] is True, "tutor toggle did not propagate"

    shot = screenshot_dir / "F3_discussing_tutor.png"
    page.screenshot(path=str(shot), full_page=True)
    run_report.add_row(test="chat_discussing_chip_and_tutor_toggle", status="passed")


def test_chat_login_gate_when_unauthenticated(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """With no token, the chat tab shows a sign-in nudge and no input box."""
    # No token init-script → unauthenticated.
    _seed_loaded_analysis(page, frontend_url)
    page.get_by_role("button", name="CHAT").click()

    expect(page.get_by_text("Sign in to chat", exact=False)).to_be_visible(timeout=5_000)
    # Input must be gated away.
    expect(page.get_by_placeholder("Ask about chords, theory, techniques...")).to_have_count(0)
    # The nudge links to /login.
    expect(page.locator('a[href="/login"]')).to_be_visible()

    shot = screenshot_dir / "F3_login_gate.png"
    page.screenshot(path=str(shot), full_page=True)
    run_report.add_row(test="chat_login_gate_when_unauthenticated", status="passed")


def test_authed_reload_keeps_chat_unlocked(
    page: Page,
    frontend_url: str,
    screenshot_dir: Path,
    run_report,
):
    """After a hard reload, a stored JWT must rehydrate the auth store so the
    chat tab stays unlocked (no 'Sign in to chat' flash that persists)."""
    page.add_init_script(
        "window.localStorage.setItem('synesthesia.auth.token', JSON.stringify('jwt-e2e-token'));"
        "window.localStorage.setItem('synesthesia.auth.user', JSON.stringify({user_id:'u1',username:'tester'}));"
    )
    _seed_loaded_analysis(page, frontend_url)
    page.reload(wait_until="domcontentloaded")
    page.get_by_role("button", name="CHAT").click()

    # Gate must NOT show — input box present instead.
    expect(page.get_by_placeholder("Ask about chords, theory, techniques...")).to_be_visible(
        timeout=5_000
    )
    expect(page.get_by_text("Sign in to chat", exact=False)).to_have_count(0)

    shot = screenshot_dir / "F4_authed_reload.png"
    page.screenshot(path=str(shot), full_page=True)
    run_report.add_row(test="authed_reload_keeps_chat_unlocked", status="passed")
