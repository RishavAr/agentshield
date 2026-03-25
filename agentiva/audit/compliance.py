from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional


class ComplianceExporter:
    """Export audit data in formats compliance teams need."""

    def __init__(self, actions: List[Any], approvals: Optional[Dict[str, bool]] = None):
        self.actions = actions
        self.approvals = approvals or {}

    def _filter_by_date(self, start_date: str, end_date: str) -> List[Any]:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        result: List[Any] = []
        for action in self.actions:
            ts = datetime.fromisoformat(action.timestamp.replace("Z", "+00:00"))
            if start <= ts <= end:
                result.append(action)
        return result

    def export_soc2_report(self, start_date: str, end_date: str) -> dict:
        actions = self._filter_by_date(start_date, end_date)
        violations = [a for a in actions if a.decision == "block"]
        risk_bins = Counter("high" if a.risk_score >= 0.7 else "medium" if a.risk_score >= 0.3 else "low" for a in actions)
        return {
            "period": {"start": start_date, "end": end_date},
            "total_actions": len(actions),
            "policy_violations": [
                {"action_id": a.id, "tool_name": a.tool_name, "timestamp": a.timestamp}
                for a in violations
            ],
            "approvals": self.approvals,
            "risk_distribution": dict(risk_bins),
            "human_in_the_loop_evidence": {
                "approval_endpoint": "/api/v1/request-approval",
                "blocked_actions_count": len(violations),
            },
        }

    def export_gdpr_data_access_log(self, data_subject_id: str) -> dict:
        touched = [
            a
            for a in self.actions
            if data_subject_id in str(a.arguments)
        ]
        return {
            "data_subject_id": data_subject_id,
            "access_events": [
                {
                    "action_id": a.id,
                    "tool_name": a.tool_name,
                    "agent_id": a.agent_id,
                    "timestamp": a.timestamp,
                }
                for a in touched
            ],
        }

    def export_eu_ai_act_transparency(self) -> dict:
        by_agent = Counter(a.agent_id for a in self.actions)
        by_decision = Counter(a.decision for a in self.actions)
        return {
            "deployed_agents": list(by_agent.keys()),
            "decisions_summary": dict(by_decision),
            "human_oversight": {
                "approval_workflow": True,
                "negotiation_workflow": True,
            },
            "risk_classification_per_agent": {
                agent_id: ("high" if count > 100 else "medium" if count > 20 else "low")
                for agent_id, count in by_agent.items()
            },
        }

    def export_csv(self, filters: dict) -> str:
        rows = self._apply_filters(filters)
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "timestamp", "tool_name", "agent_id", "decision", "risk_score"],
        )
        writer.writeheader()
        for action in rows:
            writer.writerow(
                {
                    "id": action.id,
                    "timestamp": action.timestamp,
                    "tool_name": action.tool_name,
                    "agent_id": action.agent_id,
                    "decision": action.decision,
                    "risk_score": action.risk_score,
                }
            )
        return output.getvalue()

    def export_json_siem(self, filters: dict) -> list:
        rows = self._apply_filters(filters)
        return [
            {
                "event_type": "agentiva_action",
                "action_id": a.id,
                "timestamp": a.timestamp,
                "tool_name": a.tool_name,
                "decision": a.decision,
                "risk_score": a.risk_score,
                "agent_id": a.agent_id,
                "arguments": a.arguments,
            }
            for a in rows
        ]

    def _apply_filters(self, filters: dict) -> List[Any]:
        rows = list(self.actions)
        tool_name = filters.get("tool_name")
        decision = filters.get("decision")
        if tool_name:
            rows = [a for a in rows if a.tool_name == tool_name]
        if decision:
            rows = [a for a in rows if a.decision == decision]
        return rows
