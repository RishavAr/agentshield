from agentiva import Agentiva


class DummyCrewTool:
    def __init__(self, name: str):
        self.name = name

    def run(self, **kwargs):
        return f"ok:{kwargs}"


class DummyCrew:
    def __init__(self, tools):
        self.tools = tools


def test_crewai_tool_blocked_message() -> None:
    shield = Agentiva(mode="shadow", policy_path="policies/default.yaml")
    tool = DummyCrewTool("send_email")
    wrapped = shield.protect_crewai(DummyCrew([tool])).tools[0]
    output = wrapped.run(to="evil@outside.com", subject="x")
    assert "BLOCK" in output.upper() or "SHADOW" in output.upper()


def test_crewai_tool_allows_passthrough_for_allow_mode() -> None:
    shield = Agentiva(mode="live", policy_path=None)
    tool = DummyCrewTool("safe_tool")
    wrapped = shield.protect_crewai(DummyCrew([tool])).tools[0]
    output = wrapped.run(input="x")
    assert output.startswith("ok:")


def test_crewai_crew_wraps_all_tools() -> None:
    shield = Agentiva(mode="shadow")
    crew = DummyCrew([DummyCrewTool("a"), DummyCrewTool("b")])
    wrapped = shield.protect_crewai(crew)
    assert len(wrapped.tools) == 2


def test_crewai_block_contains_agentiva_marker() -> None:
    shield = Agentiva(mode="shadow")
    tool = DummyCrewTool("send_email")
    wrapped = shield.protect_crewai(DummyCrew([tool])).tools[0]
    output = wrapped.run(to="anyone@outside.com")
    assert "[Agentiva CrewAI]" in output
