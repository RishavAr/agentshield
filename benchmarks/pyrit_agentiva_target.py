"""
PyRIT PromptTarget that routes every user prompt through Agentiva.intercept().

Used by benchmarks/pyrit_benchmark.py for an end-to-end PyRIT → Agentiva path.
"""

from __future__ import annotations

from pyrit.models import Message, construct_response_from_request
from pyrit.prompt_target.common.prompt_target import PromptTarget

from agentiva.interceptor.core import Agentiva


class AgentivaPromptTarget(PromptTarget):
    """Sends normalized prompts to Agentiva as synthetic `process_user_request` tool calls."""

    supported_converters: list = []

    def __init__(self, *, shield: Agentiva, agent_id: str = "pyrit-benchmark") -> None:
        super().__init__(model_name="agentiva-intercept")
        self._shield = shield
        self._agent_id = agent_id

    def _validate_request(self, *, message: Message) -> None:
        pass

    async def send_prompt_async(self, *, message: Message) -> list[Message]:
        self._validate_request(message=message)
        texts: list[str] = []
        for mp in message.message_pieces:
            if mp.api_role == "user":
                v = mp.converted_value if mp.converted_value is not None else mp.original_value
                texts.append(str(v))
        text = "\n".join(texts).strip() or "(empty)"
        action = await self._shield.intercept(
            tool_name="process_user_request",
            arguments={"prompt": text, "content": text},
            agent_id=self._agent_id,
        )
        body = f"[{str(action.decision).upper()} — risk {float(action.risk_score):.2f}]"
        req = message.message_pieces[0]
        return [construct_response_from_request(request=req, response_text_pieces=[body])]
