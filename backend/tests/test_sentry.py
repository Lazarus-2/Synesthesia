"""Tests for the opt-in Sentry error-tracking integration.

Hermetic — never makes a real network call. The DSN-set case stubs out
``sentry_sdk.init`` so nothing ships off-box.
"""

from __future__ import annotations

import sys

from backend.config import get_settings
from backend.observability.sentry import init_sentry


def test_init_sentry_noop_when_dsn_unset(monkeypatch):
    """Default settings have no DSN: init_sentry returns False and does not
    import/call sentry_sdk.init."""
    # Ensure a clean, DSN-less settings instance.
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    get_settings.cache_clear()

    called = {"init": False}

    # If sentry_sdk happens to be importable, prove its init is never touched.
    if "sentry_sdk" in sys.modules:
        monkeypatch.setattr(
            sys.modules["sentry_sdk"], "init", lambda *a, **k: called.__setitem__("init", True)
        )

    try:
        assert init_sentry() is False
        assert called["init"] is False
    finally:
        get_settings.cache_clear()


def test_init_sentry_initializes_when_dsn_set(monkeypatch):
    """With a DSN configured, init_sentry returns True and calls
    sentry_sdk.init exactly once with that DSN. Stubbed — no network."""
    import sentry_sdk

    monkeypatch.setenv("SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    get_settings.cache_clear()

    calls: list[dict] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda *a, **k: calls.append(k))

    try:
        assert init_sentry() is True
        assert len(calls) == 1
        assert calls[0]["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
    finally:
        get_settings.cache_clear()
