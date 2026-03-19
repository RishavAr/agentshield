from agentshield.interceptor.code_agent_hook import CodeAgentInterceptor


def test_shell_command_rm_rf_critical() -> None:
    interceptor = CodeAgentInterceptor()
    action = interceptor.intercept_shell_command("rm -rf /")
    assert action.risk_score == 1.0
    assert action.decision == "block"


def test_shell_command_sudo_high_risk() -> None:
    interceptor = CodeAgentInterceptor()
    action = interceptor.intercept_shell_command("sudo apt update")
    assert action.risk_score >= 0.8


def test_file_write_env_detected() -> None:
    interceptor = CodeAgentInterceptor()
    action = interceptor.intercept_file_write(".env", "API_KEY=secret")
    assert action.risk_score >= 0.6


def test_git_force_push_risk() -> None:
    interceptor = CodeAgentInterceptor()
    action = interceptor.intercept_git_operation("push", {"force": True, "branch": "main"})
    assert action.risk_score >= 0.7
