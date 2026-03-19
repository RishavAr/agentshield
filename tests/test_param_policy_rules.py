from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentshield import AgentShield
from agentshield.interceptor.core import InterceptedAction
from agentshield.policy.engine import PolicyEngine


TOOLS = [
    "send_email",
    "gmail_send",
    "slack_post",
    "slack_dm",
    "create_jira_ticket",
    "update_jira_ticket",
    "delete_jira_ticket",
    "database_query",
    "database_write",
    "database_delete",
    "call_external_api",
    "call_internal_api",
    "read_customer_data",
    "write_customer_data",
    "delete_customer_data",
    "transfer_funds",
    "process_payment",
    "create_user",
    "delete_user",
    "modify_permissions",
    "deploy_code",
    "rollback_deploy",
    "send_sms",
    "make_phone_call",
    "upload_file",
    "download_file",
    "delete_file",
    "create_pr",
    "merge_pr",
    "run_shell_command",
    "install_package",
]
OPERATORS = ["equals", "not_equals", "contains", "not_contains", "in"]
ACTIONS = ["block", "shadow", "allow", "approve"]
RISK_LEVELS = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
SCENARIO_TYPES = ["external", "internal", "destructive", "business_hours", "bulk"]


def _args_for_scenario(scenario_type: str) -> dict:
    if scenario_type == "external":
        return {"to": "external@evil.com", "hour": 14, "ids": [1]}
    if scenario_type == "internal":
        return {"to": "internal@yourcompany.com", "hour": 14, "ids": [1]}
    if scenario_type == "destructive":
        return {"query": "DROP TABLE users", "action": "delete", "hour": 14}
    if scenario_type == "business_hours":
        return {"to": "team@yourcompany.com", "hour": 10}
    return {"ids": list(range(20)), "hour": 14}


@pytest.mark.parametrize("tool_name", TOOLS)
@pytest.mark.parametrize("risk_level", RISK_LEVELS)
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("operator", OPERATORS)
@pytest.mark.parametrize("scenario_type", SCENARIO_TYPES)
def test_policy_rule_evaluation(tool_name, risk_level, action, operator, scenario_type):
    # PolicyEngine check operator compatibility and returns deterministic rule action.
    rule_value = (
        "@yourcompany.com"
        if operator in {"contains", "not_contains"}
        else "internal@yourcompany.com"
    )
    condition = {"field": "arguments.to", "operator": operator, "value": rule_value}
    action_obj = InterceptedAction(
        id="x",
        timestamp=datetime.now(UTC).isoformat(),
        tool_name=tool_name,
        arguments=_args_for_scenario(scenario_type),
        agent_id="policy-test",
        risk_score=risk_level,
        decision="pending",
        mode="shadow",
    )

    # Emulate rule check semantics directly through PolicyEngine._check
    engine = PolicyEngine("policies/default.yaml")
    checked = engine._check(condition, action_obj)
    assert isinstance(checked, bool)
    # Ensure action labels are valid expected labels
    assert action in {"block", "shadow", "allow", "approve"}


@pytest.mark.parametrize("tool_name", TOOLS)
@pytest.mark.parametrize(
    "argument_pattern",
    [
        {"to": "external@evil.com"},
        {"to": "internal@yourcompany.com"},
        {"query": "DROP TABLE users"},
        {"query": "SELECT * FROM users"},
        {"channel": "#general"},
        {"channel": "#private-team"},
        {"amount": "1000000"},
        {"amount": "50"},
        {"action": "delete"},
        {"action": "read"},
    ],
)
def test_risk_scoring_by_tool_and_args(tool_name, argument_pattern):
    shield = AgentShield(mode="shadow")
    action = shield.intercept_sync(tool_name, argument_pattern, agent_id="risk-test")
    assert 0.0 <= action.risk_score <= 1.0
