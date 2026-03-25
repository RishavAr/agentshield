"""
Generate PCI-DSS oriented compliance report as PDF (cardholder data handling & monitoring).
"""

from __future__ import annotations

import json
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

from agentiva.compliance.knowledge_base import PCI_DSS_REQUIREMENTS
from agentiva.compliance.report_pdf import action_to_row, build_cover, esc, summarize_actions


def _args_blob(r: dict) -> str:
    try:
        return json.dumps(r.get("arguments") or {}, default=str).lower()
    except Exception:
        return str(r.get("arguments")).lower()


def is_payment_related(r: dict) -> bool:
    tool = (r.get("tool_name") or "").lower()
    blob = _args_blob(r)
    keys = ("payment", "transfer", "refund", "card", "cvv", "pan", "charge", "invoice")
    return any(k in tool for k in ("payment", "transfer", "refund", "transaction", "card")) or any(
        k in blob for k in keys
    )


def build_pci_pdf(
    actions: List[Any],
    period_start: datetime,
    period_end: datetime,
    *,
    company_name: str = "Your Organization",
) -> bytes:
    rows = [action_to_row(a) for a in actions]
    stats = summarize_actions(rows)
    pay_rows = [r for r in rows if is_payment_related(r)]
    blocked_pay = [r for r in pay_rows if r["decision"] == "block"]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="PCI-DSS Report",
    )
    styles = getSampleStyleSheet()
    story: list = []

    build_cover(
        story,
        styles,
        title="PCI-DSS — Monitoring & access (summary)",
        subtitle="Cardholder data environment — agent actions",
        company=company_name,
        period_start=period_start,
        period_end=period_end,
    )

    story.append(Paragraph(esc("Executive Summary"), styles["Heading1"]))
    story.append(
        Paragraph(
            esc(
                f"Total actions: {stats['total']}. "
                f"Payment-related (heuristic): {len(pay_rows)}. "
                f"Blocked payment-related: {len(blocked_pay)}. "
                f"Average risk: {stats['avg_risk']:.3f}."
            ),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.2 * inch))

    for pid, req in PCI_DSS_REQUIREMENTS.items():
        story.append(Paragraph(esc(f"{req['section']} — {req['name']}"), styles["Heading2"]))
        story.append(Paragraph(esc(req["requirement"]), styles["Normal"]))
        story.append(Paragraph(esc(f"How Agentiva enforces: {req['how_agentiva_enforces']}"), styles["Normal"]))
        if "3" in pid:
            ev = f"Blocked rows mentioning card/cvv in arguments (approx): {sum(1 for r in rows if r['decision']=='block' and ('card' in _args_blob(r) or 'cvv' in _args_blob(r)))}."
        elif "7" in pid:
            ev = f"Agents touching payment-related tools: {len({r['agent_id'] for r in pay_rows})}."
        else:
            ev = f"Payment-related actions logged: {len(pay_rows)}; blocked: {len(blocked_pay)}."
        story.append(Paragraph(esc(f"Evidence: {ev}"), styles["Normal"]))
        st = "PASS" if stats["total"] and stats["avg_risk"] < 0.75 else "NEEDS ATTENTION"
        story.append(Paragraph(esc(f"Status: {st}."), styles["Normal"]))
        story.append(Spacer(1, 0.12 * inch))

    story.append(PageBreak())
    story.append(Paragraph(esc("Appendix — Payment-related sample"), styles["Heading1"]))
    data = [["Timestamp", "Tool", "Agent", "Decision", "Risk"]]
    for r in pay_rows[:35]:
        data.append(
            [
                esc(r["timestamp"][:24]),
                esc(str(r["tool_name"])[:30]),
                esc(str(r["agent_id"])[:24]),
                esc(r["decision"]),
                f"{r['risk_score']:.2f}",
            ]
        )
    if len(data) == 1:
        data.append(["—", "—", "—", "—", "No payment-related rows"])
    t = Table(data, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14532d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
            ]
        )
    )
    story.append(t)

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
