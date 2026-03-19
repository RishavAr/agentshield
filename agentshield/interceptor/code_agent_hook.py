from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from agentshield.interceptor.core import InterceptedAction


class CodeAgentInterceptor:
    """Intercept actions from coding agents (Devin, Claude Code, Cursor Agent, Copilot)."""

    def _make_action(self, tool_name: str, arguments: Dict[str, Any], risk: float) -> InterceptedAction:
        decision = "block" if risk >= 0.7 else "shadow"
        return InterceptedAction(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=tool_name,
            arguments=arguments,
            agent_id="code-agent",
            risk_score=risk,
            decision=decision,
            mode="shadow",
            result={"status": decision, "message": f"Code action {tool_name} intercepted"},
            rollback_plan=None,
        )

    def intercept_shell_command(self, command: str) -> InterceptedAction:
        cmd = command.lower()
        risk = 0.1
        if "rm -rf /" in cmd:
            risk = 1.0
        elif "sudo " in cmd:
            risk = 0.8
        elif "curl" in cmd and "bash" in cmd:
            risk = 0.9
        elif "git push --force" in cmd:
            risk = 0.7
        return self._make_action("shell_command", {"command": command}, risk)

    def intercept_file_write(self, path: str, content: str) -> InterceptedAction:
        path_lower = path.lower()
        risk = 0.1
        if path_lower.endswith(".env"):
            risk = 0.6
        if path_lower.startswith("/etc") or "/system" in path_lower:
            risk = 0.9
        return self._make_action("file_write", {"path": path, "content_preview": content[:200]}, risk)

    def intercept_git_operation(self, operation: str, args: dict) -> InterceptedAction:
        op = operation.lower()
        risk = 0.2
        if op == "push" and args.get("force"):
            risk = 0.7
        elif op == "push" and args.get("branch") in {"main", "master"}:
            risk = 0.6
        elif op == "delete_branch":
            risk = 0.5
        return self._make_action("git_operation", {"operation": operation, "args": args}, risk)
