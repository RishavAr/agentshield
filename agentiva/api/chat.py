"""
Shield Chat — answer questions about agent activity from the in-memory audit log.

Uses pattern matching and simple analytics by default; optional OpenRouter LLM
for complex queries.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agentiva.interceptor.core import Agentiva

# Phrases that trigger the one-off allow (shadow/block → narrow allow) flow.
ALLOW_ONE_PHRASES: tuple[str, ...] = (
    "allow just this",
    "allow this one",
    "allow this specific",
    "shadow to allow",
    "convert shadow to allow",
    "make this allowed",
    "let this through",
    "allow for shadow",
    "allow shadow",
    "shadow allow",
    "one off allow",
    "one-off allow",
    "exception for shadow",
    "unblock last",
    "unblock this",
)


def is_allow_one_user_message(q: str) -> bool:
    m = (q or "").lower()
    if any(p in m for p in ALLOW_ONE_PHRASES):
        return True
    # Also treat "allow <tool>" as an allow-one request, since the UI often lists tool
    # names (e.g. "allow read_customer_data") and users naturally type that.
    if re.match(r"^\s*allow\b", m) and "allowlist" not in m and "allow list" not in m:
        return True
    return False


@dataclass
class ChatResponse:
    answer: str
    data: Any
    follow_up_suggestions: List[str]
    mode: str = "basic"  # "basic" (pattern matching) or "ai-powered" (OpenRouter)
    grounding_data: Optional[Dict[str, Any]] = None
    compliance_refs: Optional[List[str]] = None


class ShieldChat:
    """Chat with Agentiva about your agents' activity."""

    def __init__(self, shield: Agentiva):
        self.shield = shield
        self._last_grounding: Optional[Dict[str, Any]] = None

    async def ask(self, question: str) -> ChatResponse:
        q = (question or "").strip().lower()
        if not q:
            return ChatResponse(
                answer="Ask me anything about intercepted actions, blocks, risk, or agents.",
                data={},
                follow_up_suggestions=[
                    "Give me a session summary",
                    "What are the riskiest actions?",
                    "Why were actions blocked?",
                ],
            )

        # Deterministic DB-grounded replies are applied in HTTP handlers (`server.py`)
        # so unit tests can call `ShieldChat.ask` with in-memory audit only.

        # Persisted audit evidence (action_logs) for every turn — RAG grounding.
        try:
            from agentiva.compliance.audit_grounding import fetch_audit_grounding

            self._last_grounding = await fetch_audit_grounding(question)
        except Exception:
            self._last_grounding = None

        # Pick an intent, then (optionally) prepend proactive high-block guidance.
        if self._is_disable_all_security(q):
            resp = self._refuse_disable_all_security()
        elif self._is_allow_one_request(q):
            resp = await self._allow_one_flow_async(question)
        elif self._is_policy_wizard_request(q) or self._is_policy_wizard_active():
            resp = self._policy_wizard(question)
        elif self._is_policy_apply_request(q):
            resp = self._help_unblock_apply_flow(question)
        elif self._is_help_unblock_request(q):
            resp = self._help_unblock(question)
        elif self._is_compliance_question(q):
            resp = self._compliance_answer(question)
        elif re.search(
            r"\b(hi|hello|hey|yo|greetings|good\s+(morning|afternoon|evening))\b", q
        ):
            resp = ChatResponse(
                answer=(
                    "Hey! I'm your Agentiva security co-pilot. I can analyze your agent activity, "
                    "check compliance, and help you tune policies. What would you like to know?"
                ),
                data={},
                follow_up_suggestions=[
                    "Session overview",
                    "Any security issues?",
                    "Check HIPAA compliance",
                ],
            )
        elif "timeline" in q:
            resp = self._show_timeline()
        elif any(w in q for w in ["why blocked", "why block", "why was", "reason"]):
            resp = await self._explain_blocks(question)
        elif any(
            w in q
            for w in [
                "what was blocked",
                "blocked actions",
                "show blocked",
                "blocked action",
                "blocks",
                "blocked",
            ]
        ):
            resp = await self._explain_blocks(question)
        elif any(w in q for w in ["what went wrong", "problems", "issues", "incidents"]):
            resp = self._summarize_issues()
        elif any(
            w in q
            for w in [
                "risky",
                "riskiest",
                "most risky",
                "highest risk",
                "dangerous",
                "suspicious",
                "high risk",
            ]
        ):
            resp = self._show_risky_actions()
        elif any(w in q for w in ["explain the #1 risk", "explain risk", "explain the risk"]):
            resp = self._show_risky_actions()
        elif any(
            w in q
            for w in [
                "summary",
                "overview",
                "status",
                "report",
                "export report",
                "export",
                "what happened",
                "whats going on",
                "what's going on",
            ]
        ):
            resp = self._generate_summary()
        elif any(w in q for w in ["agent", "who", "which agent"]):
            resp = self._agent_analysis(question)
        elif any(w in q for w in ["policy", "change", "what if", "would happen"]):
            resp = self._policy_simulation(question)
        elif any(
            w in q
            for w in [
                "recommend",
                "suggestion",
                "improve",
                "fix",
                "apply changes",
                "apply these changes",
            ]
        ):
            resp = self._recommendations()
        else:
            resp = self._smart_response(question)

        proactive = self._maybe_proactive_block_rate_message(q)
        if proactive and not self._should_skip_proactive_for_question(q):
            suggestions = list(resp.follow_up_suggestions)
            if "Help me unblock" not in suggestions:
                suggestions = ["Help me unblock", *suggestions]
            resp = ChatResponse(
                answer=f"{proactive}\n\n{resp.answer}",
                data=resp.data,
                follow_up_suggestions=suggestions,
                mode=resp.mode,
            )
        return resp

    @staticmethod
    def _action_path_from_args(arguments: Any) -> str:
        if not isinstance(arguments, dict):
            return ""
        for key in ("path", "file", "filepath"):
            v = arguments.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    @staticmethod
    def _describe_blocked_tool(tool: str, args: Any) -> str:
        tl = (tool or "").lower()
        if isinstance(args, dict) and args.get("credentials_found"):
            return "hardcoded credentials"
        if tl == "read_customer_data":
            return "exposes PII (SSN/credit card)"
        if tl == "run_shell_command":
            return "dangerous shell patterns"
        if tl == "install_package":
            return "compromised or risky dependency"
        return f"`{tool}` blocked by policy"

    def _get_block_reason(self, action: Any) -> str:
        res = getattr(action, "result", None) or {}
        rule = res.get("policy_rule") if isinstance(res, dict) else None
        if isinstance(res, dict):
            # Prefer high-signal, user-facing reasons from policy rules (geo, mandatory, etc).
            if res.get("reason"):
                return str(res.get("reason"))
        if rule:
            return f"Policy rule: {rule}"
        args = getattr(action, "arguments", {}) or {}
        tool = getattr(action, "tool_name", "")
        if tool == "send_email" and isinstance(args, dict):
            to = str(args.get("to", ""))
            if "@yourcompany.com" not in to:
                return "External recipient / policy block on email"
        if isinstance(args, dict) and any(
            x in str(args).upper() for x in ("DROP", "DELETE", "TRUNCATE")
        ):
            return "Destructive or sensitive data operation blocked by policy"
        return "Blocked by Agentiva policy evaluation"

    def _is_disable_all_security(self, q: str) -> bool:
        return any(
            phrase in q
            for phrase in [
                "disable all blocks",
                "disable blocks",
                "turn off security",
                "turn off safeguards",
                "allow everything",
                "allow all",
                "disable security",
                "turn off security",
                "off security",
                "turn off protection",
                "disable protection",
            ]
        )

    def _refuse_disable_all_security(self) -> ChatResponse:
        return ChatResponse(
            answer=(
                "I strongly recommend against disabling all blocks. Here's what would happen:\n"
                "- Your agent could email customer SSNs to external addresses\n"
                "- Database DELETE queries would execute without review\n"
                "- Unauthorized refunds could process automatically\n\n"
                "Instead, let me help you find the specific rules that are too strict.\n"
                "Ask me: 'which blocks are false positives?' and I'll analyze each one."
            ),
            data={},
            follow_up_suggestions=[
                "Which blocks are false positives?",
                "Help me unblock",
                "Show blocked actions",
            ],
        )

    def _is_policy_wizard_request(self, q: str) -> bool:
        q_lower = q.lower()
        return any(
            phrase in q_lower
            for phrase in [
                "help me tune policies",
                "policy wizard",
                "policy tuning assistant",
                "help me tune policy",
                "copilot update policy",
                "co-pilot update policy",
                "change policy for me",
                "edit my policy",
                "add a policy exception",
                "add an allow rule",
                "selective allow",
                "selective shadow",
            ]
        )

    def _is_help_unblock_request(self, q: str) -> bool:
        q_lower = q.lower()
        return any(
            phrase in q_lower
            for phrase in [
                "help me unblock",
                "keeps getting blocked",
                "too many blocks",
                "how to fix blocks",
                "agent can't do anything",
                "agent cant do anything",
                "too restrictive",
                "stuck and blocked",
                "blocked nonstop",
                "blocking continuously",
                "always blocked",
                "false positive",
                "allow this action",
                "stop blocking",
            ]
        )

    def _is_allow_one_request(self, q: str) -> bool:
        return is_allow_one_user_message(q)

    async def _allow_one_flow_async(self, question: str) -> ChatResponse:
        """
        Generate a narrow allow exception for the *most recent* shadow/block action.

        This is the "shadow -> allow for a specific case" co-pilot path. It works by
        proposing a highly specific policy rule and (on confirm) returning apply_now=True
        so the HTTP layer applies it via /api/v1/policies.
        """
        q = (question or "").strip().lower()
        # Optional: user can specify which tool they want to allow.
        # Examples: "allow read_customer_data", "allow update_database", "allow `send_email`".
        tool_hints = {
            "send_email": ("send_email", "send email", "email"),
            "read_customer_data": ("read_customer_data", "read customer data", "read customer"),
            "update_database": ("update_database", "update database", "database", "sql"),
            "create_ticket": ("create_ticket", "create ticket", "ticket", "jira"),
            "call_external_api": ("call_external_api", "external api", "call api"),
            "run_shell_command": ("run_shell_command", "shell", "run shell", "command"),
            "send_slack_message": ("send_slack_message", "slack", "send slack"),
        }
        requested_tool: str | None = None
        for tool_name, hints in tool_hints.items():
            if any(h in q for h in hints):
                requested_tool = tool_name
                break

        log = getattr(self.shield, "audit_log", []) or []
        target = next(
            (
                a
                for a in reversed(log)
                if getattr(a, "decision", "") in {"shadow", "block"}
                and (requested_tool is None or str(getattr(a, "tool_name", "") or "") == requested_tool)
            ),
            None,
        )
        if target is None:
            try:
                from agentiva.db.database import list_actions

                rows = await list_actions(limit=200)
                for row in rows:
                    if getattr(row, "decision", "") in ("shadow", "block"):
                        if requested_tool is not None and str(getattr(row, "tool_name", "") or "") != requested_tool:
                            continue
                        target = row
                        break
            except Exception:
                target = None
        if target is None:
            return ChatResponse(
                answer=(
                    "I don't see any recent shadowed or blocked actions in memory or the audit database. "
                    "Run the agent action once (so it is logged), then ask again — e.g. **allow read_customer_data** — and reply **Confirm**."
                ),
                data={},
                follow_up_suggestions=["Show blocked actions", "Session overview"],
            )

        tool = str(getattr(target, "tool_name", "") or "")
        args = getattr(target, "arguments", {}) or {}

        if not isinstance(args, dict):
            return ChatResponse(
                answer=(
                    f"I can do one-off allow exceptions for specific tools when I can extract a stable argument value. "
                    f"The most recent flagged action was `{tool}`, but its arguments weren't a dict. "
                    "Ask me to create a broader policy exception instead: 'add a policy exception'."
                ),
                data={},
                follow_up_suggestions=["Add a policy exception", "Help me unblock", "Show blocked actions"],
            )

        additions: List[Dict[str, Any]] = []
        short_desc = ""

        if tool == "send_email":
            to_addr = str(args.get("to") or "").strip()
            if not to_addr:
                return ChatResponse(
                    answer="I couldn't extract the `to` address from the last `send_email` action.",
                    data={},
                    follow_up_suggestions=["Show blocked actions", "Help me unblock"],
                )
            short_desc = f"recipient `{to_addr}`"
            additions = [
                {
                    "name": "allow_exception_specific_email_recipient",
                    "tool": "send_email",
                    "condition": {"field": "arguments.to", "operator": "equals", "value": to_addr},
                    "action": "allow",
                    "risk_score": 0.15,
                    "insert_before": ["block_external_email", "block_personal_email_domains"],
                }
            ]

        elif tool == "read_customer_data":
            fields = str(args.get("fields") or "").strip()
            if not fields:
                return ChatResponse(
                    answer="I couldn't extract `arguments.fields` from the last `read_customer_data` action.",
                    data={},
                    follow_up_suggestions=["Show shadowed actions", "Help me unblock"],
                )
            short_desc = f"fields `{fields}`"
            additions = [
                {
                    "name": "allow_exception_specific_customer_fields",
                    "tool": "read_customer_data",
                    "condition": {"field": "arguments.fields", "operator": "equals", "value": fields},
                    "action": "allow",
                    "risk_score": 0.25,
                }
            ]

        elif tool == "update_database":
            query = str(args.get("query") or "").strip()
            if not query:
                return ChatResponse(
                    answer="I couldn't extract `arguments.query` from the last `update_database` action.",
                    data={},
                    follow_up_suggestions=["Show shadowed actions", "Help me unblock"],
                )
            # Keep it narrow: allow *only* this exact query string.
            short_desc = "this exact SQL query"
            additions = [
                {
                    "name": "allow_exception_specific_sql_query",
                    "tool": "update_database",
                    "condition": {"field": "arguments.query", "operator": "equals", "value": query},
                    "action": "allow",
                    "risk_score": 0.25,
                    "insert_before": ["block_destructive_sql_drop", "block_destructive_sql_delete"],
                }
            ]

        elif tool == "create_ticket":
            title = str(args.get("title") or "").strip()
            if not title:
                return ChatResponse(
                    answer="I couldn't extract `arguments.title` from the last `create_ticket` action.",
                    data={},
                    follow_up_suggestions=["Show shadowed actions", "Help me unblock"],
                )
            short_desc = f"title `{title}`"
            additions = [
                {
                    "name": "allow_exception_specific_ticket_title",
                    "tool": "create_ticket",
                    "condition": {"field": "arguments.title", "operator": "equals", "value": title},
                    "action": "allow",
                    "risk_score": 0.25,
                }
            ]

        if not additions:
            return ChatResponse(
                answer=(
                    f"I can do one-off allow exceptions for `send_email`, `read_customer_data`, `update_database`, and `create_ticket` right now. "
                    f"The most recent flagged action was `{tool}`. "
                    "Ask me to create a broader policy exception instead: 'add a policy exception'."
                ),
                data={},
                follow_up_suggestions=["Add a policy exception", "Help me unblock", "Show blocked actions"],
            )

        snippet = self._format_policy_additions_snippet(additions)

        is_confirm = "confirm" in q or q.strip() in {"yes", "yes confirm", "yes, confirm"}
        if not is_confirm:
            return ChatResponse(
                answer=(
                    f"I can allow **just this exact case** for `{tool}` ({short_desc}).\n\n"
                    "This is a narrow policy exception (not a global allow). Confirm?\n\n"
                    "Add this rule to your policy.yaml:\n\n"
                    f"{snippet}"
                ),
                data={"apply_now": False, "policy_yaml": None},
                follow_up_suggestions=["Confirm", "Cancel"],
            )

        policy_yaml = self._build_policy_yaml_with_additions(additions)
        return ChatResponse(
            answer=(
                f"Done — I added a narrow allow exception for `{tool}` ({short_desc}). "
                "Try the action again; it should now return `allow`."
            ),
            data={"apply_now": True, "policy_yaml": policy_yaml},
            follow_up_suggestions=["Show blocked actions", "Show the timeline", "Session overview"],
        )

    def _is_policy_apply_request(self, q: str) -> bool:
        return any(
            phrase in q
            for phrase in [
                "apply the fix",
                "update policy",
                "yes apply",
                "apply these changes",
                "apply changes",
                "apply policy",
                "apply this policy",
                "confirm",
            ]
        )

    def _session_stats(self) -> Dict[str, Any]:
        log = getattr(self.shield, "audit_log", []) or []
        blocked = [a for a in log if getattr(a, "decision", "") == "block"]
        total = len(log)
        return {
            "total": total,
            "blocked": len(blocked),
            "block_rate": (len(blocked) / total) if total else 0.0,
        }

    def _is_compliance_question(self, q: str) -> bool:
        return any(
            k in q
            for k in (
                "hipaa",
                "soc 2",
                "soc2",
                "pci",
                "pci-dss",
                "compliance",
                "gdpr",
                "regulatory",
                "audit controls",
                "45 cfr",
            )
        )

    def _compliance_answer(self, question: str) -> ChatResponse:
        from agentiva.compliance.knowledge_base import get_compliance_context

        ctx = get_compliance_context(question)
        stats = self._session_stats()
        g = self._last_grounding or {}
        extra = ""
        bl = g.get("baseline") or {}
        tot_rows = bl.get("totals") or []
        if tot_rows and isinstance(tot_rows, list):
            for row in tot_rows:
                if isinstance(row, dict) and row.get("total") is not None:
                    extra = f"\n\nFrom the persisted action_logs extract: {row.get('total')} total rows."
                    break
        excerpt = ctx[:6500] if len(ctx) > 6500 else ctx
        answer = (
            f"Session (in-memory): {stats['total']} actions, {stats['blocked']} blocked. "
            f"Citations below reference real regulatory text; pair with your audit exports for evidence.{extra}\n\n"
            f"---\n\n{excerpt}"
        )
        return ChatResponse(
            answer=answer,
            data={},
            follow_up_suggestions=[
                "Session overview",
                "Show blocked actions",
                "Give me recommendations",
            ],
        )

    def _should_skip_proactive_for_question(self, q: str) -> bool:
        return (
            self._is_help_unblock_request(q)
            or self._is_policy_wizard_request(q)
            or self._is_policy_wizard_active()
            or self._is_policy_apply_request(q)
            or self._is_disable_all_security(q)
        )

    def _is_policy_wizard_active(self) -> bool:
        state = getattr(self.shield, "_policy_wizard_state", None)
        if not isinstance(state, dict):
            return False
        try:
            step = int(state.get("step", 0))
        except Exception:
            return False
        return step in (1, 2, 3, 4, 5)

    def _maybe_proactive_block_rate_message(self, q: str) -> str | None:
        stats = self._session_stats()
        if stats["total"] <= 0:
            return None
        if stats["block_rate"] <= 0.4:
            return None
        pct = int(round(stats["block_rate"] * 100))
        return (
            f"I notice {pct}% of your agent's actions are being blocked. "
            "This might mean your policies are too strict for your use case. "
            "Would you like me to analyze which blocks are false positives and suggest fixes?"
        )

    def _get_policy_engine(self):
        return getattr(self.shield, "_policy_engine", None)

    def _find_policy_rule(self, rule_name: str) -> Dict[str, Any] | None:
        engine = self._get_policy_engine()
        if not engine:
            return None
        policy = getattr(engine, "policy", None)
        rules = (policy or {}).get("rules", []) if isinstance(policy, dict) else []
        for r in rules:
            if r.get("name") == rule_name:
                return r
        return None

    def _rule_condition_summary(self, rule: Dict[str, Any]) -> str:
        cond = rule.get("condition") or {}
        field = cond.get("field", "arguments.<unknown>")
        op = cond.get("operator", "equals")
        value = cond.get("value")
        return f"{field} {op} {value}"

    def _compute_unblock_policy_additions(self, blocked_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Returns YAML rule dicts to insert into policies/default.yaml.
        Kept intentionally small/deterministic for UX and testability.
        """
        additions: List[Dict[str, Any]] = []
        seen_names = set()

        for g in blocked_groups:
            tool = g["tool_name"]
            rule_name = g["policy_rule"]
            if g["category"] != "too_strict":
                continue

            if tool == "send_email" and rule_name == "block_external_email":
                name = "allow_customer_replies"
                if name in seen_names:
                    continue
                # Match the UX example exactly for support replies.
                additions.append(
                    {
                        "name": name,
                        "tool": "send_email",
                        "condition": {
                            "field": "arguments.subject",
                            "operator": "contains",
                            "value": "Re:",
                        },
                        "action": "allow",
                        "risk_score": 0.2,
                        "insert_before": ["block_external_email"],
                    }
                )
                seen_names.add(name)

            if tool == "read_customer_data" and rule_name and "ssn" in rule_name:
                name = "allow_support_data_read"
                if name in seen_names:
                    continue
                additions.append(
                    {
                        "name": name,
                        "tool": "read_customer_data",
                        "condition": {
                            "field": "arguments.fields",
                            "operator": "not_contains",
                            "value": "ssn",
                        },
                        "action": "allow",
                        "risk_score": 0.3,
                        "insert_before": ["block_read_ssn_export"],
                    }
                )
                seen_names.add(name)

        return additions

    def _format_policy_additions_snippet(self, additions: List[Dict[str, Any]]) -> str:
        # Render additions as plain YAML blocks (no fenced code blocks).
        # Keep quoting consistent with the UX example.
        blocks: List[str] = []
        for r in additions:
            name = r["name"]
            tool = r["tool"]
            cond = r["condition"]
            field = cond["field"]
            op = cond["operator"]
            value = cond["value"]
            action = r["action"]
            risk_score = r["risk_score"]
            blocks.append(
                "\n".join(
                    [
                        f"- name: {name}",
                        f"  tool: {tool}",
                        f"  condition:",
                        f"    field: {field}",
                        f"    operator: {op}",
                        f"    value: '{value}'",
                        f"  action: {action}",
                        f"  risk_score: {risk_score}",
                    ]
                )
            )
        return "\n\n".join(blocks).strip()

    def _build_policy_yaml_with_additions(self, additions: List[Dict[str, Any]]) -> str:
        import yaml

        policy_path = os.getenv("AGENTIVA_POLICY_PATH", "policies/default.yaml")
        with open(policy_path, encoding="utf-8") as handle:
            base = yaml.safe_load(handle)
        if not isinstance(base, dict):
            raise ValueError("Invalid policy YAML root")
        rules = base.get("rules", []) or []
        if not isinstance(rules, list):
            rules = []

        # Insert each addition before the first matching rule name.
        for add in additions:
            insert_before = add.get("insert_before") or []
            idx = None
            for name in insert_before:
                for i, r in enumerate(rules):
                    if r.get("name") == name:
                        idx = i
                        break
                if idx is not None:
                    break
            # Strip internal insert_before key before dumping.
            add_rule = {k: v for k, v in add.items() if k != "insert_before"}
            if idx is None:
                rules.append(add_rule)
            else:
                rules.insert(idx, add_rule)

        base["rules"] = rules
        return yaml.safe_dump(base, sort_keys=False)

    def _help_unblock(self, question: str) -> ChatResponse:
        log = getattr(self.shield, "audit_log", []) or []
        blocked = [a for a in log if getattr(a, "decision", "") == "block"]
        if not blocked:
            return ChatResponse(
                answer="I don't see blocked actions in the audit log yet. Run the demo or intercept a few actions and try again.",
                data={},
                follow_up_suggestions=["Show blocked actions", "Give me a session summary", "Run the demo script"],
            )

        # Group by (tool, policy_rule) so we can explain “which policy rule blocked it”.
        groups_map: Dict[tuple[str, str], List[Any]] = {}
        for a in blocked:
            res = getattr(a, "result", None) or {}
            rule_name = res.get("policy_rule") if isinstance(res, dict) else None
            if not rule_name:
                rule_name = "unknown_rule"
            key = (getattr(a, "tool_name", "unknown_tool"), str(rule_name))
            groups_map.setdefault(key, []).append(a)

        grouped = [
            {
                "tool_name": tool,
                "policy_rule": rule,
                "count": len(actions),
                "sample": max(actions, key=lambda x: getattr(x, "risk_score", 0.0) or 0.0),
            }
            for (tool, rule), actions in groups_map.items()
        ]
        grouped = sorted(grouped, key=lambda g: g["count"], reverse=True)[:5]

        # Categorize blocks into correct vs possibly too strict.
        # Deterministic heuristic: higher risk score implies “genuinely dangerous”.
        correct_groups: List[Dict[str, Any]] = []
        too_strict_groups: List[Dict[str, Any]] = []
        for g in grouped:
            sample = g["sample"]
            risk = float(getattr(sample, "risk_score", 0.0) or 0.0)
            category = "correct" if risk >= 0.7 else "too_strict"
            g["risk_score"] = risk
            g["category"] = category
            if category == "correct":
                correct_groups.append(g)
            else:
                too_strict_groups.append(g)

        correct_count = sum(g["count"] for g in correct_groups)
        too_strict_count = sum(g["count"] for g in too_strict_groups)

        additions = self._compute_unblock_policy_additions(too_strict_groups)
        additions_snippet = self._format_policy_additions_snippet(additions) if additions else ""

        lines: List[str] = []
        lines.append(f"Your agent was blocked {len(blocked)} times this session. Here's the breakdown:")
        lines.append("")

        # Copilot awareness: role-based policies need an assigned agent role.
        engine = getattr(self.shield, "_policy_engine", None)
        roles = getattr(engine, "roles", {}) if engine else {}
        agent_id = getattr(blocked[0], "agent_id", "") if blocked else ""
        if isinstance(roles, dict) and roles and agent_id not in roles:
            lines.append(
                "Your agent doesn't have a role configured. Set it as 'sales_agent' to automatically allow external emails."
            )
            lines.append("")

        # Baseline/drift awareness to help users understand "why now?"
        baseline_blocks = [
            a
            for a in blocked
            if isinstance(getattr(a, "result", None), dict)
            and float((a.result or {}).get("baseline_delta", 0.0) or 0.0) < 0
        ]
        any_drift = any(
            isinstance(getattr(a, "result", None), dict)
            and (
                (a.result or {}).get("risk_trend_alert")
                or (a.result or {}).get("data_volume_alert")
                or (a.result or {}).get("new_tool_alert")
                or (a.result or {}).get("enumeration_alert")
            )
            for a in blocked
        )

        if baseline_blocks:
            lines.append(
                "This action looks normal for your agent's baseline, but a global rule is blocking it. "
                "I recommend adding it to the whitelist."
            )
            lines.append("")
        if any_drift:
            lines.append(
                "I also detected behavioral drift in the last hour (patterns changed enough to trigger extra scrutiny)."
            )
            lines.append("")

        if correct_groups:
            lines.append(f"✅ {correct_count} blocks were correct (genuinely dangerous):")
            for g in correct_groups:
                rule = self._find_policy_rule(g["policy_rule"])
                cond_summary = self._rule_condition_summary(rule) if rule else "matched a block rule"
                lines.append(
                    f"- {g['count']}x `{g['tool_name']}` blocked by policy `{g['policy_rule']}` "
                    f"(risk: {g['risk_score']:.2f}) because {cond_summary}"
                )
                # Give a short “why it was high” marker for UX.
                if rule and "risk_score" in rule:
                    lines[-1] += f" (rule risk: {float(rule.get('risk_score', 0.0)):.2f})"
        else:
            lines.append("✅ No clearly dangerous blocks detected in the top items.")

        lines.append("")

        if too_strict_groups:
            lines.append(f"⚠️ {too_strict_count} blocks might be too strict:")
            for g in too_strict_groups:
                rule = self._find_policy_rule(g["policy_rule"])
                cond_summary = self._rule_condition_summary(rule) if rule else "matched a block rule"
                lines.append(
                    f"- {g['count']}x `{g['tool_name']}` blocked by policy `{g['policy_rule']}` "
                    f"(risk: {g['risk_score']:.2f}) because {cond_summary}"
                )
                if rule and "risk_score" in rule:
                    lines[-1] += f" (rule risk: {float(rule.get('risk_score', 0.0)):.2f})"
        else:
            lines.append("⚠️ No possibly-too-strict blocks detected in the top items.")

        if additions_snippet:
            lines.append("")
            lines.append(f"Recommended fix for the {too_strict_count} false positives:")
            lines.append("")
            lines.append("Add these rules to your policy.yaml:")
            lines.append("")
            lines.append(additions_snippet)

        lines.append("")
        lines.append("Want me to apply these changes?")

        return ChatResponse(
            answer="\n".join(lines),
            data={"unblock_policy_additions": additions},
            follow_up_suggestions=[
                "Apply these changes",
                "Which blocks are false positives?",
                "Show the timeline",
            ],
        )

    def _help_unblock_apply_flow(self, question: str) -> ChatResponse:
        q = (question or "").strip().lower()

        # Always recompute additions from the current audit log.
        log = getattr(self.shield, "audit_log", []) or []
        blocked = [a for a in log if getattr(a, "decision", "") == "block"]

        if not blocked:
            return ChatResponse(
                answer="I don't see blocked actions in the audit log yet, so I can't generate a targeted unblock policy change.",
                data={},
                follow_up_suggestions=["Show blocked actions", "Give me a session summary"],
            )

        # Build top groups (same grouping logic as _help_unblock).
        groups_map: Dict[tuple[str, str], List[Any]] = {}
        for a in blocked:
            res = getattr(a, "result", None) or {}
            rule_name = res.get("policy_rule") if isinstance(res, dict) else None
            if not rule_name:
                rule_name = "unknown_rule"
            key = (getattr(a, "tool_name", "unknown_tool"), str(rule_name))
            groups_map.setdefault(key, []).append(a)

        grouped = [
            {
                "tool_name": tool,
                "policy_rule": rule,
                "count": len(actions),
                "sample": max(actions, key=lambda x: getattr(x, "risk_score", 0.0) or 0.0),
            }
            for (tool, rule), actions in groups_map.items()
        ]
        grouped = sorted(grouped, key=lambda g: g["count"], reverse=True)[:5]

        too_strict_groups: List[Dict[str, Any]] = []
        for g in grouped:
            sample = g["sample"]
            risk = float(getattr(sample, "risk_score", 0.0) or 0.0)
            if risk < 0.7:
                g["risk_score"] = risk
                g["category"] = "too_strict"
                too_strict_groups.append(g)

        additions = self._compute_unblock_policy_additions(too_strict_groups)
        additions_snippet = self._format_policy_additions_snippet(additions) if additions else ""
        if not additions_snippet:
            return ChatResponse(
                answer="I couldn't identify any blocks that look plausibly too strict in the top items. If you want, I can still review specific tool blocks by asking: 'which blocks are false positives?'.",
                data={},
                follow_up_suggestions=["Which blocks are false positives?", "Show blocked actions", "Show the timeline"],
            )

        is_confirm = "confirm" in q or q.strip() == "yes" or "yes, confirm" in q
        if not is_confirm:
            allow_summary = "customer email replies and support data reads (excluding SSN)"
            return ChatResponse(
                answer=(
                    "This will allow "
                    + allow_summary
                    + ". Confirm?\n\nAdd these rules to your policy.yaml:\n\n"
                    + additions_snippet
                ),
                data={"apply_policy_yaml": None, "apply_now": False},
                follow_up_suggestions=["Confirm", "Cancel"],
            )

        # Apply immediately: server will call the policy update API using policy_yaml.
        policy_yaml = self._build_policy_yaml_with_additions(additions)
        return ChatResponse(
            answer=(
                "Policy updated. Your agent should now be able to handle customer replies and read non-sensitive customer data. "
                "I'll monitor the next 50 actions and let you know if anything looks wrong."
            ),
            data={"apply_now": True, "policy_yaml": policy_yaml},
            follow_up_suggestions=["Show blocked actions", "Which tools are riskiest?", "Show the timeline"],
        )

    def _policy_wizard(self, question: str) -> ChatResponse:
        q = (question or "").strip().lower()
        start = self._is_policy_wizard_request(q)
        state = getattr(self.shield, "_policy_wizard_state", None)
        if start or not isinstance(state, dict):
            state = {"step": 1, "responses": {}, "generated_policy_yaml": None}
            setattr(self.shield, "_policy_wizard_state", state)

        step = int(state.get("step", 1))

        def parse_agent_type() -> str | None:
            if any(k in q for k in ["customer support", "support", "helpdesk", "support ticket"]):
                return "customer support"
            if any(k in q for k in ["sales", "lead", "crm"]):
                return "sales"
            if any(k in q for k in ["devops", "dev ops", "code", "ci/cd", "deploy"]):
                return "devops"
            if "other" in q:
                return "other"
            return None

        def parse_tools() -> List[str]:
            tools: List[str] = []
            if "email" in q or "send_email" in q:
                tools.append("send_email")
            if "slack" in q or "send_slack_message" in q:
                tools.append("send_slack_message")
            if "jira" in q or "create_jira_ticket" in q:
                tools.append("create_jira_ticket")
            if "database" in q or "db" in q or "sql" in q:
                tools.append("read_customer_data")
            if "read_customer_data" in q:
                tools.append("read_customer_data")
            if "payments" in q or "refund" in q or "transfer_funds" in q:
                tools.append("transfer_funds")
            if not tools:
                tools = []
            return tools

        def parse_recipients() -> str | None:
            if "internal" in q:
                return "internal"
            if "customer" in q or "support" in q:
                return "customers"
            if "external" in q or "partner" in q:
                return "external partners"
            return None

        def parse_risk_tol() -> str | None:
            if "strict" in q:
                return "strict"
            if "permissive" in q:
                return "permissive"
            if "balanced" in q:
                return "balanced"
            return None

        # Step 1
        if step == 1:
            agent_type = parse_agent_type()
            if not agent_type:
                return ChatResponse(
                    answer=(
                        "Policy Tuning Assistant\n\n"
                        "Step 1: What does your agent do? (customer support / sales / devops / other)"
                    ),
                    data={},
                    follow_up_suggestions=["customer support", "sales", "devops", "other"],
                )
            state["responses"]["agent_type"] = agent_type
            state["step"] = 2
            return ChatResponse(
                answer=(
                    "Step 2: Which tools does it use? (email, slack, jira, database, payments)\n"
                    "Reply with something like: `email + jira + database`."
                ),
                data={},
                follow_up_suggestions=["email + jira + database", "email + slack", "devops tools", "payments"],
            )

        # Step 2
        if step == 2:
            tools = parse_tools()
            if not tools:
                return ChatResponse(
                    answer="Step 2: Which tools does it use? (email, slack, jira, database, payments)",
                    data={},
                    follow_up_suggestions=["email + jira + database", "email + slack", "devops tools", "payments"],
                )
            state["responses"]["tools"] = tools
            state["step"] = 3
            return ChatResponse(
                answer="Step 3: Who are the recipients? (internal only / customers / external partners)",
                data={},
                follow_up_suggestions=["internal only", "customers", "external partners"],
            )

        # Step 3
        if step == 3:
            recipients = parse_recipients()
            if not recipients:
                return ChatResponse(
                    answer="Step 3: Who are the recipients? (internal only / customers / external partners)",
                    data={},
                    follow_up_suggestions=["internal only", "customers", "external partners"],
                )
            state["responses"]["recipients"] = recipients
            state["step"] = 4
            return ChatResponse(
                answer="Step 4: What's your risk tolerance? (strict / balanced / permissive)",
                data={},
                follow_up_suggestions=["strict", "balanced", "permissive"],
            )

        # Step 4
        if step == 4:
            risk_tol = parse_risk_tol()
            if not risk_tol:
                return ChatResponse(
                    answer="Step 4: What's your risk tolerance? (strict / balanced / permissive)",
                    data={},
                    follow_up_suggestions=["strict", "balanced", "permissive"],
                )
            state["responses"]["risk_tolerance"] = risk_tol
            policy_yaml = self._generate_policy_from_wizard_state(state)
            state["generated_policy_yaml"] = policy_yaml
            state["step"] = 5
            return ChatResponse(
                answer=(
                    "Policy Wizard generated a custom policy.yaml for your use case.\n\n"
                    f"{policy_yaml}\n\n"
                    "Want me to apply this policy?"
                ),
                data={},
                follow_up_suggestions=["Apply policy", "Review risky rules", "Show blocked actions"],
            )

        # Step 5 (policy ready)
        generated = state.get("generated_policy_yaml") or ""
        if not generated:
            state["step"] = 4
            return ChatResponse(
                answer="I lost the generated policy. Step 4: What's your risk tolerance? (strict / balanced / permissive)",
                data={},
                follow_up_suggestions=["strict", "balanced", "permissive"],
            )

        if "confirm" in q:
            return ChatResponse(
                answer=(
                    "Policy updated. I'll monitor the next 50 actions and let you know if anything looks wrong."
                ),
                data={"apply_now": True, "policy_yaml": generated},
                follow_up_suggestions=["Show blocked actions", "Show risky actions", "Show the timeline"],
            )

        if any(
            phrase in q
            for phrase in [
                "apply policy",
                "apply this policy",
                "update policy",
                "yes apply",
                "apply these changes",
            ]
        ):
            return ChatResponse(
                answer="This will apply your custom policy.yaml. Confirm?",
                data={"apply_now": False, "policy_yaml": generated},
                follow_up_suggestions=["Confirm", "Cancel"],
            )

        return ChatResponse(
            answer="I already generated a custom policy.yaml. Want to apply it now?",
            data={},
            follow_up_suggestions=["Apply policy", "Review risky rules", "Show blocked actions"],
        )

    def _generate_policy_from_wizard_state(self, state: Dict[str, Any]) -> str:
        import yaml

        agent_type = state.get("responses", {}).get("agent_type", "other")
        tools = state.get("responses", {}).get("tools", [])
        recipients = state.get("responses", {}).get("recipients", "internal")
        risk_tol = state.get("responses", {}).get("risk_tolerance", "balanced")

        # Start from a safe minimal baseline: keep high-severity blocks.
        rules: List[Dict[str, Any]] = [
            {
                "name": "block_sql_drop",
                "tool": "update_database",
                "condition": {"field": "arguments.query", "operator": "contains", "value": "DROP"},
                "action": "block",
                "risk_score": 0.97,
            },
            {
                "name": "block_shell_rm_rf_root",
                "tool": "run_shell_command",
                "condition": {"field": "arguments.command", "operator": "contains", "value": "rm -rf /"},
                "action": "block",
                "risk_score": 0.99,
            },
            {
                "name": "demo_outcome_allow",
                "tool": "*",
                "condition": {"field": "arguments.outcome_tier", "operator": "equals", "value": "allow"},
                "action": "allow",
                "risk_score": 0.11,
            },
        ]

        # Add allow rules guided by tolerance and recipients.
        # This is intentionally conservative: it only “opens doors” where it matches your answers.
        if "send_email" in tools:
            if recipients in {"internal", "customers"} and risk_tol in {"strict", "balanced"}:
                rules.append(
                    {
                        "name": "allow_internal_email",
                        "tool": "send_email",
                        "condition": {"field": "arguments.to", "operator": "contains", "value": "@yourcompany.com"},
                        "action": "allow",
                        "risk_score": 0.2,
                    }
                )
            if recipients in {"customers"} and risk_tol in {"balanced", "permissive"}:
                rules.append(
                    {
                        "name": "allow_customer_replies",
                        "tool": "send_email",
                        "condition": {"field": "arguments.subject", "operator": "contains", "value": "Re:"},
                        "action": "allow",
                        "risk_score": 0.2 if risk_tol != "permissive" else 0.25,
                    }
                )

        if "read_customer_data" in tools and recipients in {"customers", "external partners"}:
            rules.append(
                {
                    "name": "allow_support_data_read",
                    "tool": "read_customer_data",
                    "condition": {"field": "arguments.fields", "operator": "not_contains", "value": "ssn"},
                    "action": "allow",
                    "risk_score": 0.3,
                }
            )

        if agent_type == "devops" and "run_shell_command" in tools:
            rules.append(
                {
                    "name": "allow_safe_shell_commands",
                    "tool": "run_shell_command",
                    "condition": {"field": "arguments.command", "operator": "contains", "value": "ls"},
                    "action": "allow",
                    "risk_score": 0.25,
                }
            )

        policy = {
            "version": 1,
            "default_mode": "shadow",
            "rules": rules,
        }
        return yaml.safe_dump(policy, sort_keys=False).strip()

    async def _explain_blocks(self, question: str) -> ChatResponse:
        from agentiva.db.database import list_actions

        db_rows: List[Any] = []
        try:
            db_rows = await list_actions(decision="block", limit=15)
        except Exception:
            db_rows = []

        log = getattr(self.shield, "audit_log", []) or []
        blocked = [a for a in log if a.decision == "block"]
        recent = blocked[-5:] if blocked else []

        explanations: List[Dict[str, Any]] = []
        for action in recent:
            explanations.append(
                {
                    "tool": action.tool_name,
                    "arguments": action.arguments,
                    "risk_score": action.risk_score,
                    "reason": self._get_block_reason(action),
                    "timestamp": action.timestamp,
                }
            )

        lines: List[str] = []
        if blocked:
            first = blocked[-1]
            aid = getattr(first, "agent_id", "unknown")
            args0 = getattr(first, "arguments", {}) or {}
            if not isinstance(args0, dict):
                args0 = {}
            path0 = self._action_path_from_args(args0)
            desc0 = self._describe_blocked_tool(str(getattr(first, "tool_name", "")), args0)
            n_same = len([a for a in blocked if getattr(a, "agent_id", "") == aid])
            cred_shadow = len(
                [
                    a
                    for a in log
                    if getattr(a, "decision", "") == "shadow"
                    and isinstance(getattr(a, "arguments", None), dict)
                    and (getattr(a, "arguments") or {}).get("credentials_found")
                    and getattr(a, "agent_id", "") == aid
                ]
            )
            lead = (
                f"{aid} had {n_same} blocked action(s) in session: "
                f"{(path0 + ' ') if path0 else ''}{desc0} at risk {float(getattr(first, 'risk_score', 0) or 0):.2f}."
            )
            if cred_shadow:
                lead += f" {cred_shadow} warning(s) for hardcoded credentials in config files."
            lines.append(lead)
            lines.append("")

        if db_rows:
            lines.append(
                f"Persisted audit log (action_logs): {len(db_rows)} recent blocked row(s) (up to 15 shown)."
            )
            for row in db_rows:
                ts = getattr(row, "timestamp", None)
                ts_s = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                args = getattr(row, "arguments", None) or {}
                path = self._action_path_from_args(args if isinstance(args, dict) else {})
                path_note = f" · `{path}`" if path else ""
                lines.append(
                    f"- `{row.tool_name}` risk: {float(row.risk_score):.2f} · agent `{row.agent_id}`{path_note} · at {ts_s}"
                )
            lines.append("")

        lines.append(
            f"In-memory session: {len(blocked)} blocked action(s). Most recent (up to 5):"
        )
        if explanations:
            lines.append("")
        for e in explanations:
            ap = self._action_path_from_args(
                e.get("arguments") if isinstance(e.get("arguments"), dict) else {}
            )
            path_e = f" · `{ap}`" if ap else ""
            lines.append(
                f"- `{e['tool']}` risk: {float(e['risk_score']):.2f} · {e['reason']}{path_e} · at {e['timestamp']}"
            )
        if not explanations and not db_rows:
            lines = [
                "No blocked actions found in the persisted audit log or the current in-memory session yet. "
                "Run intercepts or `python demo/real_agent.py --mode protected`, then ask again."
            ]

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Show blocked actions",
                "Which tools are riskiest?",
                "Explain the #1 risk",
            ],
        )

    def _summarize_issues(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No actions recorded yet — run intercepts or the live demo to populate data.",
                data={"total_blocked": 0, "high_risk_count": 0, "top_blocked_tools": []},
                follow_up_suggestions=["Give me a session summary", "Run the demo script"],
            )

        blocked = [a for a in log if a.decision == "block"]
        high_risk = [a for a in log if a.risk_score > 0.7]

        by_tool: Dict[str, int] = {}
        for a in blocked:
            by_tool[a.tool_name] = by_tool.get(a.tool_name, 0) + 1

        top_issues = [
            {"tool": k, "count": v}
            for k, v in sorted(by_tool.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        most_dangerous = max(log, key=lambda a: a.risk_score)

        lines = [
            f"In this session, {len(blocked)} action(s) were blocked and {len(high_risk)} were high risk (risk > 0.70)."
        ]

        if top_issues:
            lines.append("")
            lines.append("Top blocked tools:")
            for row in top_issues:
                lines.append(f"- `{row['tool']}`: {row['count']}")

        lines.append("")
        lines.append(
            f"Most dangerous attempted action: `{most_dangerous.tool_name}` risk: {most_dangerous.risk_score:.2f} by agent `{most_dangerous.agent_id}`."
        )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Show blocked actions",
                "Which tools are riskiest?",
                "Export report",
            ],
        )

    def _show_risky_actions(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No actions yet — nothing to rank by risk.",
                data=[],
                follow_up_suggestions=["Give me a session summary"],
            )

        risky = sorted(log, key=lambda a: a.risk_score, reverse=True)[:10]
        rows = [
            {
                "tool": a.tool_name,
                "risk": a.risk_score,
                "decision": a.decision,
                "args": a.arguments,
                "agent": a.agent_id,
            }
            for a in risky
        ]

        lines = ["Top riskiest actions in the current audit log (by risk score):"]
        lines.append("")
        for idx, a in enumerate(risky, 1):
            lines.append(
                f"{idx}. `{a.tool_name}` risk: {a.risk_score:.2f} · decision: {a.decision} · agent: `{a.agent_id}`"
            )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Explain the #1 risk",
                "What policy would fix this?",
                "Show the timeline",
            ],
        )

    def _show_timeline(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No actions yet — intercept actions or run the live demo first to build a timeline.",
                data={},
                follow_up_suggestions=[
                    "Give me a session overview",
                    "Show blocked actions",
                    "Show risky actions",
                ],
            )

        # Timestamps are typically ISO strings; lexicographic sort works for chronological ordering.
        recent = sorted(log, key=lambda a: str(getattr(a, "timestamp", "")), reverse=True)[:15]

        lines = ["Session timeline (most recent first):", ""]
        for a in recent:
            ts = getattr(a, "timestamp", "")
            lines.append(
                f"- {ts} `{a.tool_name}` decision: {a.decision} · risk: {a.risk_score:.2f} · agent: `{a.agent_id}`"
            )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Explain the #1 risk",
                "What policy would fix this?",
                "Show me the riskiest actions",
            ],
        )

    def _agent_analysis(self, question: str) -> ChatResponse:
        log = self.shield.audit_log
        agents: Dict[str, Dict[str, Any]] = {}
        for a in log:
            aid = a.agent_id
            if aid not in agents:
                agents[aid] = {"total": 0, "blocked": 0, "risks": []}
            agents[aid]["total"] += 1
            agents[aid]["risks"].append(a.risk_score)
            if a.decision == "block":
                agents[aid]["blocked"] += 1

        for _aid, data in agents.items():
            rs = data["risks"]
            data["avg_risk"] = round(sum(rs) / len(rs), 4) if rs else 0.0
            del data["risks"]

        sorted_rows = [
            {"agent_id": aid, **stats}
            for aid, stats in sorted(
                agents.items(), key=lambda x: x[1]["avg_risk"], reverse=True
            )
        ]

        top = sorted_rows[:5]
        lines = [f"Tracking {len(agents)} agent(s) in the audit log."]
        lines.append("")
        lines.append("Top agents by average risk:")
        for row in top:
            lines.append(
                f"- `{row['agent_id']}`: avg risk {row['avg_risk']:.2f}, blocked {row.get('blocked', 0)}"
            )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Deactivate the riskiest agent",
                "Show me the riskiest actions from the top agent",
                "Recommendations to improve security",
            ],
        )

    def _recommendations(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No activity yet — recommendations will be more useful after actions are intercepted.",
                data=["Run your agents through Agentiva or the live demo first."],
                follow_up_suggestions=["Give me a session summary"],
            )

        blocked = [a for a in log if a.decision == "block"]
        shadowed = [a for a in log if a.decision == "shadow"]

        recommendations: List[str] = []

        if len(blocked) > len(log) * 0.3:
            recommendations.append(
                "Over 30% of actions are blocked. Review whether policies are too strict "
                "or agents need better tool-use training."
            )

        external_blocks = [
            a
            for a in blocked
            if "external" in str(a.arguments).lower()
            or "@" in str((a.arguments or {}).get("to", ""))
        ]
        if external_blocks:
            recommendations.append(
                f"{len(external_blocks)} external communication attempt(s) blocked. "
                "Consider an allowlist for trusted external contacts."
            )

        destructive = [
            a
            for a in blocked
            if any(
                w in str(a.arguments).lower()
                for w in ("delete", "drop", "remove", "truncate")
            )
        ]
        if destructive:
            recommendations.append(
                f"{len(destructive)} destructive pattern(s) caught. Keep destructive-action policies strict."
            )

        if len(shadowed) > len(log) * 0.5:
            recommendations.append(
                "Many actions are in shadow mode — good for observation before you tighten to block/allow."
            )

        if not recommendations:
            recommendations.append(
                "Activity looks within normal parameters for this session."
            )

        lines = ["Here are my security recommendations based on current audit log activity:"]
        lines.append("")
        for r in recommendations:
            lines.append(f"- {r}")

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Apply these changes",
                "Show me the data behind this",
                "Compare to last session",
            ],
        )

    def _generate_summary(self) -> ChatResponse:
        log = self.shield.audit_log
        g = self._last_grounding or {}
        baseline = (g.get("baseline") or {}).get("totals_by_decision") or []
        persisted_total = None
        if baseline:
            try:
                persisted_total = sum(int(r.get("n", 0) or 0) for r in baseline if isinstance(r, dict))
            except (TypeError, ValueError):
                persisted_total = None

        if not log and not persisted_total:
            return ChatResponse(
                answer=(
                    "I don't have enough data for that yet — the in-memory session has no actions and "
                    "the persisted `action_logs` table is empty. Run intercepts or the live demo, then ask again."
                ),
                data={},
                follow_up_suggestions=["Run the demo to see actions", "Send a test intercept"],
                grounding_data=g or None,
            )

        blocked = [a for a in log if a.decision == "block"]
        shadowed = [a for a in log if a.decision == "shadow"]
        allowed = [a for a in log if a.decision == "allow"]
        avg_risk = sum(a.risk_score for a in log) / len(log) if log else 0.0
        highest = max(log, key=lambda a: a.risk_score) if log else None

        lines = [
            "Summary (in-memory session plus persisted `action_logs` where queried):",
            f"- Session actions (this process): {len(log)}",
        ]
        if persisted_total is not None:
            lines.append(f"- Persisted audit rows (database): {persisted_total} total decisions in action_logs")
        if baseline:
            lines.append(f"- By decision (DB): {baseline!s}"[:500])
        if log:
            lines.extend(
                [
                    f"- Blocked (session): {len(blocked)}",
                    f"- Shadowed (session): {len(shadowed)}",
                    f"- Allowed (session): {len(allowed)}",
                    f"- Average risk (session): {avg_risk:.2f}",
                ]
            )
        if highest:
            lines.append(
                f"- Highest risk (session): `{highest.tool_name}` at {highest.risk_score:.2f} (agent `{highest.agent_id}`)"
            )
            lines.append(f"- Time span (session): {log[0].timestamp} → {log[-1].timestamp}")

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Show blocked actions",
                "Which tools are riskiest?",
                "Export report",
            ],
            grounding_data=g or None,
        )

    def _policy_simulation(self, question: str) -> ChatResponse:
        engine = getattr(self.shield, "_policy_engine", None)
        policy_loaded = engine is not None
        hints = []
        if policy_loaded:
            hints.append(
                "Policies are loaded from YAML; first matching rule wins for each action."
            )
        else:
            hints.append(
                "No YAML policy engine attached — decisions use smart scoring / mode defaults."
            )

        q = question.lower()
        if "email" in q and "external" in q:
            hints.append(
                "Typical pattern: external `send_email` may hit `block_external_email` if not @yourcompany.com."
            )

        return ChatResponse(
            answer="Policy simulation (rule-based): I can’t run hypothetical tool calls without arguments, "
            "but here’s how Agentiva reasons about policy today:",
            data={},
            follow_up_suggestions=[
                "Show blocked actions",
                "What policy is triggering these blocks?",
                "Give me recommendations",
            ],
        )

    def _smart_response(self, question: str) -> ChatResponse:
        return ChatResponse(
            answer=(
                "I can help with session overviews, security analysis, and compliance checks — no external API key needed. "
                f'For "{question[:80]}...", try: '
                "“session overview”, “what was blocked?”, or “HIPAA-aligned check”"
            ),
            data={},
            follow_up_suggestions=[
                "Session overview",
                "What was blocked?",
                "HIPAA-aligned check",
            ],
            grounding_data=self._last_grounding,
        )


class SmartChat:
    """LLM-powered chat for premium users via OpenRouter."""

    def __init__(self, shield: Agentiva, api_key: Optional[str] = None):
        self.shield = shield
        self.basic_chat = ShieldChat(shield)
        raw = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
        self.api_key = (raw or "").strip()
        self.has_llm = bool(self.api_key)

    async def ask(self, question: str) -> ChatResponse:
        basic_response = await self.basic_chat.ask(question)
        q = (question or "").strip().lower()
        grounding = getattr(self.basic_chat, "_last_grounding", None) or {}
        critical = self.basic_chat._is_help_unblock_request(q) or self.basic_chat._is_policy_apply_request(
            q
        ) or self.basic_chat._is_disable_all_security(q) or self.basic_chat._is_policy_wizard_request(
            q
        )
        if critical:
            return ChatResponse(
                answer=basic_response.answer,
                data=basic_response.data,
                follow_up_suggestions=basic_response.follow_up_suggestions,
                mode=basic_response.mode,
                grounding_data=grounding or None,
                compliance_refs=basic_response.compliance_refs,
            )
        if not self.has_llm:
            return ChatResponse(
                answer=basic_response.answer,
                data=basic_response.data,
                follow_up_suggestions=basic_response.follow_up_suggestions,
                mode=basic_response.mode,
                grounding_data=grounding or None,
                compliance_refs=basic_response.compliance_refs,
            )
        context = self._get_context()
        return await self._ask_llm(question, context, basic_response, grounding)

    def _needs_llm(self, question: str) -> bool:
        q = (question or "").lower()
        complex_indicators = [
            "compare",
            "predict",
            "write a policy",
            "what if",
            "should i",
            "is it safe",
            "analyze",
            "trend",
            "recommend changes",
            "generate report",
            "explain in detail",
            "help me understand",
            "what does this mean",
        ]
        return any(ind in q for ind in complex_indicators)

    def _get_context(self) -> Dict[str, Any]:
        log = self.shield.audit_log if hasattr(self.shield, "audit_log") else []
        return {
            "total": len(log),
            "blocked": len([a for a in log if a.decision == "block"]),
            "shadowed": len([a for a in log if a.decision == "shadow"]),
            "allowed": len([a for a in log if a.decision in ("allow", "live")]),
            "avg_risk": round(sum(a.risk_score for a in log) / max(len(log), 1), 2),
            "recent": [
                {
                    "tool": a.tool_name,
                    "decision": a.decision,
                    "risk": a.risk_score,
                    "args": a.arguments,
                    "agent": a.agent_id,
                }
                for a in log[-30:]
            ],
        }

    async def _ask_llm(
        self,
        question: str,
        context: Dict[str, Any],
        basic_data: ChatResponse,
        grounding: Dict[str, Any],
    ) -> ChatResponse:
        import httpx

        from agentiva.compliance.audit_grounding import (
            format_grounding_for_llm,
            grounding_covers_numbers,
        )

        ql = (question or "").lower()
        if any(k in ql for k in ["summary", "overview", "status", "report"]):
            suggestions = ["Show blocked actions", "Which tools are riskiest?", "Export report"]
        elif any(k in ql for k in ["risky", "dangerous", "suspicious", "high risk"]):
            suggestions = [
                "Explain the #1 risk",
                "What policy would fix this?",
                "Show the timeline",
            ]
        elif any(k in ql for k in ["recommend", "suggestion", "improve", "fix"]):
            suggestions = [
                "Apply these changes",
                "Show me the data behind this",
                "Compare to last session",
            ]
        elif any(k in ql for k in ["hi", "hello", "hey", "greetings"]):
            suggestions = [
                "Give me a session overview",
                "Any incidents today?",
                "How are my agents performing?",
            ]
        elif any(k in ql for k in ["why blocked", "why block", "reason", "blocked"]):
            suggestions = [
                "Show blocked actions",
                "Which tools are riskiest?",
                "Explain the #1 risk",
            ]
        else:
            suggestions = [
                "Give me a session overview",
                "Show risky actions",
                "Any recommendations?",
            ]

        evidence_blob = format_grounding_for_llm(grounding)
        compliance_refs: List[str] = []
        for line in (grounding.get("compliance_text") or "").splitlines():
            if "§" in line or "CFR" in line or "CC" in line or "PCI" in line:
                compliance_refs.append(line.strip()[:200])
        compliance_refs = list(dict.fromkeys(compliance_refs))[:15]

        system_prompt = (
            "You are Agentiva's security co-pilot. You analyze real audit data from AI agent deployments.\n\n"
            "RULES:\n"
            "1. ONLY answer based on the audit data and compliance rules provided below.\n"
            "2. Include specific numbers, action IDs, and timestamps from the data when present.\n"
            "3. When citing compliance rules, include the exact section number (e.g., \"45 CFR § 164.312(a)(1)\").\n"
            "4. If you don't have data to answer a question, say \"I don't have enough data for that yet.\"\n"
            "5. Never speculate or make up numbers.\n"
            "6. Be conversational — a smart security analyst, not a database.\n"
            "7. End with 1-2 specific follow-up questions the user could ask next.\n"
            "8. Never output JSON, code fences, or raw hints.\n\n"
            "In-memory session snapshot (for context only; prefer persisted DB evidence below):\n"
            f"- Total actions intercepted: {context['total']}\n"
            f"- Blocked: {context['blocked']}\n"
            f"- Shadowed: {context['shadowed']}\n"
            f"- Allowed: {context['allowed']}\n"
            f"- Average risk score: {context['avg_risk']}\n"
            f"- Recent actions: {json.dumps(context['recent'][:20], default=str)}\n\n"
            "PERSISTED AUDIT DATABASE EVIDENCE (authoritative — action_logs):\n"
            f"{evidence_blob[:28000]}\n"
        )
        user_message = question

        model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://agentiva.dev",
                        "X-Title": "Agentiva",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": 1024,
                    },
                    timeout=30.0,
                )
            if response.status_code == 200:
                data = response.json()
                answer = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if answer:
                    # strip accidental code fences / JSON
                    answer = answer.strip()
                    if answer.startswith("```"):
                        answer = re.sub(r"^```[a-z]*\s*", "", answer)
                        answer = re.sub(r"\s*```$", "", answer)
                    if not grounding_covers_numbers(answer, evidence_blob):
                        answer = (
                            "I don't have enough data to confirm every number in that answer against "
                            "the current `action_logs` extract. Here's a conservative summary instead:\n\n"
                            + answer[:1200]
                        )
                    return ChatResponse(
                        answer=answer,
                        data={},
                        follow_up_suggestions=suggestions,
                        mode="ai-powered",
                        grounding_data=grounding,
                        compliance_refs=compliance_refs or None,
                    )
        except Exception:
            pass
        return ChatResponse(
            answer=basic_data.answer,
            data=basic_data.data,
            follow_up_suggestions=basic_data.follow_up_suggestions,
            mode=basic_data.mode,
            grounding_data=grounding,
            compliance_refs=basic_data.compliance_refs,
        )


def chat_response_to_dict(resp: ChatResponse) -> Dict[str, Any]:
    # API contract: natural language + suggestions; also `content`/`role` for clients that expect chat shape.
    return {
        "answer": resp.answer,
        "suggestions": resp.follow_up_suggestions,
        "role": "assistant",
        "content": resp.answer,
    }
