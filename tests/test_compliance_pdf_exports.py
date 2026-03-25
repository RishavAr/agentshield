"""PDF compliance reports (ReportLab)."""

from datetime import datetime, timezone

from agentiva.compliance.hipaa_report import build_hipaa_pdf
from agentiva.compliance.pci_report import build_pci_pdf
from agentiva.compliance.soc2_report import build_soc2_pdf


class _FakeAction:
    def __init__(self) -> None:
        self.id = "a1"
        self.timestamp = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        self.tool_name = "send_email"
        self.arguments = {"to": "x@y.com"}
        self.agent_id = "agent-1"
        self.decision = "block"
        self.risk_score = 0.85
        self.mode = "shadow"


def test_soc2_pdf_starts_with_pdf_magic() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 31, tzinfo=timezone.utc)
    pdf = build_soc2_pdf([_FakeAction()], start, end, company_name="Test Co")
    assert pdf[:4] == b"%PDF"


def test_hipaa_pdf_starts_with_pdf_magic() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 31, tzinfo=timezone.utc)
    pdf = build_hipaa_pdf([_FakeAction()], start, end)
    assert pdf[:4] == b"%PDF"


def test_pci_pdf_starts_with_pdf_magic() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 31, tzinfo=timezone.utc)
    pdf = build_pci_pdf([_FakeAction()], start, end)
    assert pdf[:4] == b"%PDF"
