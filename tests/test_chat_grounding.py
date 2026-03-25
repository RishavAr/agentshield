"""Shield chat / co-pilot grounding: audit numbers, compliance citations, sessions."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from agentiva import Agentiva
from agentiva.api import server
from agentiva.api.chat import ShieldChat
from agentiva.compliance.audit_grounding import (
    fetch_audit_grounding,
    format_grounding_for_llm,
    grounding_covers_numbers,
)
from agentiva.compliance.knowledge_base import get_compliance_context
from agentiva.interceptor.core import InterceptedAction


def _reset_runtime_state() -> None:
    if server._shield is not None:
        server._shield.audit_log.clear()
        server._shield.mode = "shadow"
    server._request_counts_by_agent.clear()


def _client() -> TestClient:
    return TestClient(server.app)


def test_copilot_response_includes_real_numbers() -> None:
    shield = Agentiva(mode="shadow")
    shield.audit_log.extend(
        [
            InterceptedAction(
                id="a1",
                timestamp="2026-01-01T12:00:00+00:00",
                tool_name="send_email",
                arguments={"to": "x@y.com"},
                agent_id="ag1",
                risk_score=0.55,
                decision="shadow",
                mode="shadow",
            ),
            InterceptedAction(
                id="a2",
                timestamp="2026-01-01T12:01:00+00:00",
                tool_name="send_email",
                arguments={"to": "z@y.com"},
                agent_id="ag1",
                risk_score=0.60,
                decision="shadow",
                mode="shadow",
            ),
        ]
    )
    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("give me a summary"))
    assert "2" in resp.answer or "two" in resp.answer.lower()
    assert "Session actions" in resp.answer or "session" in resp.answer.lower()


def test_copilot_refuses_to_speculate() -> None:
    shield = Agentiva(mode="shadow")
    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("predict the stock market price next year in detail"))
    assert resp.answer
    lowered = resp.answer.lower()
    assert "rephrasing" in lowered or "summary" in lowered or "blocked" in lowered or "audit" in lowered


def test_copilot_cites_compliance_sections() -> None:
    text = get_compliance_context("HIPAA audit controls 164.312")
    assert "45 CFR" in text or "164.312" in text


def test_copilot_contextual_suggestions() -> None:
    shield = Agentiva(mode="shadow")
    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("show me risky actions"))
    assert resp.follow_up_suggestions
    assert len(resp.follow_up_suggestions) >= 1


def test_chat_session_creation() -> None:
    with _client() as client:
        _reset_runtime_state()
        r = client.post("/api/v1/chat/sessions", json={"tenant_id": "default", "title": "Unit test"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("id")
        assert body.get("title")


def test_chat_history_persistence() -> None:
    with _client() as client:
        _reset_runtime_state()
        cr = client.post("/api/v1/chat/sessions", json={"tenant_id": "t1", "title": "persist"})
        assert cr.status_code == 200
        session_id = cr.json()["id"]
        pr = client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"message": "give me a summary"},
        )
        assert pr.status_code == 200
        gr = client.get(f"/api/v1/chat/sessions/{session_id}")
        assert gr.status_code == 200
        detail = gr.json()
        assert detail.get("messages")
        roles = [m.get("role") for m in detail["messages"]]
        assert "user" in roles


def test_chat_session_deletion() -> None:
    with _client() as client:
        _reset_runtime_state()
        cr = client.post("/api/v1/chat/sessions", json={"tenant_id": "t2", "title": "del"})
        session_id = cr.json()["id"]
        dr = client.delete(f"/api/v1/chat/sessions/{session_id}")
        assert dr.status_code == 200
        gr = client.get(f"/api/v1/chat/sessions/{session_id}")
        assert gr.status_code == 404


def test_grounding_format_and_number_check() -> None:
    g = asyncio.run(fetch_audit_grounding("HIPAA PHI audit"))
    blob = format_grounding_for_llm(g)
    assert "action_logs" in blob.lower() or "AUDIT" in blob
    # No numeric claims → passes; co-pilot adds answer into the check set when validating LLM output.
    assert grounding_covers_numbers("Summary with no digits", blob) is True
    assert grounding_covers_numbers("Total 0 actions in the database snapshot", blob) is True
