from agentiva.interceptor.multi_agent_hook import MultiAgentInterceptor


def test_delegation_interception() -> None:
    interceptor = MultiAgentInterceptor()
    action = interceptor.intercept_delegation("agent-a", "agent-b", "review task")
    assert action.tool_name == "agent_delegation"


def test_data_transfer_sensitive_blocked() -> None:
    interceptor = MultiAgentInterceptor()
    action = interceptor.intercept_data_transfer("a", "b", {"ssn": "123-45-6789"})
    assert action.decision == "block"


def test_cascade_detection() -> None:
    interceptor = MultiAgentInterceptor()
    assert interceptor.detect_cascade("agent-a", list(range(11))) is True


def test_privilege_escalation_delegation_risk() -> None:
    interceptor = MultiAgentInterceptor()
    action = interceptor.intercept_delegation("analyst-agent", "admin-agent", "admin password reset")
    assert action.risk_score >= 0.8
