from agentiva.interceptor.browser_agent_hook import BrowserAgentInterceptor


def test_navigation_unknown_domain_risk() -> None:
    interceptor = BrowserAgentInterceptor()
    action = interceptor.intercept_navigation("https://unknown-domain.example")
    assert action.risk_score >= 0.5


def test_form_submission_payment_high_risk() -> None:
    interceptor = BrowserAgentInterceptor()
    action = interceptor.intercept_form_submission({"payment": "4111111111111111", "cvv": "123"})
    assert action.risk_score >= 0.8


def test_download_executable_block() -> None:
    interceptor = BrowserAgentInterceptor()
    action = interceptor.intercept_download("https://example.com/tool.exe", "tool.exe")
    assert action.decision == "block"
