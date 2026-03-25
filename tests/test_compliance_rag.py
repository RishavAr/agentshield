"""Compliance KB, PHI detector, audit SQL validation."""

from agentiva.compliance.knowledge_base import get_compliance_context, get_evidence_queries
from agentiva.compliance.phi_detector import detect_phi
from agentiva.db.database import validate_audit_select_sql


def test_get_compliance_context_hipaa():
    text = get_compliance_context("What HIPAA controls apply to PHI?")
    assert "164.312" in text or "HIPAA" in text


def test_evidence_queries_keys():
    hipaa = get_evidence_queries("hipaa")
    assert "164.312.b" in hipaa
    assert "action_logs" in hipaa["164.312.b"]


def test_phi_detector_ssn():
    r = detect_phi("Patient SSN 123-45-6789 on file")
    assert r["has_phi"]
    assert "SSN" in r["types"]


def test_validate_audit_select_allows_action_logs_only():
    assert validate_audit_select_sql(
        "SELECT COUNT(*) AS n FROM action_logs WHERE decision='block'"
    )
    assert not validate_audit_select_sql("DELETE FROM action_logs WHERE 1=1")
    assert not validate_audit_select_sql("SELECT * FROM chat_messages")
