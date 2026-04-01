"""JWT gate when AGENTIVA_AUTH_SECRET is set (matches dashboard AUTH_SECRET)."""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from agentiva.api import server


@pytest.fixture
def client_with_jwt(monkeypatch):
    secret = "test-jwt-secret-for-ci-only"
    monkeypatch.setenv("AGENTIVA_AUTH_SECRET", secret)
    # Reload middleware behavior: server module already imported; env read at request time via auth_secret()
    with TestClient(server.app) as c:
        yield c, secret


def test_api_open_when_jwt_secret_not_set(monkeypatch):
    monkeypatch.delenv("AGENTIVA_AUTH_SECRET", raising=False)
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    monkeypatch.delenv("NEXTAUTH_SECRET", raising=False)
    with TestClient(server.app) as client:
        r = client.post("/api/v1/intercept", json={"tool_name": "send_email", "arguments": {}, "agent_id": "a"})
        assert r.status_code == 200


def test_api_requires_bearer_when_jwt_secret_set(client_with_jwt):
    client, _secret = client_with_jwt
    r = client.post("/api/v1/intercept", json={"tool_name": "send_email", "arguments": {}, "agent_id": "a"})
    assert r.status_code == 401


def test_api_accepts_valid_jwt(client_with_jwt):
    client, secret = client_with_jwt
    token = jwt.encode(
        {"sub": "user-1", "email": "u@example.com", "name": "U"},
        secret,
        algorithm="HS256",
    )
    r = client.post(
        "/api/v1/intercept",
        json={"tool_name": "send_email", "arguments": {}, "agent_id": "a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
