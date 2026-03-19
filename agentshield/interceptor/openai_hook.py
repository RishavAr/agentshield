from __future__ import annotations

from typing import Any, Callable, Dict, List


def shield_openai_tool(tool: Dict[str, Any], interceptor: Any) -> Dict[str, Any]:
    # OpenAI-style function tool schema with callable stored in "__callable__"
    callable_fn: Callable[..., Any] | None = tool.get("__callable__")
    if callable_fn is None:
        return tool

    def _wrapped_callable(**kwargs):
        action, negotiation = interceptor.intercept_with_negotiation_sync(
            tool_name=tool.get("name", "openai_tool"),
            arguments=kwargs,
        )
        if action.decision in {"block", "shadow"}:
            explanation = (
                negotiation.explanation.get("human_readable")
                if negotiation is not None
                else f"Action {action.decision}"
            )
            return {"blocked": True, "decision": action.decision, "explanation": explanation}
        return callable_fn(**kwargs)

    wrapped = dict(tool)
    wrapped["__callable__"] = _wrapped_callable
    return wrapped


def shield_openai_tools(tools: List[Dict[str, Any]], interceptor: Any) -> List[Dict[str, Any]]:
    return [shield_openai_tool(tool, interceptor) for tool in tools]
