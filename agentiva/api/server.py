import asyncio
import logging
import os
import random
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Deque, Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import AliasChoices, BaseModel, Field, field_validator

from agentiva.db.database import (
    add_approval_log,
    add_chat_message,
    add_negotiation_log,
    add_policy_history,
    count_action_logs_by_decision,
    count_all_action_logs,
    create_chat_session,
    delete_all_chat_sessions,
    delete_chat_session,
    enqueue_approval,
    export_chat_markdown,
    get_chat_session,
    get_last_chat_message_preview,
    health_check_db,
    init_db,
    list_actions_between,
    list_chat_messages,
    list_chat_sessions,
    list_negotiations,
    log_action,
    touch_agent_registry,
    update_chat_session_title,
)
from agentiva.audit.compliance import ComplianceExporter
from agentiva.alerts.alerter import AlertManager
from agentiva.auth.tenancy import TenantManager
from agentiva.interceptor.core import Agentiva
from agentiva.policy.anomaly_detector import AnomalyDetector
from agentiva.registry.agent_registry import AgentRegistry

from agentiva.api.chat import ChatResponse, ShieldChat, SmartChat, chat_response_to_dict
from agentiva.api.chat_router import router as chat_router
from agentiva.compliance.hipaa_report import build_hipaa_pdf
from agentiva.compliance.pci_report import build_pci_pdf
from agentiva.compliance.soc2_report import build_soc2_pdf

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentiva.api")


class InterceptRequest(BaseModel):
    tool_name: str = Field(
        ..., min_length=1, max_length=256, description="Name of the tool being called"
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool call arguments"
    )
    agent_id: str = Field(
        default="default", max_length=128, description="Identifier for the agent"
    )
    context: Dict[str, Any] | None = Field(
        default=None, description="Optional context about who/what is requesting the action"
    )
    timestamp: str | None = Field(
        default=None,
        description="Optional ISO 8601 time for risk scoring (e.g. simulated off-hours action)",
    )

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool_name cannot be empty")
        return value.strip()


class InterceptResponse(BaseModel):
    action_id: str
    tool_name: str
    arguments: Dict[str, Any]
    agent_id: str
    decision: str
    risk_score: float
    mode: str
    timestamp: str
    phi_detection: Optional[Dict[str, Any]] = None


class AuditEntry(BaseModel):
    action_id: str
    tool_name: str
    arguments: Dict[str, Any]
    agent_id: str
    decision: str
    risk_score: float
    mode: str
    mandatory: bool = False
    timestamp: str
    phi_detection: Optional[Dict[str, Any]] = None


class ShadowReport(BaseModel):
    total_actions: int
    by_tool: Dict[str, int]
    by_decision: Dict[str, int]
    avg_risk_score: float


class PolicyUpdateRequest(BaseModel):
    policy_yaml: str = Field(..., min_length=1, description="YAML policy content")


class HealthResponse(BaseModel):
    status: str
    version: str
    mode: str
    total_actions_intercepted: int
    uptime_seconds: float


class MetricsResponse(BaseModel):
    total_requests: int
    avg_latency_ms: float
    error_rate: float


class ApprovalRequest(BaseModel):
    action_id: str
    approved: bool
    reason: str = ""


class ApprovalSubmitRequest(BaseModel):
    action_id: str
    reason: str = ""
    requested_by: str = "agent"


class RetryRequest(BaseModel):
    modified_arguments: Dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(default="agent", max_length=128)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected total=%d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("websocket_disconnected total=%d", len(self.active_connections))

    async def broadcast(self, message: Dict[str, Any]) -> None:
        disconnected: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for connection in disconnected:
            self.disconnect(connection)


_shield: Optional[Agentiva] = None
_manager = ConnectionManager()
_start_time: Optional[datetime] = None
_pending_approvals: Dict[str, bool] = {}
_request_counts_by_agent: Dict[str, Deque[float]] = {}
_rate_limit_per_minute = int(os.getenv("AGENTIVA_RATE_LIMIT_PER_MINUTE", "100"))
_metrics: Dict[str, float] = {
    "total_requests": 0,
    "total_errors": 0,
    "total_latency_ms": 0.0,
}
_runtime_settings: Dict[str, Any] = {"risk_threshold": 0.7, "mode": "shadow"}
_retry_chain: Dict[str, Dict[str, Any]] = {}
_tenant_manager = TenantManager()
_registry = AgentRegistry()
_alerter = AlertManager()
_anomaly_detector = AnomalyDetector()


def _bootstrap_default_tenant() -> None:
    env_key = os.getenv("AGENTIVA_DEFAULT_API_KEY")
    if env_key and not _tenant_manager.is_enabled():
        _tenant_manager.register_tenant("default", "Default Tenant", env_key)


_bootstrap_default_tenant()


def get_shield() -> Agentiva:
    if _shield is None:
        raise HTTPException(status_code=500, detail="Agentiva not initialized")
    return _shield


async def _chat_answer_with_optional_deterministic(
    msg: str,
    shield: Agentiva,
    history: Optional[List[Dict[str, str]]] = None,
    session_id: Optional[str] = None,
) -> ChatResponse:
    """HTTP routes: prefer DB-grounded deterministic replies; fall back to Shield/Smart chat."""
    try:
        from agentiva.api.basic_chat_responses import try_deterministic_chat

        det = await try_deterministic_chat(msg, history=history, session_id=session_id)
        if det is not None:
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                await asyncio.sleep(random.uniform(0.5, 0.8))
            return det
    except Exception:
        logger.exception("deterministic_chat_failed")
    if os.getenv("OPENROUTER_API_KEY", "").strip():
        chat = SmartChat(shield)
    else:
        chat = ShieldChat(shield)
    resp = await chat.ask(msg)
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        await asyncio.sleep(random.uniform(0.5, 0.8))
    return resp


def _maybe_remove_legacy_sqlite_files() -> None:
    if os.getenv("AGENTIVA_RESET_LEGACY_DB", "").lower() not in ("1", "true", "yes"):
        return
    for name in ("agentshield.db", "agentiva.db"):
        path = os.path.abspath(name)
        if os.path.isfile(path):
            try:
                os.remove(path)
                logger.info("removed_legacy_sqlite path=%s", path)
            except OSError as exc:
                logger.warning("could_not_remove_sqlite path=%s err=%s", path, exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _shield, _start_time
    _start_time = datetime.now(timezone.utc)
    print(
        f"[Agentiva] OPENROUTER_API_KEY: {'SET' if os.getenv('OPENROUTER_API_KEY') else 'NOT SET'}"
    )
    logger.info(
        "openrouter_api_key=%s",
        "set" if os.getenv("OPENROUTER_API_KEY") else "not_set",
    )
    mode = os.getenv("AGENTIVA_MODE", "shadow")
    env_policy = os.getenv("AGENTIVA_POLICY_PATH", "").strip()
    if env_policy and os.path.isfile(env_policy):
        policy_path = env_policy
    elif os.path.exists("policies/default.yaml"):
        policy_path = "policies/default.yaml"
    else:
        policy_path = None
    _maybe_remove_legacy_sqlite_files()
    import agentiva.db.models  # noqa: F401 — ensure all models registered on Base.metadata

    await init_db()
    logger.info("[Agentiva] Database tables created/verified (SQLAlchemy metadata)")
    if not await health_check_db():
        raise RuntimeError("Database health check failed at startup")
    if policy_path:
        with open(policy_path, encoding="utf-8") as handle:
            yaml.safe_load(handle)
    _shield = Agentiva(mode=mode, policy_path=policy_path)
    logger.info("agentiva_started mode=%s policy=%s", mode, policy_path)
    try:
        yield
    finally:
        logger.info("agentiva_stopping")


app = FastAPI(
    title="Agentiva",
    description="Preview deployments for AI agents. Intercept, preview, approve, and rollback agent actions.",
    version="0.1.0",
    lifespan=lifespan,
)

# Browsers reject credentialed CORS with wildcard origins; dashboard uses simple fetch (no cookies).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.perf_counter()
    _metrics["total_requests"] += 1
    if request.url.path.startswith("/api/") and _tenant_manager.is_enabled():
        # Chat co-pilot must remain available in deterministic/basic mode without API keys.
        # We keep tenant auth for the rest of the API surface.
        if request.url.path.startswith("/api/v1/chat"):
            request.state.tenant_id = "default"
        else:
            api_key = request.headers.get("X-Agentiva-Key")
            if not api_key:
                return JSONResponse(status_code=401, content={"error": {"type": "unauthorized", "message": "Missing X-Agentiva-Key"}})
            try:
                tenant = _tenant_manager.tenant_from_key(api_key)
                request.state.tenant_id = tenant.tenant_id
            except KeyError:
                return JSONResponse(status_code=403, content={"error": {"type": "forbidden", "message": "Invalid API key"}})
    try:
        response = await call_next(request)
    except Exception as exc:
        _metrics["total_errors"] += 1
        logger.exception("unhandled_error request_id=%s path=%s", request_id, request.url.path)
        response = JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_server_error",
                    "message": "Unexpected server error",
                    "request_id": request_id,
                }
            },
        )
    latency_ms = (time.perf_counter() - start) * 1000
    _metrics["total_latency_ms"] += latency_ms
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request request_id=%s method=%s path=%s status=%s latency_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
    )
    return response


def _rate_limit_allow(agent_id: str) -> bool:
    now = time.time()
    bucket = _request_counts_by_agent.setdefault(agent_id, deque())
    while bucket and (now - bucket[0]) > 60:
        bucket.popleft()
    if len(bucket) >= _rate_limit_per_minute:
        return False
    bucket.append(now)
    return True


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    shield = get_shield()
    if _start_time is None:
        raise HTTPException(status_code=500, detail="Server start time unavailable")
    elapsed = (datetime.now(timezone.utc) - _start_time).total_seconds()
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        mode=shield.mode,
        total_actions_intercepted=len(shield.audit_log),
        uptime_seconds=round(elapsed, 2),
    )


@app.post("/api/v1/intercept", response_model=InterceptResponse)
async def intercept_action(request: InterceptRequest) -> InterceptResponse:
    shield = get_shield()
    if not _rate_limit_allow(request.agent_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for agent_id")
    try:
        if request.agent_id in [a["id"] for a in _registry.list_agents()]:
            profile = _registry.get_agent(request.agent_id)
            if profile.status in {"suspended", "deactivated"}:
                raise HTTPException(status_code=403, detail=f"Agent {request.agent_id} is {profile.status}")
        action = await shield.intercept(
            tool_name=request.tool_name,
            arguments=request.arguments,
            agent_id=request.agent_id,
            context=request.context,
            timestamp=request.timestamp,
        )
        await log_action(
            {
                "id": action.id,
                "tool_name": action.tool_name,
                "arguments": action.arguments,
                "agent_id": action.agent_id,
                "decision": action.decision,
                "risk_score": action.risk_score,
                "mode": action.mode,
                "simulation_result": (action.result or {}).get("simulation"),
                "rollback_plan": action.rollback_plan,
                "phi_detection": (action.result or {}).get("phi_detection"),
            }
        )
        await touch_agent_registry(request.agent_id)
        alerts = _anomaly_detector.analyze(
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            risk_score=action.risk_score,
            data_volume=len(str(request.arguments)),
        )
        if action.decision == "block" or action.risk_score >= 0.8 or alerts:
            await _alerter.send_alert("policy_event", action, channel="websocket")
        if any(a["id"] == request.agent_id for a in _registry.list_agents()):
            _registry.update_reputation(request.agent_id, action.decision)
    except Exception as exc:
        _metrics["total_errors"] += 1
        logger.exception("interception_failed tool=%s", request.tool_name)
        raise HTTPException(status_code=500, detail=f"Interception failed: {exc}") from exc

    response = InterceptResponse(
        action_id=action.id,
        tool_name=action.tool_name,
        arguments=action.arguments,
        agent_id=action.agent_id,
        decision=action.decision,
        risk_score=action.risk_score,
        mode=action.mode,
        timestamp=action.timestamp,
        phi_detection=(action.result or {}).get("phi_detection"),
    )

    await _manager.broadcast(response.model_dump())
    logger.info(
        "action_intercepted tool=%s decision=%s risk=%.2f agent=%s",
        action.tool_name,
        action.decision,
        action.risk_score,
        action.agent_id,
    )
    return response


@app.get("/api/v1/compliance/soc2")
async def compliance_soc2(start: str, end: str) -> Dict[str, Any]:
    shield = get_shield()
    exporter = ComplianceExporter(shield.audit_log, approvals=_pending_approvals)
    return exporter.export_soc2_report(start, end)


@app.get("/api/v1/compliance/gdpr/{data_subject_id}")
async def compliance_gdpr(data_subject_id: str) -> Dict[str, Any]:
    shield = get_shield()
    exporter = ComplianceExporter(shield.audit_log, approvals=_pending_approvals)
    return exporter.export_gdpr_data_access_log(data_subject_id)


@app.get("/api/v1/compliance/eu-ai-act")
async def compliance_eu_ai_act() -> Dict[str, Any]:
    shield = get_shield()
    exporter = ComplianceExporter(shield.audit_log, approvals=_pending_approvals)
    return exporter.export_eu_ai_act_transparency()


def _parse_report_range(start: Optional[str], end: Optional[str]) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if end:
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
    else:
        end_dt = now
    if start:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
    else:
        start_dt = end_dt - timedelta(days=30)
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    return start_dt, end_dt


@app.get("/api/v1/compliance/soc2/report")
async def compliance_soc2_report_pdf(
    start: Optional[str] = Query(None, description="ISO8601 start (default: 30 days before end)"),
    end: Optional[str] = Query(None, description="ISO8601 end (default: now UTC)"),
    company: str = Query("Your Organization", max_length=256),
):
    """Download auditor-style SOC2 PDF built from persisted action_logs."""
    start_dt, end_dt = _parse_report_range(start, end)
    rows = await list_actions_between(start_dt, end_dt)
    pdf = build_soc2_pdf(rows, start_dt, end_dt, company_name=company)
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="agentiva-soc2-report.pdf"'},
    )


@app.get("/api/v1/compliance/hipaa/report")
async def compliance_hipaa_report_pdf(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    company: str = Query("Your Organization", max_length=256),
):
    """Download HIPAA audit-style PDF from persisted action_logs."""
    start_dt, end_dt = _parse_report_range(start, end)
    rows = await list_actions_between(start_dt, end_dt)
    pdf = build_hipaa_pdf(rows, start_dt, end_dt, company_name=company)
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="agentiva-hipaa-report.pdf"'},
    )


@app.get("/api/v1/compliance/pci/report")
async def compliance_pci_report_pdf(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    company: str = Query("Your Organization", max_length=256),
):
    """Download PCI-DSS summary PDF from persisted action_logs."""
    start_dt, end_dt = _parse_report_range(start, end)
    rows = await list_actions_between(start_dt, end_dt)
    pdf = build_pci_pdf(rows, start_dt, end_dt, company_name=company)
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="agentiva-pci-report.pdf"'},
    )


@app.get("/api/v1/export/csv")
async def export_csv(
    tool_name: Optional[str] = None,
    decision: Optional[str] = None,
) -> str:
    shield = get_shield()
    exporter = ComplianceExporter(shield.audit_log, approvals=_pending_approvals)
    return exporter.export_csv({"tool_name": tool_name, "decision": decision})


@app.get("/api/v1/export/siem")
async def export_siem(format: str = "json", tool_name: Optional[str] = None, decision: Optional[str] = None):
    _ = format
    shield = get_shield()
    exporter = ComplianceExporter(shield.audit_log, approvals=_pending_approvals)
    return exporter.export_json_siem({"tool_name": tool_name, "decision": decision})


class RegisterAgentRequest(BaseModel):
    agent_id: str
    name: str
    owner: str
    allowed_tools: List[str] = Field(default_factory=list)
    max_risk_tolerance: float = 0.8
    role: str | None = None


@app.post("/api/v1/agents")
async def register_agent(payload: RegisterAgentRequest) -> Dict[str, Any]:
    agent = _registry.register_agent(
        payload.agent_id,
        payload.name,
        payload.owner,
        payload.allowed_tools,
        payload.max_risk_tolerance,
        role=payload.role,
    )
    return agent.to_dict()


@app.get("/api/v1/agents")
async def list_agents() -> List[Dict[str, Any]]:
    return _registry.list_agents()


@app.post("/api/v1/agents/{agent_id}/deactivate")
async def deactivate_agent(agent_id: str) -> Dict[str, str]:
    _registry.deactivate_agent(agent_id)
    return {"status": "ok", "agent_id": agent_id, "new_status": "deactivated"}


async def _persist_intercepted_action(action: Any) -> None:
    await log_action(
        {
            "id": action.id,
            "tool_name": action.tool_name,
            "arguments": action.arguments,
            "agent_id": action.agent_id,
            "decision": action.decision,
            "risk_score": action.risk_score,
            "mode": action.mode,
            "simulation_result": (action.result or {}).get("simulation"),
            "rollback_plan": action.rollback_plan,
            "phi_detection": (action.result or {}).get("phi_detection"),
        }
    )
    await touch_agent_registry(action.agent_id)
    if any(a["id"] == action.agent_id for a in _registry.list_agents()):
        _registry.update_reputation(action.agent_id, action.decision)


class AgentRegisterPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    framework: str = "custom"
    allowed_tools: List[str] = Field(default_factory=list)
    max_risk_tolerance: float = 0.8
    owner_email: str = "owner@localhost"


class AgentUpdatePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    allowed_tools: Optional[List[str]] = None


@app.post("/api/v1/agents/register")
async def register_agent_onboarding(payload: AgentRegisterPayload) -> Dict[str, Any]:
    """Register an agent and return a one-time API key (agv_live_…)."""
    agent, api_key = _registry.register_with_api_key(
        name=payload.name.strip(),
        description=(payload.description or "").strip(),
        framework=(payload.framework or "custom").strip() or "custom",
        allowed_tools=payload.allowed_tools or ["send_email"],
        max_risk_tolerance=float(payload.max_risk_tolerance),
        owner_email=(payload.owner_email or "owner@localhost").strip() or "owner@localhost",
    )
    return {
        "agent_id": agent.id,
        "api_key": api_key,
        "name": agent.name,
        "created_at": agent.created_at,
        "description": agent.description,
        "framework": agent.framework,
    }


@app.patch("/api/v1/agents/{agent_id}")
async def update_agent_onboarding(agent_id: str, payload: AgentUpdatePayload) -> Dict[str, Any]:
    try:
        agent = _registry.update_agent(
            agent_id,
            name=payload.name,
            description=payload.description,
            allowed_tools=payload.allowed_tools,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.to_dict()


@app.delete("/api/v1/agents/{agent_id}")
async def delete_agent_onboarding(agent_id: str) -> Dict[str, Any]:
    deleted = _registry.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "ok", "deleted": True, "agent_id": agent_id}


@app.get("/api/v1/bootstrap")
async def onboarding_bootstrap() -> Dict[str, Any]:
    agents = _registry.list_agents()
    n = await count_all_action_logs()
    return {
        "agents_count": len(agents),
        "action_logs_count": n,
        "is_empty": len(agents) == 0 and n == 0,
    }


@app.post("/api/v1/demo/seed")
async def demo_seed_sample_data() -> Dict[str, Any]:
    """Insert realistic sample intercepts into the audit log and in-memory shield."""
    shield = get_shield()
    if not any(a["id"] == "demo-agent-1" for a in _registry.list_agents()):
        _registry.register_agent(
            "demo-agent-1",
            "Demo Agent",
            "demo@agentiva.local",
            ["send_email", "read_customer_data", "update_database", "call_external_api", "create_ticket"],
            0.85,
            description="Sample onboarding agent",
            framework="demo",
        )
    scenarios: List[tuple[str, Dict[str, Any], str]] = [
        ("send_email", {"to": "x@evil.com", "subject": "customer data"}, "demo-agent-1"),
        ("send_email", {"to": "ally@yourcompany.com", "subject": "Standup notes"}, "demo-agent-1"),
        ("read_customer_data", {"fields": "ssn"}, "demo-agent-1"),
        ("read_customer_data", {"fields": "name"}, "demo-agent-1"),
        ("update_database", {"query": "SELECT 1"}, "demo-agent-1"),
        ("create_ticket", {"title": "Bug"}, "demo-agent-1"),
    ]
    created = 0
    for tool, args, aid in scenarios:
        action = await shield.intercept(tool_name=tool, arguments=args, agent_id=aid)
        await _persist_intercepted_action(action)
        await _manager.broadcast(
            {
                "action_id": action.id,
                "tool_name": action.tool_name,
                "arguments": action.arguments,
                "agent_id": action.agent_id,
                "decision": action.decision,
                "risk_score": action.risk_score,
                "mode": action.mode,
                "timestamp": action.timestamp,
            }
        )
        created += 1
    return {"status": "ok", "actions_created": created, "agent_id": "demo-agent-1"}


class ChatMessageRequest(BaseModel):
    """Accept either `message` or `content` (same field)."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Question for Agentiva chat",
        validation_alias=AliasChoices("message", "content"),
    )


@app.get("/api/v1/chat/capabilities")
async def chat_capabilities() -> Dict[str, Any]:
    """Whether OpenRouter-powered (premium) chat is configured."""
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return {
        "llm_enabled": bool(key),
        "provider": "openrouter" if key else None,
    }


@app.post("/api/v1/chat")
async def chat_with_shield(payload: ChatMessageRequest) -> Dict[str, Any]:
    """Ask questions about agent activity using the in-memory audit log."""
    shield = get_shield()
    resp = await _chat_answer_with_optional_deterministic(
        payload.message.strip(), shield, history=None, session_id=None
    )
    # If the chat computed an auto-policy update, apply it server-side.
    try:
        if isinstance(getattr(resp, "data", None), dict) and resp.data.get("apply_now"):
            policy_yaml = resp.data.get("policy_yaml") or ""
            if policy_yaml:
                await update_policy(PolicyUpdateRequest(policy_yaml=policy_yaml))
    except Exception as exc:
        logger.exception("policy_update_from_chat_failed exc=%s", exc)
    return chat_response_to_dict(resp)


class ChatSessionCreate(BaseModel):
    tenant_id: str = "default"
    title: str = "New chat"


class ChatSessionPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)


class RuntimeSettingsPayload(BaseModel):
    risk_threshold: float = Field(0.7, ge=0.0, le=1.0)
    mode: str = Field("shadow")


@app.get("/api/v1/chat/sessions")
async def chat_sessions_list(tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = await list_chat_sessions(tenant_id=tenant_id)
    out: List[Dict[str, Any]] = []
    for r in rows:
        preview = await get_last_chat_message_preview(r.id)
        out.append(
            {
                "id": r.id,
                "tenant_id": r.tenant_id,
                "title": r.title,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
                "last_message_preview": preview,
            }
        )
    return out


@app.patch("/api/v1/chat/sessions/{session_id}")
async def chat_session_rename(session_id: str, payload: ChatSessionPatch) -> Dict[str, Any]:
    sess = await get_chat_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await update_chat_session_title(session_id, payload.title.strip())
    row = await get_chat_session(session_id)
    assert row is not None
    return {
        "id": row.id,
        "title": row.title,
        "tenant_id": row.tenant_id,
        "updated_at": row.updated_at.isoformat(),
    }


@app.delete("/api/v1/chat/sessions/all")
async def chat_sessions_delete_all() -> Dict[str, Any]:
    deleted = await delete_all_chat_sessions()
    return {"status": "ok", "deleted_sessions": deleted}


@app.post("/api/v1/chat/sessions")
async def chat_sessions_create(payload: ChatSessionCreate) -> Dict[str, Any]:
    try:
        row = await create_chat_session(tenant_id=payload.tenant_id, title=payload.title)
    except Exception as exc:
        logger.exception("chat_session_create_failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Could not create chat session: {exc}") from exc
    return {"id": row.id, "title": row.title, "tenant_id": row.tenant_id}


@app.get("/api/v1/chat/sessions/{session_id}/messages")
async def chat_session_messages_list(session_id: str) -> Dict[str, Any]:
    sess = await get_chat_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await list_chat_messages(session_id)
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in messages
        ],
    }


@app.get("/api/v1/chat/sessions/{session_id}")
async def chat_session_detail(session_id: str) -> Dict[str, Any]:
    sess = await get_chat_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await list_chat_messages(session_id)
    return {
        "session": {
            "id": sess.id,
            "title": sess.title,
            "tenant_id": sess.tenant_id,
            "created_at": sess.created_at.isoformat(),
            "updated_at": sess.updated_at.isoformat(),
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "grounding_data": m.grounding_data,
                "compliance_refs": m.compliance_refs,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in messages
        ],
    }


@app.delete("/api/v1/chat/sessions/{session_id}")
async def chat_session_delete(session_id: str) -> Dict[str, str]:
    ok = await delete_chat_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok", "id": session_id}


@app.post("/api/v1/chat/sessions/{session_id}/messages")
async def chat_session_post_message(session_id: str, payload: ChatMessageRequest) -> Dict[str, Any]:
    sess = await get_chat_session(session_id)
    if sess is None:
        # Convenience fallback: allow clients/tests to post to an arbitrary ID first.
        row = await create_chat_session(tenant_id="default", title="New conversation")
        session_id = row.id
        sess = row
    msg = payload.message.strip()
    prior_msgs = await list_chat_messages(session_id)
    history = [{"role": m.role, "content": m.content} for m in prior_msgs[-5:]]
    await add_chat_message(session_id, "user", msg)
    shield = get_shield()
    resp = await _chat_answer_with_optional_deterministic(msg, shield, history=history, session_id=session_id)
    if sess.title in ("", "New chat", "New conversation") and msg:
        await update_chat_session_title(session_id, msg[:80] + ("…" if len(msg) > 80 else ""))
    await add_chat_message(
        session_id,
        "assistant",
        resp.answer,
        grounding_data=resp.grounding_data,
        compliance_refs=resp.compliance_refs or [],
    )
    try:
        if isinstance(getattr(resp, "data", None), dict) and resp.data.get("apply_now"):
            policy_yaml = resp.data.get("policy_yaml") or ""
            if policy_yaml:
                await update_policy(PolicyUpdateRequest(policy_yaml=policy_yaml))
    except Exception as exc:
        logger.exception("policy_update_from_chat_failed exc=%s", exc)
    return chat_response_to_dict(resp)


@app.put("/api/v1/settings")
async def update_runtime_settings(payload: RuntimeSettingsPayload) -> Dict[str, Any]:
    mode = (payload.mode or "shadow").strip().lower()
    if mode not in {"shadow", "live", "approval"}:
        raise HTTPException(status_code=400, detail="mode must be one of: shadow, live, approval")
    _runtime_settings["risk_threshold"] = float(payload.risk_threshold)
    _runtime_settings["mode"] = mode
    shield = get_shield()
    shield.mode = mode
    return {
        "status": "ok",
        "risk_threshold": _runtime_settings["risk_threshold"],
        "mode": _runtime_settings["mode"],
        "note": "Actions with risk above threshold are treated as high-risk by runtime settings.",
    }


@app.get("/api/v1/chat/sessions/{session_id}/export")
async def chat_session_export(
    session_id: str,
    export_format: str = Query("markdown", alias="format"),
):
    sess = await get_chat_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await list_chat_messages(session_id)
    md = export_chat_markdown(messages)
    if export_format == "markdown":
        return Response(content=md, media_type="text/markdown; charset=utf-8")
    return {"markdown": md}


@app.post("/api/v1/negotiate/{action_id}")
async def negotiate_action(action_id: str) -> Dict[str, Any]:
    shield = get_shield()
    action = next((a for a in shield.audit_log if a.id == action_id), None)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.decision not in {"block", "shadow"}:
        return {
            "action_id": action.id,
            "status": "skipped",
            "explanation": {
                "decision": action.decision,
                "reason": "not_blocked",
                "risk_score": action.risk_score,
                "risk_factors": [],
                "human_readable": "Negotiation is intended for blocked or shadowed actions.",
            },
            "suggestions": [],
            "proposed_safe_action": {},
            "escalation_available": False,
            "retry_endpoint": "",
        }

    negotiation = await shield.negotiator.negotiate(action, None)
    await add_negotiation_log(
        action_id=action.id,
        agent_id=action.agent_id,
        status=negotiation.status,
        explanation=negotiation.explanation,
        suggestions=negotiation.suggestions,
        proposed_safe_action=negotiation.proposed_safe_action,
    )
    return negotiation.to_dict()


@app.post("/api/v1/request-approval")
async def request_approval(request: ApprovalSubmitRequest) -> Dict[str, Any]:
    _pending_approvals[request.action_id] = False
    queue_id = await enqueue_approval(
        action_id=request.action_id,
        requested_by=request.requested_by,
        reason=request.reason,
    )
    await add_approval_log(
        action_id=request.action_id,
        approved=False,
        reason=request.reason,
        approved_by=request.requested_by,
    )
    await _manager.broadcast(
        {
            "event": "approval_requested",
            "queue_id": queue_id,
            "action_id": request.action_id,
            "requested_by": request.requested_by,
            "reason": request.reason,
            "status": "pending",
        }
    )
    return {
        "status": "requested",
        "queue_id": queue_id,
        "action_id": request.action_id,
        "requested_by": request.requested_by,
    }


@app.get("/api/v1/negotiation-history")
async def negotiation_history() -> List[Dict[str, Any]]:
    shield = get_shield()
    return shield.negotiator.get_history()


@app.get("/api/v1/negotiations")
async def negotiations(limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)) -> List[Dict[str, Any]]:
    rows = await list_negotiations(limit=limit, offset=offset)
    return [
        {
            "id": row.id,
            "action_id": row.action_id,
            "agent_id": row.agent_id,
            "status": row.status,
            "explanation": row.explanation,
            "suggestions": row.suggestions,
            "proposed_safe_action": row.proposed_safe_action,
            "timestamp": row.timestamp.isoformat(),
        }
        for row in rows
    ]


@app.post("/api/v1/retry/{action_id}")
async def retry_action(action_id: str, request: RetryRequest) -> Dict[str, Any]:
    shield = get_shield()
    original = next((a for a in shield.audit_log if a.id == action_id), None)
    if original is None:
        raise HTTPException(status_code=404, detail="Original action not found")

    retried_action, negotiation = await shield.intercept_with_negotiation(
        tool_name=original.tool_name,
        arguments=request.modified_arguments,
        agent_id=original.agent_id,
    )
    _retry_chain[action_id] = {
        "original_action_id": action_id,
        "retried_action_id": retried_action.id,
        "original_decision": original.decision,
        "retried_decision": retried_action.decision,
        "modified_arguments": request.modified_arguments,
        "requested_by": request.requested_by,
    }
    await add_negotiation_log(
        action_id=retried_action.id,
        agent_id=retried_action.agent_id,
        status="retry",
        explanation={
            "decision": retried_action.decision,
            "reason": "retry_flow",
            "risk_score": retried_action.risk_score,
            "risk_factors": [],
            "human_readable": "Action retried after negotiation guidance.",
        },
        suggestions=(negotiation.suggestions if negotiation else []),
        proposed_safe_action=(negotiation.proposed_safe_action if negotiation else {}),
    )
    return {
        "status": "retried",
        "chain": _retry_chain[action_id],
        "action": {
            "id": retried_action.id,
            "decision": retried_action.decision,
            "risk_score": retried_action.risk_score,
        },
        "negotiation": negotiation.to_dict() if negotiation else None,
    }


def _filtered_audit_entries(
    shield: Agentiva,
    tool_name: Optional[str],
    decision: Optional[str],
    agent_id: Optional[str],
    min_risk: Optional[float],
):
    entries = list(shield.audit_log)
    if tool_name:
        entries = [a for a in entries if a.tool_name == tool_name]
    if decision:
        entries = [a for a in entries if a.decision == decision]
    if agent_id:
        entries = [a for a in entries if a.agent_id == agent_id]
    if min_risk is not None:
        entries = [a for a in entries if a.risk_score >= min_risk]
    return entries


@app.get("/api/v1/audit/count")
async def get_audit_count(
    tool_name: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    min_risk: Optional[float] = Query(None, ge=0, le=1),
) -> Dict[str, int]:
    shield = get_shield()
    entries = _filtered_audit_entries(shield, tool_name, decision, agent_id, min_risk)
    return {"total": len(entries)}


@app.get("/api/v1/audit", response_model=List[AuditEntry])
async def get_audit_log(
    tool_name: Optional[str] = Query(None, description="Filter by tool name"),
    decision: Optional[str] = Query(None, description="Filter by decision"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    min_risk: Optional[float] = Query(None, ge=0, le=1, description="Minimum risk score"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> List[AuditEntry]:
    shield = get_shield()
    entries = _filtered_audit_entries(shield, tool_name, decision, agent_id, min_risk)

    paged = entries[offset : offset + limit]
    return [
        AuditEntry(
            action_id=a.id,
            tool_name=a.tool_name,
            arguments=a.arguments,
            agent_id=a.agent_id,
            decision=a.decision,
            risk_score=a.risk_score,
            mode=a.mode,
            mandatory=bool((a.result or {}).get("mandatory")),
            timestamp=a.timestamp,
            phi_detection=(a.result or {}).get("phi_detection"),
        )
        for a in paged
    ]


@app.get("/api/v1/report", response_model=ShadowReport)
async def get_shadow_report() -> ShadowReport:
    shield = get_shield()
    report = shield.get_shadow_report()
    return ShadowReport(**report)


@app.post("/api/v1/approve")
async def approve_action(request: ApprovalRequest) -> Dict[str, Any]:
    if request.action_id not in _pending_approvals:
        raise HTTPException(status_code=404, detail="No pending approval for this action")
    _pending_approvals[request.action_id] = request.approved
    await add_approval_log(
        action_id=request.action_id,
        approved=request.approved,
        reason=request.reason,
        approved_by="api",
    )
    return {"status": "processed", "action_id": request.action_id, "approved": request.approved}


@app.post("/api/v1/mode/{new_mode}")
async def change_mode(new_mode: str) -> Dict[str, str]:
    if new_mode not in ("shadow", "live", "approval"):
        raise HTTPException(status_code=400, detail="Mode must be: shadow, live, or approval")
    shield = get_shield()
    shield.mode = new_mode
    logger.info("mode_changed mode=%s", new_mode)
    return {"status": "ok", "mode": new_mode}


@app.get("/api/v1/policies")
async def get_current_policy() -> Dict[str, str]:
    """Return active policy YAML from disk (same path as POST updates)."""
    policy_path = os.getenv("AGENTIVA_POLICY_PATH", "policies/default.yaml")
    if not os.path.isfile(policy_path):
        raise HTTPException(status_code=404, detail=f"Policy file not found: {policy_path}")
    with open(policy_path, encoding="utf-8") as handle:
        return {"policy_yaml": handle.read(), "policy_path": policy_path}


@app.post("/api/v1/policies")
async def update_policy(payload: PolicyUpdateRequest) -> Dict[str, str]:
    policy_yaml = payload.policy_yaml
    try:
        yaml.safe_load(policy_yaml)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}") from exc

    policy_path = os.getenv("AGENTIVA_POLICY_PATH", "policies/default.yaml")
    os.makedirs(os.path.dirname(policy_path), exist_ok=True)
    with open(policy_path, "w", encoding="utf-8") as handle:
        handle.write(policy_yaml)
    await add_policy_history(policy_yaml=policy_yaml, applied_by="api")
    # Ensure in-memory policy engine reflects the new policy immediately.
    try:
        shield = get_shield()
        shield.reload_policy(policy_path)
    except Exception:
        logger.exception("reload_policy_failed")
    return {"status": "ok", "policy_path": policy_path}


@app.get("/api/v1/metrics", response_model=MetricsResponse)
async def metrics() -> MetricsResponse:
    total_requests = int(_metrics["total_requests"])
    total_errors = int(_metrics["total_errors"])
    avg_latency = (_metrics["total_latency_ms"] / total_requests) if total_requests else 0.0
    error_rate = (total_errors / total_requests) if total_requests else 0.0
    return MetricsResponse(
        total_requests=total_requests,
        avg_latency_ms=round(avg_latency, 4),
        error_rate=round(error_rate, 4),
    )


@app.websocket("/ws/actions")
async def websocket_actions(websocket: WebSocket):
    await _manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _manager.disconnect(websocket)
    except Exception:
        _manager.disconnect(websocket)
        logger.exception("websocket_error")


def _ensure_chat_session_routes_registered() -> None:
    existing = {getattr(r, "path", "") for r in app.routes}
    required = {
        "/api/v1/chat/sessions",
        "/api/v1/chat/sessions/{session_id}/messages",
    }
    if not required.issubset(existing):
        app.include_router(chat_router)
        logger.warning("chat_fallback_router_enabled missing=%s", sorted(required - existing))


_ensure_chat_session_routes_registered()


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
