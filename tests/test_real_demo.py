"""Tests for demo database setup and protected vs unprotected demo agent behavior."""

from __future__ import annotations

import asyncio
import sqlite3

from fastapi.testclient import TestClient

from agentiva.api import server
from agentiva.db.database import truncate_action_logs
from demo.real_agent import ATTACK_SCENARIOS, RealDemoAgent, _dispatch_tool, _tool_name_for_api
from demo.setup_demo_environment import setup_demo_db


def _reset_runtime_state() -> None:
    if server._shield is not None:
        server._shield.audit_log.clear()
        server._shield.mode = "shadow"
    server._request_counts_by_agent.clear()
    asyncio.run(truncate_action_logs())


def test_demo_db_creation(tmp_path) -> None:
    path = setup_demo_db(str(tmp_path / "demo.db"))
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM customers")
    assert cur.fetchone()[0] == 100
    cur.execute("SELECT COUNT(*) FROM transactions")
    assert cur.fetchone()[0] == 50
    conn.close()


def test_unprotected_mode_all_execute(tmp_path) -> None:
    """Each demo scenario's tools run locally against a fresh DB (destructive ops isolated)."""
    for scenario in ATTACK_SCENARIOS:
        db_path = setup_demo_db(str(tmp_path / f"db_{hash(scenario['name'])}.db"))
        agent = RealDemoAgent(db_path)
        try:
            for tool_name, args in scenario["actions"]:
                out = _dispatch_tool(agent, tool_name, args)
                assert isinstance(out, str)
                assert len(out) >= 1
        finally:
            agent.close()


def test_protected_mode_blocks_attacks() -> None:
    with TestClient(server.app) as client:
        _reset_runtime_state()
        for scenario in ATTACK_SCENARIOS:
            if scenario.get("expected") != "block":
                continue
            decisions = []
            for tool_name, args in scenario["actions"]:
                api_tool = _tool_name_for_api(tool_name)
                r = client.post(
                    "/api/v1/intercept",
                    json={
                        "tool_name": api_tool,
                        "arguments": args,
                        "agent_id": "demo-test-agent",
                    },
                )
                assert r.status_code == 200
                decisions.append(r.json().get("decision"))
            assert "block" in decisions, f"expected a block in {scenario['name']}: {decisions}"


def test_protected_mode_allows_safe_actions() -> None:
    with TestClient(server.app) as client:
        _reset_runtime_state()
        for scenario in ATTACK_SCENARIOS:
            if scenario.get("expected") == "block":
                continue
            for tool_name, args in scenario["actions"]:
                api_tool = _tool_name_for_api(tool_name)
                r = client.post(
                    "/api/v1/intercept",
                    json={
                        "tool_name": api_tool,
                        "arguments": args,
                        "agent_id": "demo-safe-agent",
                    },
                )
                assert r.status_code == 200
                d = r.json().get("decision")
                assert d in {"allow", "shadow", "approve"}, f"{scenario['name']}: {d}"
