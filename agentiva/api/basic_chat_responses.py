"""
Conversational deterministic chat: delegates to `chat_router` for one source of truth.

Allow-one / shadow→allow flows must run through `ShieldChat` (not the router stub) so
`apply_now` policy updates and in-memory + DB audit targets work end-to-end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from agentiva.api import chat_router as cr
from agentiva.api.chat import ChatResponse, ShieldChat, is_allow_one_user_message

if TYPE_CHECKING:
    from agentiva.interceptor.core import Agentiva


async def try_deterministic_chat(
    user_message: str,
    shield: "Agentiva | None" = None,
    history: Optional[List[Dict[str, str]]] = None,
    session_id: Optional[str] = None,
) -> Optional[ChatResponse]:
    msg = (user_message or "").strip()
    if not msg:
        return None
    if shield is not None:
        # If the user says "Confirm" as a follow-up, infer the allow-one context from
        # recent history (the UI often sends "Confirm" as a standalone message).
        if msg.lower() in {"confirm", "yes confirm", "yes, confirm"}:
            recent_user = [
                (h.get("content") or "")
                for h in (history or [])
                if (h.get("role") or "").lower() == "user"
            ][-5:]
            if any(is_allow_one_user_message(t) for t in recent_user):
                return await ShieldChat(shield).ask("allow this one confirm")

        if is_allow_one_user_message(msg):
            return await ShieldChat(shield).ask(msg)
    sid = session_id or ""
    r = await cr.generate_response(msg, db=None, session_id=sid, history=history)
    return ChatResponse(
        answer=r["content"],
        data={},
        follow_up_suggestions=r.get("suggestions", []),
        mode="basic",
    )
