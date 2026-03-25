"""
Conversational deterministic chat: delegates to `chat_router` for one source of truth.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from agentiva.api import chat_router as cr
from agentiva.api.chat import ChatResponse


async def try_deterministic_chat(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    session_id: Optional[str] = None,
) -> Optional[ChatResponse]:
    msg = (user_message or "").strip()
    if not msg:
        return None
    sid = session_id or ""
    r = await cr.generate_response(msg, db=None, session_id=sid, history=history)
    return ChatResponse(
        answer=r["content"],
        data={},
        follow_up_suggestions=r.get("suggestions", []),
        mode="basic",
    )
