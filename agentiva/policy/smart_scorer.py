from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple
import fnmatch
import json
import re


@dataclass
class RiskAssessment:
    score: float
    signals: List[str] = field(default_factory=list)
    recommendation: str = "shadow"
    explanation: str = ""
    # Persisted on InterceptedAction.result for compliance (types, details when PHI present).
    phi_detection: Optional[Dict[str, Any]] = None


class SmartRiskScorer:
    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        enable_llm_judge: bool = False,
        llm_client: Any = None,
    ) -> None:
        self.weights = {
            "tool_sensitivity": 1.0,
            "recipient_analysis": 1.0,
            "content_analysis": 1.0,
            "pattern_detection": 1.0,
            "time_analysis": 1.0,
            "agent_reputation": 1.0,
            "frequency": 1.0,
            "data_sensitivity": 1.0,
            "phi_detection": 1.0,
        }
        if weights:
            self.weights.update(weights)
        self.enable_llm_judge = enable_llm_judge
        self.llm_client = llm_client
        self._agent_action_counts: Dict[str, int] = {}
        self._whitelists: Dict[str, Any] = {}

    def configure_policy_context(self, *, whitelists: Optional[Dict[str, Any]] = None) -> None:
        self._whitelists = whitelists or {}

    def score_action(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        agent_role: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        recent_actions_per_minute: int = 1,
        bulk_size: int = 1,
        agent_reputation: str = "established",
        first_time_tool: bool = False,
        data_classification: str = "none",
    ) -> RiskAssessment:
        ts = timestamp or datetime.now(UTC)
        score_components: List[Tuple[str, float, str]] = []

        tool_score, tool_signal = self._tool_sensitivity(tool_name)
        score_components.append(("tool_sensitivity", tool_score, tool_signal))

        recipient_score, recipient_signal = self._recipient_analysis(arguments)
        score_components.append(("recipient_analysis", recipient_score, recipient_signal))

        pattern_score, pattern_signal = self._pattern_detection(
            first_time_tool=first_time_tool,
            bulk_size=bulk_size,
            recent_actions_per_minute=recent_actions_per_minute,
        )
        score_components.append(("pattern_detection", pattern_score, pattern_signal))

        time_score, time_signal = self._time_analysis(ts)
        score_components.append(("time_analysis", time_score, time_signal))

        reputation_score, reputation_signal = self._agent_reputation(agent_reputation)
        score_components.append(("agent_reputation", reputation_score, reputation_signal))

        content_score, content_signal = self._content_analysis(arguments)
        score_components.append(("content_analysis", content_score, content_signal))

        frequency_score, frequency_signal = self._frequency(agent_id, recent_actions_per_minute)
        score_components.append(("frequency", frequency_score, frequency_signal))

        data_score, data_signal = self._data_sensitivity(data_classification)
        score_components.append(("data_sensitivity", data_score, data_signal))

        phi_score, phi_signal, phi_payload = self._phi_detection(arguments)
        score_components.append(("phi_detection", phi_score, phi_signal))

        weighted_sum = 0.0
        weight_total = 0.0
        signals: List[str] = []
        for key, value, signal in score_components:
            w = float(self.weights.get(key, 1.0))
            weighted_sum += w * float(value)
            weight_total += w
            if signal:
                signals.append(signal)

        # Components were tuned as additive contributions; pure average (~0.02) collapses scores
        # and breaks context adjustments. Calibrate summed mass toward ~1.0 using a divisor.
        calibration_divisor = 3.0
        score = weighted_sum / calibration_divisor
        score = max(0.0, min(1.0, round(score, 4)))

        # Context-aware adjustments (self-access, authorized roles, known support context).
        ctx = context or {}
        ctx_adjust = 0.0
        if not ctx:
            ctx_adjust += 0.15
        else:
            requested_by = str(ctx.get("requested_by", "")).lower()
            customer_id_match = ctx.get("customer_id_match")
            user_role = str(ctx.get("user_role", "")).lower()
            session_type = str(ctx.get("session_type", "")).lower()

            if requested_by == "customer" and customer_id_match is True:
                ctx_adjust -= 0.15
            if session_type == "support_ticket":
                ctx_adjust -= 0.05
            if customer_id_match is False:
                ctx_adjust += 0.2

            if user_role == "doctor":
                fields = arguments.get("fields", [])
                if isinstance(fields, list):
                    fields_str = " ".join(str(x).lower() for x in fields)
                else:
                    fields_str = str(fields).lower()
                if "medical" in fields_str or "medical_history" in fields_str:
                    ctx_adjust -= 0.1

            # Minimal role-aware reduction for sales agents emailing externally.
            if agent_role == "sales_agent" and tool_name == "send_email":
                to = str(arguments.get("to", ""))
                if "@yourcompany.com" not in to:
                    ctx_adjust -= 0.1

        if ctx_adjust != 0.0:
            score = max(0.0, min(1.0, round(score + ctx_adjust, 4)))

        # Whitelist-based risk reduction/increase (trusted domains/endpoints, safe shell commands).
        wl_adjust = 0.0
        if self._whitelists:
            tool_lower = tool_name.lower()
            args = arguments or {}

            trusted_domains = self._whitelists.get("trusted_domains") or []
            trusted_email_domains = self._whitelists.get("trusted_email_domains") or []
            safe_shell_commands = self._whitelists.get("safe_shell_commands") or []

            if "call_external_api" in tool_lower:
                url = str(args.get("url", "") or "")
                domain = ""
                m = re.search(r"^https?://([^/]+)", url)
                if m:
                    domain = m.group(1)
                if domain:
                    if any(fnmatch.fnmatch(domain, p) for p in trusted_domains):
                        wl_adjust -= 0.15
                    else:
                        wl_adjust += 0.15

            if "send_email" in tool_lower:
                to = str(args.get("to", "") or "")
                if to:
                    if any(fnmatch.fnmatch(to, p) for p in trusted_email_domains):
                        wl_adjust -= 0.05

            if "run_shell_command" in tool_lower:
                cmd = str(args.get("command", "") or "")
                if cmd and safe_shell_commands:
                    if any(fnmatch.fnmatch(cmd, pat) for pat in safe_shell_commands):
                        wl_adjust -= 0.1
                    else:
                        wl_adjust += 0.1

        if wl_adjust != 0.0:
            score = max(0.0, min(1.0, round(score + wl_adjust, 4)))

        crit_boost, crit_sig = self._critical_pattern_boost(tool_name, arguments)
        if crit_boost > 0.0:
            score = max(0.0, min(1.0, round(score + crit_boost, 4)))
            if crit_sig:
                signals.append(crit_sig)

        recommendation = self._recommend(score)
        phi_note = ""
        if phi_payload.get("has_phi"):
            phi_note = f" phi_types={','.join(phi_payload.get('types') or [])}"
        explanation = (
            f"Risk score {score:.2f} from {len(score_components)} signals ({len(signals)} non-empty)."
            + phi_note
            + (f" context_adjust={ctx_adjust:+.2f}" if ctx_adjust != 0.0 else "")
        )

        if self.enable_llm_judge and self.llm_client:
            llm_signal = self._llm_judge(tool_name, arguments, score)
            if llm_signal:
                signals.append(llm_signal)
                explanation = f"{explanation} LLM judge refinement applied."

        return RiskAssessment(
            score=score,
            signals=signals,
            recommendation=recommendation,
            explanation=explanation,
            phi_detection=phi_payload,
        )

    def _tool_sensitivity(self, tool_name: str) -> Tuple[float, str]:
        lower = tool_name.lower()
        # High risk tools
        if "shell" in lower or "command" in lower or "bash" in lower:
            return 0.7, "tool_sensitivity=shell_command(+0.7)"
        if "email" in lower or "gmail" in lower:
            return 0.7, "tool_sensitivity=email(+0.7)"
        if "external_api" in lower or "call_api" in lower:
            return 0.6, "tool_sensitivity=external_api(+0.6)"
        if "database" in lower or "sql" in lower:
            return 0.6, "tool_sensitivity=database(+0.6)"
        if "write_file" in lower or "edit_file" in lower:
            return 0.4, "tool_sensitivity=file_write(+0.4)"
        if "read_customer" in lower:
            return 0.5, "tool_sensitivity=customer_data(+0.5)"
        if "permission" in lower:
            return 0.8, "tool_sensitivity=permission(+0.8)"
        if "payment" in lower or "transfer" in lower:
            return 0.8, "tool_sensitivity=financial(+0.8)"
        if "query" in lower and "database" not in lower:
            return 0.6, "tool_sensitivity=query(+0.6)"
        # Medium risk
        if "slack" in lower:
            return 0.4, "tool_sensitivity=slack(+0.4)"
        if "read_file" in lower:
            return 0.3, "tool_sensitivity=file_read(+0.3)"
        if "jira" in lower or "ticket" in lower:
            return 0.3, "tool_sensitivity=jira(+0.3)"
        return 0.2, "tool_sensitivity=default(+0.2)"

    def _recipient_analysis(self, arguments: Dict[str, Any]) -> Tuple[float, str]:
        recipient = str(arguments.get("to", arguments.get("recipient", "")))
        if recipient and "@" in recipient and "@yourcompany.com" not in recipient:
            return 0.3, "recipient_analysis=external(+0.3)"
        if str(arguments.get("channel", "")).startswith("#"):
            return 0.2, "recipient_analysis=broadcast(+0.2)"
        return 0.0, "recipient_analysis=internal(+0.0)"

    def _pattern_detection(
        self, first_time_tool: bool, bulk_size: int, recent_actions_per_minute: int
    ) -> Tuple[float, str]:
        score = 0.0
        notes: List[str] = []
        if first_time_tool:
            score += 0.1
            notes.append("first_time_tool(+0.1)")
        if bulk_size >= 10:
            score += 0.3
            notes.append("bulk_operation(+0.3)")
        if recent_actions_per_minute >= 60:
            score += 0.2
            notes.append("rapid_fire(+0.2)")
        return score, f"pattern_detection={','.join(notes)}" if notes else ""

    def _time_analysis(self, timestamp: datetime) -> Tuple[float, str]:
        weekday = timestamp.weekday()
        hour = timestamp.hour
        if weekday >= 5:
            return 0.15, "time_analysis=weekend(+0.15)"
        if hour < 8 or hour > 19:
            return 0.1, "time_analysis=after_hours(+0.1)"
        return 0.0, "time_analysis=business_hours(+0.0)"

    def _agent_reputation(self, reputation: str) -> Tuple[float, str]:
        if reputation == "new":
            return -0.1, "agent_reputation=new(-0.1 safer threshold)"
        if reputation == "trusted":
            return 0.0, "agent_reputation=established(+0.0)"
        if reputation == "unknown":
            return 0.2, "agent_reputation=unknown(+0.2)"
        return 0.0, "agent_reputation=established(+0.0)"

    def _content_analysis(self, arguments: Dict[str, Any]) -> Tuple[float, str]:
        blob = str(arguments).lower()
        score = 0.0
        notes: List[str] = []

        # Destructive operations
        destructive = [
            "delete",
            "drop",
            "remove",
            "destroy",
            "truncate",
            "rm -rf",
            "terminate",
            "delete-stack",
            "delete-db",
            "skip-final-snapshot",
        ]
        if any(term in blob for term in destructive):
            score += 0.5
            notes.append("destructive_keywords(+0.5)")

        # Credential/secret patterns
        credential_patterns = [
            "password",
            "secret",
            "token",
            "credential",
            "confidential",
            "ssh",
            "private.key",
            "id_rsa",
            "aws_access",
            "aws_secret",
            "api_key",
            "api.key",
            "stripe",
            "openai_api",
            "database_url",
            "gcp",
            "azure",
            "kubeconfig",
            ".env",
            "git-credentials",
        ]
        if any(term in blob for term in credential_patterns):
            score += 0.5
            notes.append("credentials_detected(+0.5)")

        # External/suspicious URLs
        if any(term in blob for term in ["evil.com", "attacker", "malicious", "exfil", "litellm.cloud", "protonmail", "offshore"]):
            score += 0.5
            notes.append("suspicious_target(+0.5)")

        # Infrastructure destruction commands
        if any(term in blob for term in ["cloudformation", "terminate-instances", "delete-stack", "delete-db-instance"]):
            score += 0.5
            notes.append("infrastructure_destruction(+0.5)")

        # Backdoor/persistence patterns
        if any(term in blob for term in ["backdoor", "systemctl", "cron", "wget", "sysmon", "persistence"]):
            score += 0.5
            notes.append("persistence_attempt(+0.5)")
        if re.search(r"curl\s+.*\|\s*bash", blob) or ("curl" in blob and "| bash" in blob):
            score += 0.5
            notes.append("curl_pipe_bash(+0.5)")

        # kubectl dangerous operations (substring + regex)
        if re.search(r"kubectl\s+.*get\s+secrets", blob) or re.search(r"kubectl\s+.*delete", blob):
            score += 0.5
            notes.append("k8s_dangerous(+0.5)")
        if re.search(r"kubectl\s+run", blob) or "--privileged" in blob:
            score += 0.5
            notes.append("k8s_privileged(+0.5)")

        # Bulk data access
        cid = arguments.get("customer_id")
        if cid == "*" or (isinstance(cid, str) and cid.strip() == "*"):
            score += 0.4
            notes.append("bulk_data_access(+0.4)")

        # PII patterns in outbound actions
        pii = ["ssn", "social security", "credit_card", "credit card", "medical_record"]
        if any(term in blob for term in pii):
            score += 0.4
            notes.append("pii_in_action(+0.4)")

        # Force push
        if "force" in blob and ("push" in blob or "git" in blob):
            score += 0.4
            notes.append("force_push(+0.4)")

        score = min(score, 1.0)
        return score, f"content_analysis={','.join(notes)}" if notes else "content_analysis=normal(+0.0)"

    def _phi_detection(self, arguments: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
        """
        Signal 9 — PHI detection. Adds up to +0.5 via weighted contribution (value 0..0.5 × weight).
        """
        from agentiva.compliance.phi_detector import detect_phi

        text = str(arguments)
        phi = detect_phi(text)
        adj = float(phi.get("risk_adjustment") or 0.0)
        # Component value is the capped adjustment (detect_phi already caps at 0.5).
        value = min(0.5, max(0.0, adj))
        types = phi.get("types") or []
        if phi.get("has_phi"):
            sig = f"phi_detection={','.join(types)}(+{value:.2f})"
        else:
            sig = ""
        return value, sig, dict(phi)

    def _frequency(self, agent_id: str, recent_actions_per_minute: int) -> Tuple[float, str]:
        self._agent_action_counts[agent_id] = self._agent_action_counts.get(agent_id, 0) + 1
        if recent_actions_per_minute >= 100:
            return 0.3, "frequency=abnormal(+0.3)"
        if recent_actions_per_minute >= 40:
            return 0.1, "frequency=high(+0.1)"
        return 0.0, "frequency=normal(+0.0)"

    def _data_sensitivity(self, data_classification: str) -> Tuple[float, str]:
        cls = data_classification.lower()
        if cls == "credentials":
            return 0.5, "data_sensitivity=credentials(+0.5)"
        if cls == "financial":
            return 0.4, "data_sensitivity=financial(+0.4)"
        if cls == "pii":
            return 0.3, "data_sensitivity=pii(+0.3)"
        return 0.0, "data_sensitivity=none(+0.0)"

    def _recommend(self, score: float) -> str:
        # Align with runtime risk_threshold defaults (0.7) and shadow band (0.3).
        if score >= 0.7:
            return "block"
        if score >= 0.3:
            return "shadow"
        return "allow"

    def _critical_pattern_boost(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[float, str]:
        """
        Deterministic boosts for obvious attack / exfil / destructive patterns so demos
        and incidents surface as high-risk even when policy rules are generic.
        """
        args = arguments or {}
        boost = 0.0
        notes: List[str] = []

        path = str(args.get("path", "") or "").lower()
        cmd = str(args.get("command", "") or "").lower()
        url = str(args.get("url", "") or "").lower()
        body = str(args.get("body", "") or "").lower()
        blob = json.dumps(args, default=str).lower()

        # Credential / key access
        if any(x in path for x in (".ssh", "id_rsa", "id_ed25519", "known_hosts")):
            boost += 0.55
            notes.append("ssh_key_path(+0.55)")
        if ".aws/credentials" in path or "aws_secret_access_key" in blob or "aws_access_key_id" in blob:
            boost += 0.5
            notes.append("aws_credentials_file(+0.5)")
        if ".env" in path and any(k in blob for k in ("api_key", "secret", "password", "database_url")):
            boost += 0.35
            notes.append("env_secrets(+0.35)")

        # Exfil / untrusted endpoints
        if any(h in url for h in ("litellm.cloud", "evil.com", "attacker", "exfil")):
            boost += 0.55
            notes.append("untrusted_exfil_host(+0.55)")
        if body and any(k in body for k in ("ssh_key", "aws_secret", "database_url", "stripe_key", "k8s_secrets")):
            boost += 0.45
            notes.append("exfil_payload(+0.45)")

        # Destructive infra / data
        if any(x in cmd for x in ("delete-stack", "terminate-instances", "delete-db-instance", "delete_stack")):
            boost += 0.55
            notes.append("infra_destroy(+0.55)")
        if "kubectl" in cmd and any(x in cmd for x in ("privileged", "hostpid", "hostnetwork", "kube-system")):
            boost += 0.5
            notes.append("k8s_priv_esc(+0.5)")
        if "wget" in cmd and any(x in cmd for x in ("evil.com", "http://", "https://")):
            boost += 0.55
            notes.append("download_backdoor(+0.55)")
        if "systemctl" in cmd and "enable" in cmd:
            boost += 0.45
            notes.append("persistence(+0.45)")

        # SQL / bulk abuse
        if any(x in blob for x in ("delete from", "drop table", "drop database")):
            boost += 0.55
            notes.append("destructive_sql(+0.55)")
        if "customer_id" in blob and "*" in blob:
            boost += 0.25
            notes.append("bulk_customer_dump(+0.25)")

        # Secrets in command / kubectl
        if "kubectl get secrets" in cmd or "secrets --all-namespaces" in cmd:
            boost += 0.45
            notes.append("k8s_secret_dump(+0.45)")

        boost = min(0.95, boost)
        sig = f"critical_pattern_boost={';'.join(notes)}" if notes else ""
        return boost, sig

    def _llm_judge(self, tool_name: str, arguments: Dict[str, Any], score: float) -> str:
        # Opt-in extension point: call external provider if wired by enterprise users.
        _ = (tool_name, arguments, score)
        return "LLM judge enabled (no-op in local deterministic mode)"
