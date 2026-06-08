"""Chat rate-limit key derivation (Group D.4 — C1 fix).

_chat_rate_limit_key now decodes the JWT directly from the Authorization
header so it does NOT depend on request.state being populated by the
endpoint body (which runs after slowapi evaluates the key_func).

Tests:
- Same Bearer token, different client IPs → same "user:" key (C1).
- No token → falls back to IP (anonymous path).
- Malformed / expired token → falls back to IP gracefully.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from backend.auth import issue_token


@pytest.fixture(autouse=True)
def _auth_env():
    prior = os.environ.get("AUTH_SECRET_KEY")
    os.environ["AUTH_SECRET_KEY"] = "test-secret-please-do-not-use-in-prod"
    from backend.config import get_settings

    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("AUTH_SECRET_KEY", None)
        else:
            os.environ["AUTH_SECRET_KEY"] = prior
        get_settings.cache_clear()


def _make_request(token: str | None, client_ip: str = "203.0.113.7"):
    """Build a minimal Request-like mock with just the fields _chat_rate_limit_key needs."""
    req = MagicMock()
    req.headers = {"authorization": f"Bearer {token}"} if token else {}
    req.client = MagicMock(host=client_ip)
    return req


# C1: two requests with the same JWT but different client IPs share one key
def test_same_token_different_ips_share_key():
    from backend.main import _chat_rate_limit_key

    token = issue_token(user_id="user-42", username="alice")
    key_a = _chat_rate_limit_key(_make_request(token, client_ip="1.2.3.4"))
    key_b = _chat_rate_limit_key(_make_request(token, client_ip="5.6.7.8"))
    assert key_a == key_b == "user:user-42"


# C1: the key is "user:<id>" not an IP
def test_key_uses_user_id_from_token():
    from backend.main import _chat_rate_limit_key

    token = issue_token(user_id="user-99")
    key = _chat_rate_limit_key(_make_request(token, client_ip="10.0.0.1"))
    assert key == "user:user-99"


# Anonymous caller → IP fallback
def test_key_falls_back_to_ip_when_no_token():
    from backend.main import _chat_rate_limit_key

    key = _chat_rate_limit_key(_make_request(None, client_ip="203.0.113.7"))
    assert key == "203.0.113.7"


# Malformed token → silent IP fallback (no exception bubbles up)
def test_key_falls_back_to_ip_on_bad_token():
    from backend.main import _chat_rate_limit_key

    key = _chat_rate_limit_key(_make_request("not-a-valid-jwt", client_ip="203.0.113.7"))
    assert key == "203.0.113.7"
