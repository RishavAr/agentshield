from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentshield.policy.smart_scorer import SmartRiskScorer


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
]
TIME_SCENARIOS = ["02:00", "03:00", "09:00", "14:00", "18:00", "23:00"]
AGENT_TYPES = ["new_agent", "established_agent", "unknown_agent", "trusted_agent", "suspended_agent"]
CONTENT_TYPES = ["normal", "contains_pii", "contains_credentials", "contains_financial", "contains_destructive", "contains_sensitive"]
RECIPIENT_TYPES = ["internal", "external", "broadcast", "personal", "unknown"]
FREQUENCY_TYPES = ["normal", "high", "burst", "first_time"]


def _content_payload(content: str) -> dict:
    mapping = {
        "normal": "hello world",
        "contains_pii": "ssn=123-45-6789",
        "contains_credentials": "password=secret token=abc",
        "contains_financial": "bank transfer financial report",
        "contains_destructive": "delete drop truncate",
        "contains_sensitive": "confidential pii credentials",
    }
    return {"body": mapping[content]}


def _time_to_dt(t: str) -> datetime:
    hour, minute = map(int, t.split(":"))
    return datetime(2026, 1, 1, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize("tool", TOOLS[:15])
@pytest.mark.parametrize("time", TIME_SCENARIOS)
@pytest.mark.parametrize("content", CONTENT_TYPES)
def test_risk_score_by_tool_time_content(tool, time, content):
    scorer = SmartRiskScorer()
    assessment = scorer.score_action(
        tool_name=tool,
        arguments=_content_payload(content),
        timestamp=_time_to_dt(time),
        agent_id="risk-agent",
        recent_actions_per_minute=5,
    )
    assert 0.0 <= assessment.score <= 1.0


@pytest.mark.parametrize("agent_type", AGENT_TYPES)
@pytest.mark.parametrize("recipient", RECIPIENT_TYPES)
@pytest.mark.parametrize("frequency", FREQUENCY_TYPES)
def test_risk_score_by_agent_recipient_frequency(agent_type, recipient, frequency):
    scorer = SmartRiskScorer()
    rpm = {"normal": 5, "high": 45, "burst": 120, "first_time": 1}[frequency]
    to_map = {
        "internal": "dev@yourcompany.com",
        "external": "evil@outside.com",
        "broadcast": "#general",
        "personal": "person@gmail.com",
        "unknown": "unknown",
    }
    assessment = scorer.score_action(
        tool_name="send_email",
        arguments={"to": to_map[recipient], "body": "hello"},
        agent_id=f"agent-{agent_type}",
        recent_actions_per_minute=rpm,
        first_time_tool=(frequency == "first_time"),
        agent_reputation=("unknown" if agent_type in {"unknown_agent", "suspended_agent"} else "established"),
    )
    assert 0.0 <= assessment.score <= 1.0
