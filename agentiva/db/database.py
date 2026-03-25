from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentiva.db.models import (
    ActionLog,
    AgentRegistry,
    ApprovalLog,
    ApprovalQueue,
    Base,
    ChatMessage,
    ChatSession,
    NegotiationLog,
    PolicyHistory,
)

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./agentiva.db"


def _normalize_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _normalize_url(os.getenv("AGENTIVA_DATABASE_URL", DEFAULT_SQLITE_URL))
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


async def _ensure_action_logs_phi_detection_column() -> None:
    """Add phi_detection to action_logs when missing (SQLite upgrades)."""
    if "sqlite" not in DATABASE_URL.lower():
        return
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(action_logs)"))
        cols = [row[1] for row in result.fetchall()]
        if cols and "phi_detection" not in cols:
            await conn.execute(text("ALTER TABLE action_logs ADD COLUMN phi_detection JSON"))
            await conn.commit()


async def _ensure_chat_tables_exist() -> None:
    """
    Ensure chat persistence tables exist even on partially initialized databases.
    """
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                bind=sync_conn,
                tables=[ChatSession.__table__, ChatMessage.__table__],
            )
        )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_action_logs_phi_detection_column()
    await _ensure_chat_tables_exist()


async def health_check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def validate_audit_select_sql(sql: str) -> bool:
    """Only allow single-statement SELECT queries that reference action_logs."""
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].strip()
    sl = s.lower()
    if not sl.startswith("select"):
        return False
    if "action_logs" not in sl:
        return False
    for bad in ("insert ", "update ", "delete ", "drop ", "pragma", "attach ", "--", "/*", ";"):
        if bad in sl:
            return False
    return True


async def execute_audit_select(sql: str) -> List[Dict[str, Any]]:
    """Run a validated read-only query against the audit table."""
    if not validate_audit_select_sql(sql):
        raise ValueError("Invalid audit SQL: only SELECT from action_logs is allowed")
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        rows = result.mappings().all()
        return [dict(r) for r in rows]


async def log_action(action: Dict[str, Any]) -> None:
    row = ActionLog(
        id=action["id"],
        tool_name=action["tool_name"],
        arguments=action.get("arguments", {}),
        agent_id=action.get("agent_id", "default"),
        decision=action.get("decision", "pending"),
        risk_score=float(action.get("risk_score", 0.0)),
        mode=action.get("mode", "shadow"),
        simulation_result=action.get("simulation_result"),
        rollback_plan=action.get("rollback_plan"),
        phi_detection=action.get("phi_detection"),
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()


async def truncate_action_logs() -> None:
    """Clear all rows in action_logs (used by tests for isolated DB state)."""
    async with get_session() as session:
        await session.execute(delete(ActionLog))
        await session.commit()


async def count_all_action_logs() -> int:
    async with get_session() as session:
        r = await session.execute(select(func.count()).select_from(ActionLog))
        return int(r.scalar_one() or 0)


async def count_action_logs_by_decision(decision: str) -> int:
    async with get_session() as session:
        r = await session.execute(select(func.count()).where(ActionLog.decision == decision))
        return int(r.scalar_one() or 0)


async def get_last_chat_message_preview(session_id: str, max_len: int = 120) -> str:
    q = (
        select(ChatMessage.content)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(1)
    )
    async with get_session() as session:
        r = await session.execute(q)
        row = r.scalar_one_or_none()
        if not row:
            return ""
        text = str(row)
        return text if len(text) <= max_len else text[: max_len - 1] + "…"


async def list_actions(
    tool_name: Optional[str] = None,
    decision: Optional[str] = None,
    min_risk: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[ActionLog]:
    query = select(ActionLog).order_by(ActionLog.timestamp.desc())
    if tool_name:
        query = query.where(ActionLog.tool_name == tool_name)
    if decision:
        query = query.where(ActionLog.decision == decision)
    if min_risk is not None:
        query = query.where(ActionLog.risk_score >= min_risk)
    query = query.limit(limit).offset(offset)

    async with get_session() as session:
        result = await session.execute(query)
        return list(result.scalars().all())


async def list_actions_between(
    start: datetime,
    end: datetime,
    *,
    limit: int = 50000,
) -> List[ActionLog]:
    """All persisted audit rows in [start, end] (inclusive by timestamp)."""
    query = (
        select(ActionLog)
        .where(and_(ActionLog.timestamp >= start, ActionLog.timestamp <= end))
        .order_by(ActionLog.timestamp.desc())
        .limit(limit)
    )
    async with get_session() as session:
        result = await session.execute(query)
        return list(result.scalars().all())


async def add_policy_history(policy_yaml: str, applied_by: str = "system") -> str:
    policy_id = str(uuid.uuid4())
    row = PolicyHistory(id=policy_id, policy_yaml=policy_yaml, applied_by=applied_by)
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return policy_id


async def add_approval_log(
    action_id: str,
    approved: bool,
    reason: str = "",
    approved_by: str = "system",
) -> str:
    approval_id = str(uuid.uuid4())
    row = ApprovalLog(
        id=approval_id,
        action_id=action_id,
        approved=approved,
        reason=reason,
        approved_by=approved_by,
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return approval_id


async def add_negotiation_log(
    action_id: str,
    agent_id: str,
    status: str,
    explanation: Dict[str, Any],
    suggestions: List[Dict[str, Any]],
    proposed_safe_action: Optional[Dict[str, Any]] = None,
) -> str:
    negotiation_id = str(uuid.uuid4())
    row = NegotiationLog(
        id=negotiation_id,
        action_id=action_id,
        agent_id=agent_id,
        status=status,
        explanation=explanation,
        suggestions=suggestions,
        proposed_safe_action=proposed_safe_action or {},
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return negotiation_id


async def list_negotiations(limit: int = 200, offset: int = 0) -> List[NegotiationLog]:
    query = select(NegotiationLog).order_by(NegotiationLog.timestamp.desc()).limit(limit).offset(offset)
    async with get_session() as session:
        result = await session.execute(query)
        return list(result.scalars().all())


async def enqueue_approval(action_id: str, requested_by: str, reason: str = "") -> str:
    queue_id = str(uuid.uuid4())
    row = ApprovalQueue(
        id=queue_id,
        action_id=action_id,
        requested_by=requested_by,
        reason=reason,
        status="pending",
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return queue_id


async def touch_agent_registry(agent_id: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent_id))
        row = result.scalar_one_or_none()
        if row is None:
            row = AgentRegistry(id=str(uuid.uuid4()), agent_id=agent_id, reputation_score=0.5, actions_count=1)
            session.add(row)
        else:
            row.actions_count += 1
        await session.commit()


async def create_chat_session(tenant_id: str = "default", title: str = "New chat") -> ChatSession:
    sid = str(uuid.uuid4())
    row = ChatSession(id=sid, tenant_id=tenant_id, title=title[:500])
    async with get_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def list_chat_sessions(tenant_id: Optional[str] = None, limit: int = 50) -> List[ChatSession]:
    q = select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit)
    if tenant_id is not None:
        q = q.where(ChatSession.tenant_id == tenant_id)
    async with get_session() as session:
        result = await session.execute(q)
        return list(result.scalars().all())


async def get_chat_session(session_id: str) -> Optional[ChatSession]:
    async with get_session() as session:
        return await session.get(ChatSession, session_id)


async def update_chat_session_title(session_id: str, title: str) -> None:
    async with get_session() as session:
        row = await session.get(ChatSession, session_id)
        if row is None:
            return
        row.title = title[:500]
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()


async def delete_chat_session(session_id: str) -> bool:
    async with get_session() as session:
        row = await session.get(ChatSession, session_id)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
    return True


async def delete_all_chat_sessions() -> int:
    """Delete all chat messages + sessions. Returns deleted session count."""
    async with get_session() as session:
        n = await session.execute(select(func.count()).select_from(ChatSession))
        total_sessions = int(n.scalar_one() or 0)
        await session.execute(delete(ChatMessage))
        await session.execute(delete(ChatSession))
        await session.commit()
    return total_sessions


async def add_chat_message(
    session_id: str,
    role: str,
    content: str,
    grounding_data: Optional[Dict[str, Any]] = None,
    compliance_refs: Optional[List[str]] = None,
) -> str:
    mid = str(uuid.uuid4())
    msg = ChatMessage(
        id=mid,
        session_id=session_id,
        role=role,
        content=content,
        grounding_data=grounding_data,
        compliance_refs=compliance_refs or [],
    )
    async with get_session() as session:
        sess_row = await session.get(ChatSession, session_id)
        if sess_row is None:
            raise ValueError("session not found")
        sess_row.updated_at = datetime.now(timezone.utc)
        session.add(msg)
        await session.commit()
    return mid


async def list_chat_messages(session_id: str) -> List[ChatMessage]:
    q = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp.asc())
    )
    async with get_session() as session:
        result = await session.execute(q)
        return list(result.scalars().all())


def export_chat_markdown(messages: List[ChatMessage]) -> str:
    parts: List[str] = ["# Agentiva chat export\n"]
    for m in messages:
        parts.append(f"\n## {m.role.upper()}\n{m.content}\n")
    return "\n".join(parts)


def alembic_migration_note() -> str:
    return (
        "Alembic-ready SQLAlchemy metadata is available at agentiva.db.models.Base. "
        "Run: alembic init alembic && configure sqlalchemy.url to AGENTIVA_DATABASE_URL."
    )
