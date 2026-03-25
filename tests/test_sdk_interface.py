from agentiva import Agentiva


def test_sdk_constructor_with_policy_template() -> None:
    shield = Agentiva(mode="shadow", policy="healthcare")
    assert shield.mode == "shadow"


def test_sdk_protect_openai_and_crewai_methods_exist() -> None:
    shield = Agentiva(mode="shadow")
    assert hasattr(shield, "protect_openai")
    assert hasattr(shield, "protect_crewai")


def test_sdk_start_mcp_proxy_method_exists() -> None:
    shield = Agentiva(mode="shadow")
    assert callable(shield.start_mcp_proxy)


def test_sdk_protect_shell_returns_interceptor() -> None:
    shield = Agentiva(mode="shadow")
    interceptor = shield.protect_shell()
    assert hasattr(interceptor, "intercept_shell_command")


def test_sdk_custom_intercept_decorator() -> None:
    shield = Agentiva(mode="shadow")

    @shield.intercept("my_custom_tool")
    def my_handler(action):
        return action

    assert my_handler("ok") == "ok"
