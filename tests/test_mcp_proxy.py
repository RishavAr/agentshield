from fastapi.testclient import TestClient

from agentiva import Agentiva
from agentiva.interceptor.mcp_proxy import create_mcp_proxy_app


def test_mcp_proxy_blocks_when_policy_blocks() -> None:
    shield = Agentiva(mode="shadow", policy_path="policies/default.yaml")
    app = create_mcp_proxy_app("localhost:3001", shield)
    with TestClient(app) as client:
        response = client.post(
            "/mcp/call",
            json={"tool_name": "send_email", "arguments": {"to": "evil@outside.com"}},
        )
        assert response.status_code == 200
        assert response.json()["blocked"] is True


def test_mcp_proxy_forwards_on_non_block(monkeypatch) -> None:
    shield = Agentiva(mode="live")
    app = create_mcp_proxy_app("localhost:3001", shield)

    class DummyResp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return DummyResp()

    monkeypatch.setattr("agentiva.interceptor.mcp_proxy.httpx.AsyncClient", DummyClient)

    with TestClient(app) as client:
        response = client.post("/mcp/call", json={"tool_name": "safe_tool", "arguments": {}})
        assert response.status_code == 200
        assert response.json()["blocked"] is False


def test_mcp_proxy_validation() -> None:
    shield = Agentiva(mode="shadow")
    app = create_mcp_proxy_app("localhost:3001", shield)
    with TestClient(app) as client:
        response = client.post("/mcp/call", json={"arguments": {}})
        assert response.status_code == 422


def test_mcp_proxy_includes_negotiation_on_block() -> None:
    shield = Agentiva(mode="shadow", policy_path="policies/default.yaml")
    app = create_mcp_proxy_app("localhost:3001", shield)
    with TestClient(app) as client:
        response = client.post("/mcp/call", json={"tool_name": "send_email", "arguments": {"to": "x@outside.com"}})
        payload = response.json()
        assert payload["blocked"] is True
        assert payload["negotiation"] is not None
