from agentiva import Agentiva


def test_openai_hook_blocks_external_email() -> None:
    shield = Agentiva(mode="shadow", policy_path="policies/default.yaml")

    def send_email(**kwargs):
        return kwargs

    tools = [{"name": "send_email", "__callable__": send_email}]
    wrapped = shield.protect_openai(tools)
    result = wrapped[0]["__callable__"](to="ext@outside.com", subject="x")
    assert result["blocked"] is True


def test_openai_hook_allows_safe_call() -> None:
    shield = Agentiva(mode="live")

    def safe_tool(**kwargs):
        return {"ok": True, "payload": kwargs}

    wrapped = shield.protect_openai([{"name": "safe_tool", "__callable__": safe_tool}])
    result = wrapped[0]["__callable__"](value=1)
    assert result["ok"] is True


def test_openai_hook_keeps_schema_fields() -> None:
    shield = Agentiva(mode="shadow")
    tool = {"name": "x", "description": "d", "__callable__": lambda **_: "x"}
    wrapped = shield.protect_openai([tool])[0]
    assert wrapped["name"] == "x"
    assert wrapped["description"] == "d"


def test_openai_hook_returns_explanation_on_block() -> None:
    shield = Agentiva(mode="shadow", policy_path="policies/default.yaml")
    wrapped = shield.protect_openai([{"name": "send_email", "__callable__": lambda **_: "x"}])[0]
    result = wrapped["__callable__"](to="x@outside.com")
    assert "explanation" in result
