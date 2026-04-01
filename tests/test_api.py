import asyncio

from fastapi.testclient import TestClient

from agentiva.api import server
from agentiva.auth.tenancy import TenantManager
from agentiva.db.database import truncate_action_logs


def _new_client() -> TestClient:
    return TestClient(server.app)


def _reset_runtime_state() -> None:
    if server._shield is not None:
        server._shield.audit_log.clear()
        server._shield.mode = "shadow"
        server._shield.risk_threshold = 0.7
    server._request_counts_by_agent.clear()
    asyncio.run(truncate_action_logs())


def test_health_endpoint() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["version"] == "0.1.0"
        assert "uptime_seconds" in body
        assert body["mode"] in {"shadow", "live", "approval"}
        assert isinstance(body.get("risk_threshold"), (int, float))


def test_chat_endpoint() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "send_email",
                "arguments": {"to": "x@evil.com", "subject": "t"},
                "agent_id": "a1",
            },
        )
        response = client.post("/api/v1/chat", json={"message": "give me a summary"})
        assert response.status_code == 200
        body = response.json()
        assert "answer" in body
        assert "suggestions" in body
        assert isinstance(body["suggestions"], list)
        assert "hint" not in body
        assert "data" not in body
        assert "mode" not in body


def test_chat_capabilities_endpoint() -> None:
    with _new_client() as client:
        response = client.get("/api/v1/chat/capabilities")
        assert response.status_code == 200
        body = response.json()
        assert "llm_enabled" in body
        assert body["llm_enabled"] in (True, False)
        assert "provider" in body


def test_intercept_valid_input() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        payload = {
            "tool_name": "send_email",
            "arguments": {"to": "dev@yourcompany.com", "subject": "Hi"},
            "agent_id": "agent-a",
        }
        response = client.post("/api/v1/intercept", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["tool_name"] == "send_email"
        assert body["agent_id"] == "agent-a"
        assert body["decision"] in {"shadow", "block", "approve", "allow", "pending"}
        assert isinstance(body["risk_score"], float)


def test_intercept_invalid_input_empty_tool_name() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        payload = {"tool_name": "   ", "arguments": {}, "agent_id": "agent-a"}
        response = client.post("/api/v1/intercept", json=payload)
        assert response.status_code == 422


def test_audit_log_filters() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "send_email",
                "arguments": {"to": "outside@example.com"},
                "agent_id": "alpha",
            },
        )
        client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "create_ticket",
                "arguments": {"title": "Issue"},
                "agent_id": "beta",
            },
        )

        response = client.get("/api/v1/audit", params={"tool_name": "create_ticket"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["tool_name"] == "create_ticket"

        response = client.get("/api/v1/audit", params={"agent_id": "alpha"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["agent_id"] == "alpha"


def test_shadow_report_endpoint() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        client.post(
            "/api/v1/intercept",
            json={"tool_name": "send_email", "arguments": {"to": "a@yourcompany.com"}},
        )
        client.post(
            "/api/v1/intercept",
            json={"tool_name": "create_ticket", "arguments": {"title": "Bug"}},
        )
        response = client.get("/api/v1/report")
        assert response.status_code == 200
        body = response.json()
        assert body["total_actions"] == 2
        assert "by_tool" in body
        assert "by_decision" in body
        assert "avg_risk_score" in body


def test_mode_change_endpoint() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        response = client.post("/api/v1/mode/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "mode": "live"}


def test_invalid_mode_error() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        response = client.post("/api/v1/mode/not-real")
        assert response.status_code == 400
        assert "Mode must be" in response.json()["detail"]


def test_compliance_pdf_report_endpoint() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        r = client.get("/api/v1/compliance/soc2/report")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


def test_chat_sessions_and_messages() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        r = client.post("/api/v1/chat/sessions", json={"title": "t"})
        assert r.status_code == 200
        sid = r.json()["id"]
        m = client.post(
            f"/api/v1/chat/sessions/{sid}/messages",
            json={"message": "give me a summary"},
        )
        assert m.status_code == 200
        assert "answer" in m.json()
        detail = client.get(f"/api/v1/chat/sessions/{sid}")
        assert detail.status_code == 200
        assert len(detail.json()["messages"]) >= 2
        ex = client.get(f"/api/v1/chat/sessions/{sid}/export?format=markdown")
        assert ex.status_code == 200
        assert b"# Agentiva" in ex.content or b"assistant" in ex.content.lower()
        dl = client.delete(f"/api/v1/chat/sessions/{sid}")
        assert dl.status_code == 200


def test_chat_session_create_works_without_api_key_header_when_tenant_auth_enabled() -> None:
    original_manager = server._tenant_manager
    server._tenant_manager = TenantManager()
    server._tenant_manager.register_tenant("default", "Default", "test-key")
    try:
        with _new_client() as client:
            _reset_runtime_state()
            # Chat endpoints should remain available in deterministic mode without key headers.
            r = client.post("/api/v1/chat/sessions", json={"title": "No-key chat"})
            assert r.status_code == 200
            assert "id" in r.json()
    finally:
        server._tenant_manager = original_manager


def test_basic_chat_mode_phrases_and_db_grounded_responses(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with _new_client() as client:
        _reset_runtime_state()
        # Seed a blocked action for session overview + blocked queries.
        i = client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "send_email",
                "arguments": {"to": "x@evil.com", "subject": "customer data"},
                "agent_id": "seed-agent",
            },
        )
        assert i.status_code == 200

        s = client.post("/api/v1/chat/sessions", json={"title": "chat smoke"})
        assert s.status_code == 200
        sid = s.json()["id"]

        hi = client.post(f"/api/v1/chat/sessions/{sid}/messages", json={"message": "hi"})
        assert hi.status_code == 200
        assert "co-pilot" in hi.json()["answer"].lower()

        overview = client.post(
            f"/api/v1/chat/sessions/{sid}/messages",
            json={"message": "session overview"},
        )
        assert overview.status_code == 200
        ans = overview.json()["answer"]
        assert "blocked" in ans.lower() and ("shadow" in ans.lower() or "monitored" in ans.lower())

        blocked = client.post(
            f"/api/v1/chat/sessions/{sid}/messages",
            json={"message": "what was blocked?"},
        )
        assert blocked.status_code == 200
        assert "blocked" in blocked.json()["answer"].lower()


def test_chat_message_accepts_content_alias() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        s = client.post("/api/v1/chat/sessions", json={"title": "alias"})
        sid = s.json()["id"]
        m = client.post(
            f"/api/v1/chat/sessions/{sid}/messages",
            json={"content": "hi"},
        )
        assert m.status_code == 200
        assert "co-pilot" in m.json()["answer"].lower()

        hipaa = client.post(
            f"/api/v1/chat/sessions/{sid}/messages",
            json={"message": "HIPAA-aligned check"},
        )
        assert hipaa.status_code == 200
        # Compliance path should include citation-like references.
        lower = hipaa.json()["answer"].lower()
        assert ("45 cfr" in lower) or ("§" in hipaa.json()["answer"])
