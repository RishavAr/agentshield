from __future__ import annotations

from typing import Any, Dict, List

import httpx


class AlertManager:
    """Send alerts when dangerous things happen."""

    def __init__(self, websocket_broadcaster=None, slack_webhook_url: str = "", email_target: str = "", webhook_url: str = ""):
        self.websocket_broadcaster = websocket_broadcaster
        self.slack_webhook_url = slack_webhook_url
        self.email_target = email_target
        self.webhook_url = webhook_url
        self.sent_alerts: List[Dict[str, Any]] = []

    async def send_alert(self, alert_type, action, channel="all"):
        payload = {
            "alert_type": alert_type,
            "action_id": action.id,
            "tool_name": action.tool_name,
            "decision": action.decision,
            "risk_score": action.risk_score,
            "agent_id": action.agent_id,
        }
        self.sent_alerts.append(payload)

        if channel in {"all", "websocket"} and self.websocket_broadcaster is not None:
            await self.websocket_broadcaster(payload)

        async with httpx.AsyncClient(timeout=5.0) as client:
            if channel in {"all", "slack"} and self.slack_webhook_url:
                await client.post(self.slack_webhook_url, json={"text": str(payload)})
            if channel in {"all", "webhook"} and self.webhook_url:
                await client.post(self.webhook_url, json=payload)
            if channel in {"all", "email"} and self.email_target:
                # Placeholder email integration hook.
                pass
