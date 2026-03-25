"""Tests for agentiva.compliance.knowledge_base (HIPAA / SOC2 / PCI citations + evidence SQL)."""

from __future__ import annotations

from agentiva.compliance.knowledge_base import (
    HIPAA_RULES,
    PCI_DSS_REQUIREMENTS,
    SOC2_CONTROLS,
    get_compliance_context,
    get_evidence_queries,
)
from agentiva.db.database import validate_audit_select_sql


def test_hipaa_rules_complete() -> None:
    assert len(HIPAA_RULES) >= 6
    for key, rule in HIPAA_RULES.items():
        assert key.startswith("164.")
        assert "section" in rule and "45 CFR" in rule["section"]
        assert rule.get("requirement")
        assert rule.get("evidence_query")
        assert "action_logs" in rule["evidence_query"]


def test_soc2_controls_complete() -> None:
    assert len(SOC2_CONTROLS) >= 6
    for key, ctrl in SOC2_CONTROLS.items():
        assert key.startswith("CC")
        assert ctrl.get("section")
        assert ctrl.get("requirement")
        assert "action_logs" in ctrl["evidence_query"]


def test_pci_requirements_complete() -> None:
    assert len(PCI_DSS_REQUIREMENTS) >= 3
    for _key, req in PCI_DSS_REQUIREMENTS.items():
        assert "PCI" in req["section"] or "PCI-DSS" in req["section"]
        assert req.get("evidence_query")
        assert "action_logs" in req["evidence_query"]


def test_get_compliance_context_hipaa() -> None:
    text = get_compliance_context("What HIPAA safeguards apply to our PHI handling?")
    assert "HIPAA" in text
    assert "164.312" in text or "45 CFR" in text


def test_get_compliance_context_soc2() -> None:
    text = get_compliance_context("Explain SOC2 CC6 logical access controls")
    assert "SOC2" in text or "CC6" in text
    assert "CC6.1" in text or "Logical Access" in text


def test_evidence_queries_valid_sql() -> None:
    for fw in ("hipaa", "soc2", "soc_2", "pci"):
        queries = get_evidence_queries(fw)
        assert queries, f"no queries for {fw}"
        for _cid, sql in queries.items():
            assert validate_audit_select_sql(sql.strip()), sql[:120]
