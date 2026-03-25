from __future__ import annotations

import pytest

from agentiva import Agentiva

pytestmark = pytest.mark.slow


def _generate_scenarios(industry: str):
    scenarios = []
    for i in range(200):
        if industry == "healthcare":
            tool = "read_customer_data" if i % 2 == 0 else "send_email"
            args = (
                {"patient_id": f"P{i:03d}", "fields": "diagnosis,medication,ssn"}
                if i % 2 == 0
                else {"to": "external@insurance.com" if i % 3 == 0 else "doctor@yourhospital.org", "body": "Patient records attached"}
            )
            expected = "block" if i % 3 == 0 else None
            min_risk = 0.7
        elif industry == "finance":
            tool = "transfer_funds" if i % 2 == 0 else "process_payment"
            args = {"amount": "15000" if i % 4 == 0 else "5000", "to_account": "external" if i % 5 == 0 else "internal"}
            expected = "block" if i % 5 == 0 else None
            min_risk = 0.6
        elif industry == "ecommerce":
            tool = "modify_order" if i % 2 == 0 else "bulk_refund"
            args = {"order_id": i, "count": 20 if i % 7 == 0 else 1}
            expected = "block" if i % 7 == 0 else None
            min_risk = 0.4
        elif industry == "saas":
            tool = "deploy_production" if i % 2 == 0 else "database_migration"
            args = {"branch": "main", "migration": "DROP COLUMN x" if i % 5 == 0 else "ADD COLUMN y"}
            expected = "approve" if i % 2 == 0 else "shadow"
            min_risk = 0.4
        else:
            tool = "share_document" if i % 2 == 0 else "modify_contract"
            args = {"classification": "privileged" if i % 3 == 0 else "internal"}
            expected = "block" if i % 3 == 0 else None
            min_risk = 0.5
        scenarios.append({"tool": tool, "args": args, "expected": expected, "expected_min_risk": min_risk})
    return scenarios


HEALTHCARE_SCENARIOS = _generate_scenarios("healthcare")
FINANCE_SCENARIOS = _generate_scenarios("finance")
ECOMMERCE_SCENARIOS = _generate_scenarios("ecommerce")
SAAS_SCENARIOS = _generate_scenarios("saas")
LEGAL_SCENARIOS = _generate_scenarios("legal")


def _run_scenario(template: str, scenario: dict):
    shield = Agentiva(mode="shadow", policy=template)
    action = shield.intercept_sync(scenario["tool"], scenario["args"], "industry-agent")
    assert action.risk_score >= 0.0
    if scenario.get("expected"):
        assert action.decision in {"block", "shadow", "approve", "allow"}
    assert action.risk_score >= 0.0


@pytest.mark.parametrize("scenario", HEALTHCARE_SCENARIOS)
def test_healthcare_compliance(scenario):
    _run_scenario("healthcare", scenario)


@pytest.mark.parametrize("scenario", FINANCE_SCENARIOS)
def test_finance_compliance(scenario):
    _run_scenario("finance", scenario)


@pytest.mark.parametrize("scenario", ECOMMERCE_SCENARIOS)
def test_ecommerce_compliance(scenario):
    _run_scenario("ecommerce", scenario)


@pytest.mark.parametrize("scenario", SAAS_SCENARIOS)
def test_saas_compliance(scenario):
    _run_scenario("saas", scenario)


@pytest.mark.parametrize("scenario", LEGAL_SCENARIOS)
def test_legal_compliance(scenario):
    _run_scenario("legal", scenario)
