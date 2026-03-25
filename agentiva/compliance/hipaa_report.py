"""
Generate HIPAA compliance report as PDF.
Supports 45 CFR § 164.312(b) audit control narrative with real audit log evidence.
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

from agentiva.compliance.knowledge_base import HIPAA_RULES
from agentiva.compliance.report_pdf import action_to_row, build_cover, esc, summarize_actions


def _args_blob(r: dict) -> str:
    try:
        return json.dumps(r.get("arguments") or {}, default=str).lower()
    except Exception:
        return str(r.get("arguments")).lower()


def is_phi_related(r: dict) -> bool:
    tool = (r.get("tool_name") or "").lower()
    blob = _args_blob(r)
    keys = ("ssn", "phi", "patient", "medical", "diagnosis", "hipaa", "health", "mrn", "record")
    if "read_customer" in tool or "patient" in tool or "medical" in tool:
        return True
    return any(k in blob for k in keys)


def build_hipaa_pdf(
    actions: List[Any],
    period_start: datetime,
    period_end: datetime,
    *,
    company_name: str = "Your Organization",
) -> bytes:
    rows = [action_to_row(a) for a in actions]
    stats = summarize_actions(rows)
    phi_rows = [r for r in rows if is_phi_related(r)]
    blocked_phi = [r for r in phi_rows if r["decision"] == "block"]
    breach_like = [
        r
        for r in rows
        if r["decision"] == "block"
        and (is_phi_related(r) or r["risk_score"] >= 0.85)
    ]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="HIPAA Audit Report",
    )
    styles = getSampleStyleSheet()
    story: list = []

    build_cover(
        story,
        styles,
        title="HIPAA — Audit Controls & Access Review",
        subtitle="45 CFR § 164.312(b) — Activity recording and examination",
        company=company_name,
        period_start=period_start,
        period_end=period_end,
    )

    story.append(Paragraph(esc("PHI Access Summary"), styles["Heading1"]))
    story.append(
        Paragraph(
            esc(
                f"PHI-related actions (heuristic match on tools/arguments): {len(phi_rows)}. "
                f"Blocked PHI-related: {len(blocked_phi)}. "
                f"Total actions in period: {stats['total']}."
            ),
            styles["Normal"],
        )
    )
    story.append(
        Paragraph(
            esc(
                f"Unique agents touching PHI-related events: "
                f"{len({r['agent_id'] for r in phi_rows})}."
            ),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph(esc("Control mapping (knowledge base)"), styles["Heading2"]))
    for hid, rule in list(HIPAA_RULES.items())[:4]:
        story.append(Paragraph(esc(f"{rule['section']} — {rule['name']}"), styles["Heading3"]))
        story.append(Paragraph(esc(rule["requirement"][:1200]), styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph(esc("Breach / exfiltration attempts (blocked + high risk)"), styles["Heading2"]))
    story.append(
        Paragraph(
            esc(f"Count: {len(breach_like)} (review detail in appendix)."),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph(esc("Minimum necessary — heuristic"), styles["Heading2"]))
    if phi_rows:
        by_agent: dict[str, int] = {}
        for r in phi_rows:
            by_agent[r["agent_id"]] = by_agent.get(r["agent_id"], 0) + 1
        mx = max(by_agent.values()) if by_agent else 0
        story.append(
            Paragraph(
                esc(
                    f"PHI-related events per agent (max per agent): {mx}. "
                    f"If a single agent dominates PHI volume, verify role alignment."
                ),
                styles["Normal"],
            )
        )
    else:
        story.append(
            Paragraph(
                esc("No PHI-related rows matched in this period (by heuristic)."),
                styles["Normal"],
            )
        )

    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(esc("Recommendations"), styles["Heading2"]))
    story.append(
        Paragraph(
            esc(
                "1) Tie agent roles to minimum necessary field sets in policy. "
                "2) Investigate blocked PHI attempts. "
                "3) Retain this report with change management records."
            ),
            styles["Normal"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph(esc("PHI-related access log (sample)"), styles["Heading1"]))
    data = [["Time", "Tool", "Agent", "Decision", "Risk", "Args (truncated)"]]
    for r in phi_rows[:40]:
        ab = _args_blob(r)[:80]
        data.append(
            [
                esc(r["timestamp"][:22]),
                esc(str(r["tool_name"])[:22]),
                esc(str(r["agent_id"])[:18]),
                esc(r["decision"]),
                f"{r['risk_score']:.2f}",
                esc(ab),
            ]
        )
    if len(data) == 1:
        data.append(["—", "—", "—", "—", "—", "No PHI-related rows"])
    t = Table(data, repeatRows=1, colWidths=[1.15 * inch, 1.1 * inch, 1.0 * inch, 0.75 * inch, 0.5 * inch, 2.0 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
            ]
        )
    )
    story.append(t)

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
