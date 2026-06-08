"""ChatRequest contract (Group D.2).

ChatRequest now carries analysis_job_id / session_id / tutor_mode and NO
longer carries a client-supplied user_id (identity comes from the JWT) nor a
trusted history (reconstructed server-side from Mongo). These assertions lock
the field set so a future edit can't quietly re-introduce client-trust.
"""

from __future__ import annotations

import pytest

from backend.schemas import ChatRequest, ChatResponse


def test_chatrequest_has_phase2_fields():
    req = ChatRequest(
        message="why is the chorus sad?",
        analysis_job_id="job-1",
        session_id="sess-1",
        tutor_mode=True,
    )
    assert req.analysis_job_id == "job-1"
    assert req.session_id == "sess-1"
    assert req.tutor_mode is True


def test_tutor_mode_defaults_false():
    assert ChatRequest(message="hi").tutor_mode is False


def test_optional_ids_default_none():
    req = ChatRequest(message="hi")
    assert req.analysis_job_id is None
    assert req.session_id is None


def test_chatrequest_drops_client_user_id():
    fields = set(ChatRequest.model_fields)
    assert "user_id" not in fields, "client must not be able to assert identity"


def test_chatrequest_drops_client_history():
    fields = set(ChatRequest.model_fields)
    assert "history" not in fields, "history is reconstructed server-side"


def test_chatresponse_shape():
    resp = ChatResponse(reply="hello", session_id="sess-1")
    assert resp.reply == "hello"
    assert resp.session_id == "sess-1"
