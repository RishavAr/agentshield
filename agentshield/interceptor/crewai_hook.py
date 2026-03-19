from __future__ import annotations

from typing import Any


def shield_crewai_tool(tool: Any, interceptor: Any) -> Any:
    original_run = getattr(tool, "run", None)
    if original_run is None:
        return tool

    def _wrapped_run(*args, **kwargs):
        payload = kwargs if kwargs else {"input": args[0] if args else ""}
        action, negotiation = interceptor.intercept_with_negotiation_sync(
            tool_name=getattr(tool, "name", getattr(tool, "__name__", "crewai_tool")),
            arguments=payload,
        )
        if action.decision in {"block", "shadow"}:
            explanation = (
                negotiation.explanation.get("human_readable")
                if negotiation is not None
                else f"Action {action.decision}"
            )
            return f"[AgentShield CrewAI] {action.decision.upper()}: {explanation}"
        return original_run(*args, **kwargs)

    setattr(tool, "run", _wrapped_run)
    return tool


def shield_crewai_crew(crew: Any, interceptor: Any) -> Any:
    tools = getattr(crew, "tools", [])
    wrapped = [shield_crewai_tool(tool, interceptor) for tool in tools]
    setattr(crew, "tools", wrapped)
    return crew
