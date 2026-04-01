import asyncio
import json
import os
import uuid
from functools import wraps
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from agentiva.modes.rollback import RollbackEngine
from agentiva.modes.simulator import ActionSimulator
from agentiva.modes.negotiator import AgentNegotiator, NegotiationResponse
from agentiva.policy.smart_scorer import SmartRiskScorer
from agentiva.policy.behavior_tracker import BehaviorTracker
from agentiva.registry.agent_registry import AgentRegistry


@dataclass
class InterceptedAction:
    """One action that an agent tried to perform."""

    id: str = ""
    timestamp: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    agent_id: str = "default"
    risk_score: float = 0.0
    # External decision label for dashboards/tests. Internal queueing uses
    # ApprovalQueue.status="pending" instead (see agentiva.db.models).
    decision: str = "shadow"
    mode: str = "shadow"
    result: Optional[Dict[str, Any]] = None
    rollback_plan: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Agentiva:
    def __init__(
        self,
        mode: str = "shadow",
        policy_path: str = None,
        policy: str = None,
        *,
        risk_threshold: float = 0.7,
    ):
        self.mode = mode
        self.risk_threshold = float(risk_threshold)
        self.audit_log: List[InterceptedAction] = []
        if policy and not policy_path:
            template_path = os.path.join("policies", "templates", f"{policy}.yaml")
            policy_path = template_path if os.path.exists(template_path) else None
        self.policy_path = policy_path
        self._policy_engine = None
        self._simulator = ActionSimulator()
        self.rollback_engine = RollbackEngine()
        self._smart_scorer = SmartRiskScorer()
        self._behavior_tracker = BehaviorTracker()
        self.agent_registry = AgentRegistry()
        if policy_path:
            from agentiva.policy.engine import PolicyEngine

            self._policy_engine = PolicyEngine(policy_path)
            self._behavior_tracker.configure_baselines(getattr(self._policy_engine, "baselines", {}) or {})
            self._smart_scorer.configure_policy_context(whitelists=getattr(self._policy_engine, "whitelists", {}) or {})
        self.negotiator = AgentNegotiator(self._policy_engine, risk_scorer=self._smart_scorer)

    def _resolve_agent_role(self, agent_id: str) -> Optional[str]:
        try:
            agent = self.agent_registry.get_agent(agent_id)
            if getattr(agent, "role", None):
                return agent.role
        except Exception:
            pass
        # Fallback: if policy engine defines roles, match by agent_id.
        engine = self._policy_engine
        roles = getattr(engine, "roles", None) if engine else None
        if isinstance(roles, dict) and agent_id in roles:
            return agent_id
        return None

    def reload_policy(self, policy_path: str | None = None) -> None:
        """Reload policy YAML into the active in-memory policy engine."""
        path = policy_path or self.policy_path
        if not path:
            self._policy_engine = None
            return
        from agentiva.policy.engine import PolicyEngine
        self.policy_path = path
        self._policy_engine = PolicyEngine(path)
        self._behavior_tracker.configure_baselines(getattr(self._policy_engine, "baselines", {}) or {})
        self._smart_scorer.configure_policy_context(
            whitelists=getattr(self._policy_engine, "whitelists", {}) or {}
        )
        self.negotiator = AgentNegotiator(self._policy_engine, risk_scorer=self._smart_scorer)

    async def _intercept_impl(
        self,
        tool_name: str,
        arguments: dict,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ) -> InterceptedAction:
        ts = timestamp
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        elif isinstance(ts, datetime):
            ts = ts.astimezone(timezone.utc).isoformat()

        action = InterceptedAction(
            id=str(uuid.uuid4()),
            timestamp=ts,
            tool_name=tool_name,
            arguments=arguments or {},
            agent_id=agent_id,
            mode=self.mode,
            context=context or {},
        )
        simulation = self._simulator.simulate(
            action_id=action.id,
            tool_name=action.tool_name,
            arguments=action.arguments,
        )
        rollback_plan = self.rollback_engine.capture_state(
            action_id=action.id,
            tool_name=action.tool_name,
            original_state=action.arguments.get("original_state", {}),
            reversible=simulation.reversible,
        )
        policy_result = None
        policy_risk_floor: Optional[float] = None

        if self._policy_engine:
            policy_result = await self._policy_engine.evaluate(action)
            action.decision = policy_result.decision
            # Start from the policy score, then refine using contextual risk signals.
            action.risk_score = policy_result.risk_score
            policy_risk_floor = policy_result.risk_score
            action.result = {
                "policy_rule": policy_result.matched_rule,
                **(policy_result.metadata or {}),
            }
        else:
            self._score_risk(action)
            self._decide(action)
        self._prepare_preview(action)
        if self._policy_engine:
            # Even when policy is active, keep risk contextual.
            self._score_risk(action, override_decision=False)
            # Do not let contextual scoring understate policy-declared severity on enforce paths.
            if (
                policy_risk_floor is not None
                and policy_result is not None
                and policy_result.decision in ("block", "shadow")
            ):
                action.risk_score = max(action.risk_score, policy_risk_floor)
            if policy_result is not None:
                self._apply_runtime_policy_overlay(action, policy_result.decision)
        self._finalize_decision_from_risk_threshold(action)
        action.result = {
            **(action.result or {}),
            "simulation": asdict(simulation),
        }
        action.rollback_plan = rollback_plan.to_dict()
        self.audit_log.append(action)
        return action

    def intercept(
        self,
        tool_name: str,
        arguments: Optional[dict] = None,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ):
        if arguments is None:
            return self.intercept_custom(tool_name)
        return self._intercept_impl(
            tool_name=tool_name,
            arguments=arguments,
            agent_id=agent_id,
            context=context,
            timestamp=timestamp,
        )

    async def intercept_with_negotiation(
        self,
        tool_name: str,
        arguments: dict,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ) -> tuple[InterceptedAction, Optional[NegotiationResponse]]:
        """Intercept + if blocked, automatically return negotiation guidance."""
        action = await self._intercept_impl(
            tool_name, arguments, agent_id, context=context, timestamp=timestamp
        )
        if action.decision in ("block", "shadow"):
            negotiation = await self.negotiator.negotiate(action, None)
            return action, negotiation
        return action, None

    def intercept_with_negotiation_sync(
        self,
        tool_name: str,
        arguments: dict,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ) -> tuple[InterceptedAction, Optional[NegotiationResponse]]:
        return asyncio.run(
            self.intercept_with_negotiation(
                tool_name,
                arguments,
                agent_id=agent_id,
                context=context,
                timestamp=timestamp,
            )
        )

    def intercept_sync(
        self,
        tool_name: str,
        arguments: dict,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ) -> InterceptedAction:
        return asyncio.run(
            self._intercept_impl(
                tool_name,
                arguments,
                agent_id=agent_id,
                context=context,
                timestamp=timestamp,
            )
        )

    def protect(self, tools: List[Any]) -> List[Any]:
        try:
            from agentiva.interceptor.langchain_hook import shield_all_tools

            return shield_all_tools(tools, self)
        except Exception:
            return tools

    def protect_crewai(self, crew: Any) -> Any:
        from agentiva.interceptor.crewai_hook import shield_crewai_crew

        return shield_crewai_crew(crew, self)

    def protect_openai(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from agentiva.interceptor.openai_hook import shield_openai_tools

        return shield_openai_tools(tools, self)

    def start_mcp_proxy(self, upstream: str = "localhost:3001", port: int = 3002) -> None:
        from agentiva.interceptor.mcp_proxy import run_proxy

        run_proxy(upstream=upstream, port=port)

    def protect_shell(self):
        from agentiva.interceptor.code_agent_hook import CodeAgentInterceptor

        return CodeAgentInterceptor()

    def intercept_custom(self, tool_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(fn)
            def wrapped(*args: Any, **kwargs: Any):
                _ = self.intercept_sync(tool_name=tool_name, arguments={"args": args, "kwargs": kwargs})
                return fn(*args, **kwargs)

            return wrapped

        return decorator

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self.audit_log]

    def get_shadow_report(self) -> Dict[str, Any]:
        actions = self.audit_log
        by_tool: Dict[str, int] = {}
        by_decision: Dict[str, int] = {}
        risk_total = 0.0

        for action in actions:
            by_tool[action.tool_name] = by_tool.get(action.tool_name, 0) + 1
            by_decision[action.decision] = by_decision.get(action.decision, 0) + 1
            risk_total += action.risk_score

        total_actions = len(actions)
        avg_risk_score = (risk_total / total_actions) if total_actions else 0.0
        return {
            "total_actions": total_actions,
            "by_tool": by_tool,
            "by_decision": by_decision,
            "avg_risk_score": round(avg_risk_score, 4),
        }

    def save_audit_log(self, output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(self.get_audit_log(), handle, indent=2)

    def _score_risk(self, action: InterceptedAction, *, override_decision: bool = True) -> None:
        agent_role = self._resolve_agent_role(action.agent_id)
        parsed_ts = None
        try:
            parsed_ts = datetime.fromisoformat(action.timestamp.replace("Z", "+00:00"))
        except Exception:
            parsed_ts = None

        assessment = self._smart_scorer.score_action(
            tool_name=action.tool_name,
            arguments=action.arguments,
            agent_id=action.agent_id,
            context=getattr(action, "context", None) or {},
            agent_role=agent_role,
            timestamp=parsed_ts,
        )

        drift = self._behavior_tracker.analyze_and_record(
            agent_id=action.agent_id,
            agent_role=agent_role,
            tool_name=action.tool_name,
            arguments=action.arguments,
            risk_score=assessment.score,
            timestamp=action.timestamp,
        )

        final_score = max(0.0, min(1.0, round(assessment.score + drift.total_delta, 4)))
        # Attach behavioral/baseline signals for the chat co-pilot and PHI metadata for compliance.
        if not isinstance(action.result, dict):
            action.result = {}
        action.result.update(
            {
                "baseline_delta": drift.baseline_delta,
                "drift_delta": drift.drift_delta,
                "risk_trend_alert": drift.risk_trend_alert,
                "data_volume_alert": drift.data_volume_alert,
                "new_tool_alert": drift.new_tool_alert,
                "enumeration_alert": drift.enumeration_alert,
            }
        )
        if assessment.phi_detection is not None:
            action.result["phi_detection"] = assessment.phi_detection
        # If policy set a decision, do not override it here; only refine risk.
        if override_decision:
            action.risk_score = final_score
            # Decision is set by policy engine or _decide; keep it unchanged unless no policy engine.
            return
        action.risk_score = final_score

    def _apply_runtime_policy_overlay(self, action: InterceptedAction, policy_decision: str) -> None:
        """Apply dashboard/runtime mode and risk threshold on top of policy decisions."""
        rs = float(action.risk_score or 0.0)
        t = float(getattr(self, "risk_threshold", 0.7))
        high = rs >= t
        pd = policy_decision

        base = action.result if isinstance(action.result, dict) else {}
        ro = dict(base.get("runtime_overlay") or {})
        ro.update({"policy_decision": pd, "risk_threshold": t, "high_risk": high})
        base = {**base, "runtime_overlay": ro}
        action.result = base

        if self.mode == "shadow":
            # Shadow mode is non-enforcing, but the policy decision should remain
            # visible for compliance, debugging, and co-pilot explanations.
            # Exception: if the policy has no matching rule and the default_mode is "block",
            # keep shadow observe-only semantics.
            policy_rule = ""
            if isinstance(action.result, dict):
                policy_rule = str(action.result.get("policy_rule") or "")
            if pd == "block" and not policy_rule:
                action.decision = "shadow"
            else:
                action.decision = pd
            return

        if self.mode in {"live", "enforce"}:
            if pd == "allow" and high:
                action.decision = "block"
            return

        if self.mode in {"approval", "approve"}:
            # Approval mode signals "needs human approval" via decision="approve".
            # Queueing status is handled via /api/v1/request-approval (ApprovalQueue.status="pending").
            if pd == "block" or high:
                action.decision = "approve"
            return

    def _finalize_decision_from_risk_threshold(self, action: InterceptedAction) -> None:
        """
        Map final risk score to an external decision label.

        Default bands (tunable via `risk_threshold` on Agentiva):
        - risk >= risk_threshold (default 0.7) -> block
        - risk >= 0.3 -> shadow
        - else -> allow

        In approval mode, high risk maps to `approve` (human gate) instead of `block`.
        Mandatory policy allows are not overridden.
        """
        res = action.result if isinstance(action.result, dict) else {}
        if res.get("mandatory") is True or (res.get("metadata") or {}).get("mandatory") is True:
            return

        ro = res.get("runtime_overlay") or {}
        pd_ro = str(ro.get("policy_decision") or "")
        policy_rule = str(res.get("policy_rule") or "")

        # Approval chains can emit approve even when Agentiva runtime mode is shadow (human gate).
        if policy_rule and pd_ro == "approve":
            action.decision = "approve"
            return

        # Policy block: shadow mode + default policy (no named rule) stays observe-only.
        if pd_ro == "block":
            if self.mode == "shadow" and not policy_rule:
                action.decision = "shadow"
                return
            if self.mode in {"approval", "approve"}:
                action.decision = "approve"
                return
            action.decision = "block"
            return

        if policy_rule and pd_ro == "shadow":
            action.decision = "shadow"
            return
        if policy_rule and pd_ro == "allow":
            action.decision = "allow"
            return

        # No named rule matched: engine fell back to default_mode (often shadow). Map by risk bands.
        if not policy_rule and pd_ro == "shadow":
            rs = float(action.risk_score or 0.0)
            t = float(getattr(self, "risk_threshold", 0.7))
            low = 0.3
            if rs >= t:
                action.decision = "block"
            elif rs >= low:
                action.decision = "shadow"
            else:
                action.decision = "allow"
            return

        rs = float(action.risk_score or 0.0)
        t = float(getattr(self, "risk_threshold", 0.7))
        low = 0.3

        if self.mode in {"approval", "approve"}:
            if rs >= t:
                action.decision = "approve"
            elif rs >= low:
                action.decision = "shadow"
            else:
                action.decision = "allow"
            return

        if rs >= t:
            action.decision = "block"
        elif rs >= low:
            action.decision = "shadow"
        else:
            action.decision = "allow"

    def _decide(self, action: InterceptedAction) -> None:
        if self.mode == "shadow":
            action.decision = "shadow"
            return
        if self.mode in {"dry-run", "dry_run"}:
            action.decision = "block"
            return
        if self.mode in {"approval", "approve"}:
            action.decision = "approve"
            return
        if self.mode in {"live", "enforce"}:
            action.decision = "allow"
            return

        # Unknown mode: stay safe and non-enforcing, but never emit "pending"
        # as an external decision label.
        action.decision = "shadow"

    def _prepare_preview(self, action: InterceptedAction) -> None:
        # Preserve any policy evaluation details already stored in `action.result`
        # (e.g., `policy_rule`) so the chat co-pilot and negotiation layer
        # can reference them later.
        existing = action.result or {}
        action.result = {
            **existing,
            "status": action.decision,
            "message": f"{action.mode} preview for {action.tool_name}",
        }
        action.rollback_plan = {
            "strategy": "manual",
            "steps": [
                "Identify side effects for the action.",
                "Undo affected resources using tool-specific remediation.",
                "Verify final state matches expected baseline.",
            ],
        }
