"""Unit tests for agentiva.compliance.phi_detector.detect_phi."""

from __future__ import annotations

from agentiva.compliance.phi_detector import detect_phi


def test_detect_ssn() -> None:
    r = detect_phi("Verify identity: 123-45-6789")
    assert r["has_phi"] is True
    assert "SSN" in r["types"]


def test_detect_credit_card() -> None:
    r = detect_phi("Card 4111-1111-1111-1111 charged")
    assert r["has_phi"] is True
    assert "credit_card" in r["types"]


def test_detect_mrn() -> None:
    r = detect_phi("Lookup MRN: 1234567890 for visit")
    assert r["has_phi"] is True
    assert "medical_record_number" in r["types"]


def test_detect_diagnosis_code() -> None:
    # ICD-10 match requires medical context terms from MEDICAL_TERMS.
    r = detect_phi("Patient diagnosis E11.9 documented in chart")
    assert r["has_phi"] is True
    assert "diagnosis_code" in r["types"]


def test_detect_prescription() -> None:
    r = detect_phi("Patient prescription: metformin per physician")
    assert r["has_phi"] is True
    assert "prescription" in r["types"]


def test_no_phi_in_normal_text() -> None:
    r = detect_phi("Schedule meeting Tuesday 3pm about quarterly revenue")
    assert r["has_phi"] is False
    assert r["types"] == []
    assert r["risk_adjustment"] == 0.0


def test_risk_adjustment_calculation() -> None:
    ssn_only = detect_phi("SSN 123-45-6789")
    assert ssn_only["risk_adjustment"] == 0.4  # critical

    stacked = detect_phi(
        "SSN 123-45-6789 and card 4111-1111-1111-1111 and MRN: 1234567890"
    )
    assert stacked["risk_adjustment"] <= 0.5
    assert stacked["risk_adjustment"] > 0.4

    empty = detect_phi("")
    assert empty["risk_adjustment"] == 0.0
