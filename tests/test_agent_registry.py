import pytest

from agentiva.registry.agent_registry import AgentRegistry


def test_register_agent() -> None:
    registry = AgentRegistry()
    agent = registry.register_agent("a1", "Agent One", "alice", ["send_email"], 0.7)
    assert agent.id == "a1"
    assert agent.reputation_score == 0.5


def test_update_reputation() -> None:
    registry = AgentRegistry()
    registry.register_agent("a1", "Agent One", "alice", [], 0.7)
    registry.update_reputation("a1", "allow")
    registry.update_reputation("a1", "block")
    agent = registry.get_agent("a1")
    assert agent.total_actions == 2
    assert agent.blocked_actions == 1


def test_kill_switch_deactivates_agent() -> None:
    registry = AgentRegistry()
    registry.register_agent("a1", "Agent One", "alice", [], 0.7)
    registry.deactivate_agent("a1")
    assert registry.get_agent("a1").status == "deactivated"


def test_get_unknown_agent_raises() -> None:
    registry = AgentRegistry()
    with pytest.raises(KeyError):
        registry.get_agent("missing")
