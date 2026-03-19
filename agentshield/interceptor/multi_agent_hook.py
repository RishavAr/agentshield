from __future__ import annotations

import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, Deque, List

from agentshield.interceptor.core import InterceptedAction


class MultiAgentInterceptor:
    """Intercept agent-to-agent communication in CrewAI, AutoGen, MetaGPT systems."""

    def __init__(self) -> None:
        self._chains: Dict[str, Deque[str]] = defaultdict(lambda: deque(maxlen=25))

    def _action(self, tool_name: str, args: Dict[str, Any], risk: float) -> InterceptedAction:
        decision = "block" if risk >= 0.8 else "shadow"
        return InterceptedAction(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=tool_name,
            arguments=args,
            agent_id=args.get("from_agent", "multi-agent"),
            risk_score=risk,
            decision=decision,
            mode="shadow",
            result={"status": decision},
            rollback_plan=None,
        )

    def intercept_delegation(self, from_agent, to_agent, task) -> InterceptedAction:
        risk = 0.2
        if "admin" in str(task).lower() and "admin" not in str(from_agent).lower():
            risk = 0.8
        return self._action(
            "agent_delegation",
            {"from_agent": from_agent, "to_agent": to_agent, "task": task},
            risk,
        )

    def intercept_data_transfer(self, from_agent, to_agent, data) -> InterceptedAction:
        risk = 0.2
        blob = str(data).lower()
        if any(x in blob for x in ["ssn", "token", "password", "credit_card"]):
            risk = 0.9
        return self._action(
            "agent_data_transfer",
            {"from_agent": from_agent, "to_agent": to_agent, "data": data},
            risk,
        )

    def detect_cascade(self, agent_id, action_chain) -> bool:
        chain_len = len(action_chain)
        if chain_len > 10:
            return True
        self._chains[agent_id].append(str(chain_len))
        return False
