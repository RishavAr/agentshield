from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from agentiva.interceptor.core import InterceptedAction


class BrowserAgentInterceptor:
    """Intercept actions from browser agents (OpenClaw, Browser Use, Playwright agents)."""

    def _action(self, tool_name: str, arguments: Dict[str, Any], risk: float) -> InterceptedAction:
        decision = "block" if risk >= 0.8 else "shadow"
        return InterceptedAction(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=tool_name,
            arguments=arguments,
            agent_id="browser-agent",
            risk_score=risk,
            decision=decision,
            mode="shadow",
            result={"status": decision},
            rollback_plan=None,
        )

    def intercept_navigation(self, url: str) -> InterceptedAction:
        risk = 0.1
        if "darkweb" in url or "suspicious" in url or "unknown" in url:
            risk = 0.5
        return self._action("browser_navigation", {"url": url}, risk)

    def intercept_form_submission(self, form_data: Dict[str, Any]) -> InterceptedAction:
        content = str(form_data).lower()
        risk = 0.2
        if any(k in content for k in ["credit_card", "cvv", "payment"]):
            risk = 0.8
        if any(k in content for k in ["password", "token", "secret"]):
            risk = max(risk, 0.7)
        return self._action("browser_form_submit", {"form_data": form_data}, risk)

    def intercept_download(self, url: str, filename: str) -> InterceptedAction:
        risk = 0.2
        if filename.lower().endswith((".exe", ".msi", ".dmg", ".pkg", ".sh")):
            risk = 0.9
        return self._action("browser_download", {"url": url, "filename": filename}, risk)
