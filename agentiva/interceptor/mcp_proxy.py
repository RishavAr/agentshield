from __future__ import annotations

import argparse
from typing import Any, Dict

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agentiva.interceptor.core import Agentiva


class MCPRequest(BaseModel):
    tool_name: str = Field(..., min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    agent_id: str = "mcp-agent"


def create_mcp_proxy_app(upstream: str, shield: Agentiva) -> FastAPI:
    app = FastAPI(title="Agentiva MCP Proxy")

    @app.post("/mcp/call")
    async def mcp_call(req: MCPRequest):
        action, negotiation = await shield.intercept_with_negotiation(
            req.tool_name, req.arguments, req.agent_id
        )
        if action.decision == "block":
            return {
                "blocked": True,
                "decision": action.decision,
                "risk_score": action.risk_score,
                "negotiation": negotiation.to_dict() if negotiation else None,
            }

        try:
            async with httpx.AsyncClient(base_url=f"http://{upstream}") as client:
                resp = await client.post(
                    "/mcp/call",
                    json={
                        "tool_name": req.tool_name,
                        "arguments": req.arguments,
                        "agent_id": req.agent_id,
                    },
                )
            return {"blocked": False, "upstream_status": resp.status_code, "upstream_response": resp.json()}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Upstream MCP error: {exc}") from exc

    return app


def run_proxy(upstream: str, port: int) -> None:
    import uvicorn

    shield = Agentiva(mode="shadow", policy_path="policies/default.yaml")
    app = create_mcp_proxy_app(upstream=upstream, shield=shield)
    uvicorn.run(app, host="0.0.0.0", port=port)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", default="localhost:3001")
    parser.add_argument("--port", type=int, default=3002)
    args = parser.parse_args()
    run_proxy(upstream=args.upstream, port=args.port)


if __name__ == "__main__":
    main()
