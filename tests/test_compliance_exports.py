import asyncio

from fastapi.testclient import TestClient

from agentshield.api import server
from agentshield.audit.compliance import ComplianceExporter


def _seed_actions():
    shield = server.get_shield()
    shield.audit_log.clear()
    asyncio.run(shield.intercept("send_email", {"to": "a@outside.com"}, "agent-a"))
    asyncio.run(shield.intercept("create_jira_ticket", {"title": "x"}, "agent-a"))
    return shield


def test_soc2_export_direct() -> None:
    with TestClient(server.app):
        shield = _seed_actions()
        exporter = ComplianceExporter(shield.audit_log, approvals={"x": True})
        report = exporter.export_soc2_report("2020-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00")
        assert "policy_violations" in report


def test_gdpr_export_direct() -> None:
    with TestClient(server.app):
        shield = _seed_actions()
        exporter = ComplianceExporter(shield.audit_log)
        report = exporter.export_gdpr_data_access_log("outside.com")
        assert report["data_subject_id"] == "outside.com"


def test_compliance_api_endpoints() -> None:
    with TestClient(server.app) as client:
        _seed_actions()
        params = {"start": "2020-01-01T00:00:00+00:00", "end": "2030-01-01T00:00:00+00:00"}
        assert client.get("/api/v1/compliance/soc2", params=params).status_code == 200
        assert client.get("/api/v1/compliance/gdpr/outside.com").status_code == 200
        assert client.get("/api/v1/compliance/eu-ai-act").status_code == 200


def test_export_csv_and_siem_api() -> None:
    with TestClient(server.app) as client:
        _seed_actions()
        assert "tool_name" in client.get("/api/v1/export/csv").text
        siem = client.get("/api/v1/export/siem").json()
        assert isinstance(siem, list)
