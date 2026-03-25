import asyncio

from agentiva.alerts.alerter import AlertManager
from agentiva.interceptor.core import InterceptedAction


def _action() -> InterceptedAction:
    return InterceptedAction(
        id="a1",
        timestamp="2026-01-01T00:00:00+00:00",
        tool_name="send_email",
        arguments={"to": "x@outside.com"},
        agent_id="agent-1",
        risk_score=0.95,
        decision="block",
        mode="shadow",
    )


def test_alert_manager_records_alert() -> None:
    manager = AlertManager()
    asyncio.run(manager.send_alert("blocked", _action()))
    assert len(manager.sent_alerts) == 1


def test_alert_manager_websocket_channel() -> None:
    events = []

    async def ws(payload):
        events.append(payload)

    manager = AlertManager(websocket_broadcaster=ws)
    asyncio.run(manager.send_alert("blocked", _action(), channel="websocket"))
    assert len(events) == 1


def test_alert_manager_slack_webhook(monkeypatch) -> None:
    calls = []

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            calls.append((url, json))

    monkeypatch.setattr("agentiva.alerts.alerter.httpx.AsyncClient", DummyClient)
    manager = AlertManager(slack_webhook_url="https://slack.example")
    asyncio.run(manager.send_alert("blocked", _action(), channel="slack"))
    assert calls


def test_alert_manager_generic_webhook(monkeypatch) -> None:
    calls = []

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            calls.append((url, json))

    monkeypatch.setattr("agentiva.alerts.alerter.httpx.AsyncClient", DummyClient)
    manager = AlertManager(webhook_url="https://hook.example")
    asyncio.run(manager.send_alert("blocked", _action(), channel="webhook"))
    assert calls[0][0] == "https://hook.example"
