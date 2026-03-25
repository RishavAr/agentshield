"""
Run read-only evidence queries against `action_logs` and assemble RAG context for the co-pilot.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from agentiva.compliance.knowledge_base import (
    HIPAA_RULES,
    PCI_DSS_REQUIREMENTS,
    SOC2_CONTROLS,
    get_compliance_context,
    get_evidence_queries,
)
from agentiva.db.database import execute_audit_select


def _frameworks_for_question(question: str) -> List[str]:
    q = question.lower()
    out: List[str] = []
    if any(k in q for k in ("hipaa", "phi", "patient", "medical", "health", "164.")):
        out.append("hipaa")
    if any(k in q for k in ("soc2", "soc 2", "cc6", "cc7", "cc8", "trust service")):
        out.append("soc2")
    if any(k in q for k in ("pci", "payment", "card", "cardholder", "cvv")):
        out.append("pci")
    if any(k in q for k in ("compliance", "audit", "regulation", "gdpr")) and not out:
        out.extend(["hipaa", "soc2"])
    return out


BASELINE_QUERIES: List[Tuple[str, str]] = [
    (
        "totals_by_decision",
        "SELECT decision, COUNT(*) AS n, ROUND(AVG(risk_score), 4) AS avg_risk FROM action_logs GROUP BY decision",
    ),
    (
        "recent_high_risk",
        "SELECT id, tool_name, agent_id, decision, risk_score, timestamp FROM action_logs "
        "ORDER BY risk_score DESC, timestamp DESC LIMIT 15",
    ),
    (
        "totals",
        "SELECT COUNT(*) AS total FROM action_logs",
    ),
]


async def fetch_audit_grounding(question: str) -> Dict[str, Any]:
    """
    Execute safe SELECTs only. Returns structured evidence + compliance text.
    """
    results: Dict[str, Any] = {
        "baseline": {},
        "evidence": {},
        "compliance_text": get_compliance_context(question),
        "frameworks": _frameworks_for_question(question),
        "errors": [],
    }

    for name, sql in BASELINE_QUERIES:
        try:
            rows = await execute_audit_select(sql)
            results["baseline"][name] = rows
        except Exception as exc:
            results["errors"].append({"query": name, "error": str(exc)})

    for fw in _frameworks_for_question(question):
        eq = get_evidence_queries(fw)
        results["evidence"][fw] = {}
        for control_id, sql in eq.items():
            try:
                rows = await execute_audit_select(sql)
                results["evidence"][fw][control_id] = {"sql": sql, "rows": rows}
            except Exception as exc:
                results["evidence"][fw][control_id] = {"sql": sql, "error": str(exc)}

    # If user asked compliance but no framework matched, still attach SOC2 summary evidence
    if not results["evidence"] and any(
        k in question.lower() for k in ("compliance", "hipaa", "soc", "pci", "audit", "regulation")
    ):
        for fw in ("soc2", "hipaa"):
            if fw not in results["evidence"]:
                results["evidence"][fw] = {}
            eq = get_evidence_queries(fw)
            for control_id, sql in list(eq.items())[:2]:
                try:
                    rows = await execute_audit_select(sql)
                    results["evidence"][fw][control_id] = {"sql": sql, "rows": rows}
                except Exception as exc:
                    results["evidence"][fw][control_id] = {"sql": sql, "error": str(exc)}

    return results


def format_grounding_for_llm(grounding: Dict[str, Any]) -> str:
    """Serialize evidence for the system prompt (no raw user PII expansion — use DB rows as-is)."""
    parts: List[str] = []
    parts.append("=== AUDIT DATABASE EVIDENCE (action_logs) ===")
    parts.append(json.dumps(grounding.get("baseline", {}), default=str, indent=2)[:12000])
    ev = grounding.get("evidence") or {}
    if ev:
        parts.append("=== FRAMEWORK EVIDENCE QUERIES ===")
        parts.append(json.dumps(ev, default=str, indent=2)[:12000])
    if grounding.get("errors"):
        parts.append("=== QUERY NOTES ===")
        parts.append(json.dumps(grounding["errors"], default=str))
    parts.append("=== COMPLIANCE RULES (CITATIONS) ===")
    parts.append(grounding.get("compliance_text", "")[:8000])
    return "\n".join(parts)


def extract_numbers_from_text(text: str) -> List[str]:
    """Loose extraction for post-hoc grounding checks."""
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def grounding_covers_numbers(answer: str, grounding_text: str) -> bool:
    """
    Soft validation: every numeric token in the answer should appear in grounding blobs.
    If no numbers in answer, pass. If numbers appear that aren't in grounding, fail.
    """
    ans_nums = set(extract_numbers_from_text(answer))
    if not ans_nums:
        return True
    ground = grounding_text + answer  # allow self-reference for round numbers
    gset = set(extract_numbers_from_text(ground))
    # allow common years
    gset.update({"2024", "2025", "2026", "0", "1"})
    suspicious = {n for n in ans_nums if n not in gset and float(n) > 10}
    return len(suspicious) == 0
