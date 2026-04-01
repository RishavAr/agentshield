import asyncio

from agentiva.interceptor.core import Agentiva


def test_intercept_records_action() -> None:
    shield = Agentiva(mode="shadow")
    action = asyncio.run(
        shield.intercept("send_email", {"to": "user@example.com"}, agent_id="agent-1")
    )

    assert action.tool_name == "send_email"
    assert action.agent_id == "agent-1"
    assert action.mode == "shadow"
    # No policy file in this smoke test — decision comes from risk bands only.
    assert action.decision in {"allow", "shadow", "block"}
    assert len(shield.get_audit_log()) == 1


if __name__ == "__main__":
    test_intercept_records_action()
    print("tests.test_core passed")
