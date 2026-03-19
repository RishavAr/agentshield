from langchain_core.tools import BaseTool


def shield_tool(tool: BaseTool, interceptor) -> BaseTool:
    original_run = tool._run

    def shielded_run(*args, **kwargs) -> str:
        action = interceptor.intercept_sync(
            tool_name=tool.name,
            arguments=kwargs if kwargs else {"input": args[0] if args else ""},
        )
        if action.decision in ("shadow", "block"):
            return (
                f"[AgentShield] Action {action.decision}. "
                f"Tool: {tool.name}. Risk: {action.risk_score}."
            )
        if action.decision == "approve":
            return f"[AgentShield] Action requires approval. Tool: {tool.name}."
        return original_run(*args, **kwargs)

    tool._run = shielded_run
    return tool


def shield_all_tools(tools: list, interceptor) -> list:
    return [shield_tool(t, interceptor) for t in tools]
