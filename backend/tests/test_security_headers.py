"""Security-headers middleware tests.

Asserts the baseline hardening headers ride on every response and that the
opt-in Content-Security-Policy header stays off by default but appears when the
``content_security_policy`` setting (env: ``CONTENT_SECURITY_POLICY``) is set.

``get_settings`` is ``@lru_cache``-d, so the CSP-on test sets the env var, clears
the cache, exercises the request, then restores the env + clears the cache again
in a ``finally`` to keep the suite hermetic.
"""

from __future__ import annotations

import os

from backend.config import get_settings

_BASELINE = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def test_baseline_security_headers_present(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    for name, value in _BASELINE.items():
        assert resp.headers.get(name) == value


def test_csp_absent_by_default(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp.headers


def test_csp_present_when_configured(api_client):
    policy = "default-src 'self'"
    prior = os.environ.get("CONTENT_SECURITY_POLICY")
    os.environ["CONTENT_SECURITY_POLICY"] = policy
    get_settings.cache_clear()
    try:
        resp = api_client.get("/health")
        assert resp.status_code == 200
        assert resp.headers.get("Content-Security-Policy") == policy
        # Baseline headers still ride alongside the CSP.
        for name, value in _BASELINE.items():
            assert resp.headers.get(name) == value
    finally:
        if prior is None:
            os.environ.pop("CONTENT_SECURITY_POLICY", None)
        else:
            os.environ["CONTENT_SECURITY_POLICY"] = prior
        get_settings.cache_clear()
