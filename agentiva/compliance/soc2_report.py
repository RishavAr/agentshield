"""
Generate SOC2 Type II compliance report as PDF.
Auditor-ready format with control objectives, evidence, and findings.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agentiva.compliance.knowledge_base import SOC2_CONTROLS
from agentiva.compliance.report_pdf import action_to_row, build_cover, esc, summarize_actions


def _status_for_control(control_id: str, stats: dict, rows: List[dict]) -> tuple[str, str]:
    """Return (status, recommendation)."""
    if stats["total"] == 0:
        return "FAIL", "No audit records in period — enable logging and generate traffic."
    br = stats["block_rate"]
    ar = stats["avg_risk"]
    if control_id in ("CC7.1", "CC7.2") and stats["high_risk"] > stats["total"] * 0.3:
        return "NEEDS ATTENTION", "Elevated high-risk action rate; review policies and agent roles."
    if br > 0.5:
        return "NEEDS ATTENTION", "Block rate exceeds 50%; tune policies to reduce false positives while maintaining security."
    if ar > 0.65:
        return "NEEDS ATTENTION", "Average risk elevated; review top tools and external integrations."
    return "PASS", "Evidence within expected bounds for the period; continue periodic review."


def _evidence_line(control_id: str, stats: dict, rows: List[dict]) -> str:
    if control_id == "CC6.1":
        return (
            f"Decisions in period: {stats['total']} total; "
            f"blocked={stats['blocked']}, shadowed={stats['shadowed']}, allowed/approve={stats['allowed']}; "
            f"avg risk={stats['avg_risk']:.3f}."
        )
    if control_id == "CC6.2":
        return f"Distinct agents with activity: {len(stats['agents'])}; total actions={stats['total']}."
    if control_id == "CC7.1":
        return f"Actions with risk_score &gt; 0.7: {stats['high_risk']} of {stats['total']}."
    if control_id == "CC7.2":
        blocked = [r for r in rows if r["decision"] == "block"]
        by_tool: dict[str, int] = {}
        for r in blocked:
            by_tool[r["tool_name"]] = by_tool.get(r["tool_name"], 0) + 1
        top = sorted(by_tool.items(), key=lambda x: -x[1])[:5]
        return f"Blocked actions by tool (top): {top!s}"
    if control_id == "CC7.3":
        return f"Allow/approve decisions recorded: {stats['allowed']} (rollback metadata stored per action when enabled)."
    if control_id == "CC8.1":
        return f"Total policy evaluations (actions logged): {stats['total']}."
    return f"Total actions: {stats['total']}."


def build_soc2_pdf(
    actions: List[Any],
    period_start: datetime,
    period_end: datetime,
    *,
    company_name: str = "Your Organization",
) -> bytes:
    """Build PDF bytes from persisted ActionLog rows."""
    rows = [action_to_row(a) for a in actions]
    stats = summarize_actions(rows)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="SOC2 Type II Report",
    )
    styles = getSampleStyleSheet()
    story: list = []

    build_cover(
        story,
        styles,
        title="SOC 2 Type II — Trust Services Criteria",
        subtitle="Security & availability controls (aligned)",
        company=company_name,
        period_start=period_start,
        period_end=period_end,
    )

    story.append(Paragraph(esc("Executive Summary"), styles["Heading1"]))
    story.append(
        Paragraph(
            esc(
                f"Total actions in scope: {stats['total']}. "
                f"Block rate: {stats['block_rate']*100:.1f}%. "
                f"Average risk score: {stats['avg_risk']:.3f}. "
                f"High-risk events (risk &gt; 0.7): {stats['high_risk']}. "
                f"Unique agents: {len(stats['agents'])}."
            ),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.2 * inch))

    for cid, control in SOC2_CONTROLS.items():
        story.append(Paragraph(esc(f"{control['section']} — {control['name']}"), styles["Heading2"]))
        story.append(Paragraph(esc(f"Objective: {control['requirement']}"), styles["Normal"]))
        story.append(
            Paragraph(esc(f"How Agentiva enforces: {control['how_agentiva_enforces']}"), styles["Normal"])
        )
        ev = _evidence_line(cid, stats, rows)
        story.append(Paragraph(esc(f"Evidence (from audit log): {ev}"), styles["Normal"]))
        status, rec = _status_for_control(cid, stats, rows)
        story.append(
            Paragraph(
                esc(f"Status: {status}. Recommendation: {rec}"),
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 0.15 * inch))

    story.append(PageBreak())
    story.append(Paragraph(esc("Appendix A — Sample audit trail entries"), styles["Heading1"]))
    story.append(
        Paragraph(
            esc("Up to 25 most recent rows in the reporting period (truncated fields)."),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.1 * inch))

    table_data = [["Action ID", "Timestamp", "Tool", "Decision", "Risk", "Agent"]]
    for r in rows[:25]:
        table_data.append(
            [
                esc(r["id"][:12]),
                esc(r["timestamp"][:22]),
                esc(str(r["tool_name"])[:28]),
                esc(r["decision"]),
                f"{r['risk_score']:.2f}",
                esc(str(r["agent_id"])[:20]),
            ]
        )
    t = Table(table_data, repeatRows=1, colWidths=[0.95 * inch, 1.2 * inch, 1.35 * inch, 0.8 * inch, 0.55 * inch, 1.0 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#f9fafb")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )
    story.append(t)

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
