from __future__ import annotations

import secrets
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


def _generate_api_key() -> str:
    return f"agv_live_{secrets.token_hex(16)}"


@dataclass
class Agent:
    id: str
    name: str
    owner: str
    allowed_tools: list
    max_risk_tolerance: float
    reputation_score: float
    total_actions: int
    blocked_actions: int
    created_at: str
    status: str
    role: str | None = None
    last_active: str | None = None
    description: str = ""
    framework: str = "custom"

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


class AgentRegistry:
    """Track all agents, their permissions, reputation scores, and lifecycle."""

    def __init__(self):
        self._agents: Dict[str, Agent] = {}

    def register_agent(
        self,
        agent_id,
        name,
        owner,
        allowed_tools,
        max_risk_tolerance,
        role: str | None = None,
        description: str = "",
        framework: str = "custom",
    ) -> Agent:
        now = datetime.now(timezone.utc).isoformat()
        agent = Agent(
            id=agent_id,
            name=name,
            owner=owner,
            allowed_tools=list(allowed_tools),
            max_risk_tolerance=float(max_risk_tolerance),
            role=role,
            reputation_score=0.5,
            total_actions=0,
            blocked_actions=0,
            created_at=now,
            status="active",
            last_active=now,
            description=description or "",
            framework=framework or "custom",
        )
        self._agents[agent_id] = agent
        return agent

    def register_with_api_key(
        self,
        name: str,
        description: str,
        framework: str,
        allowed_tools: List[str],
        max_risk_tolerance: float,
        owner_email: str = "owner@localhost",
    ) -> Tuple[Agent, str]:
        """Create agent and return (agent, plaintext_api_key) — key is shown once."""
        agent_id = f"agent-{uuid.uuid4().hex[:12]}"
        api_key = _generate_api_key()
        agent = self.register_agent(
            agent_id,
            name,
            owner_email,
            allowed_tools,
            max_risk_tolerance,
            role=None,
            description=description,
            framework=framework,
        )
        return agent, api_key

    def get_agent(self, agent_id) -> Agent:
        if agent_id not in self._agents:
            raise KeyError(f"Agent not found: {agent_id}")
        return self._agents[agent_id]

    def update_reputation(self, agent_id, action_outcome):
        agent = self.get_agent(agent_id)
        agent.last_active = datetime.now(timezone.utc).isoformat()
        agent.total_actions += 1
        if action_outcome == "block":
            agent.blocked_actions += 1
            agent.reputation_score = max(0.0, round(agent.reputation_score - 0.05, 4))
        else:
            agent.reputation_score = min(1.0, round(agent.reputation_score + 0.01, 4))
        if agent.reputation_score < 0.2:
            agent.status = "suspended"

    def list_agents(self) -> List[dict]:
        return [agent.to_dict() for agent in self._agents.values()]

    def deactivate_agent(self, agent_id):
        agent = self.get_agent(agent_id)
        agent.status = "deactivated"

    def update_agent(
        self,
        agent_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> Agent:
        agent = self.get_agent(agent_id)
        if name is not None and name.strip():
            agent.name = name.strip()
        if description is not None:
            agent.description = description.strip()
        if allowed_tools is not None:
            agent.allowed_tools = list(allowed_tools)
        agent.last_active = datetime.now(timezone.utc).isoformat()
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        return True
