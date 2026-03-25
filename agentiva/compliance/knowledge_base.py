"""
Compliance knowledge base with real regulatory citations.
Used by the co-pilot to give trustworthy, grounded answers.

Evidence SQL targets the persisted `action_logs` table (see agentiva.db.models.ActionLog).
Use CAST(arguments AS TEXT) for JSON arguments on SQLite.
"""

from __future__ import annotations

from typing import Dict

# Table name: action_logs (columns: id, timestamp, tool_name, arguments JSON, agent_id, decision, risk_score, mode, ...)

HIPAA_RULES: Dict[str, dict] = {
    "164.312.a.1": {
        "name": "Access Control",
        "section": "45 CFR § 164.312(a)(1)",
        "requirement": (
            "Implement technical policies and procedures for electronic information systems that "
            "maintain electronic protected health information to allow access only to those persons or "
            "software programs that have been granted access rights."
        ),
        "how_agentiva_enforces": (
            "Role-based policies restrict PHI access to authorized agent roles. Agent registry verifies "
            "identity before any PHI access. Minimum necessary standard enforced — agents only see data "
            "needed for their specific task."
        ),
        "evidence_query": (
            "SELECT COUNT(*) AS total_phi_access, "
            "SUM(CASE WHEN decision='block' THEN 1 ELSE 0 END) AS blocked "
            "FROM action_logs WHERE tool_name LIKE '%patient%' OR tool_name LIKE '%medical%' "
            "OR CAST(arguments AS TEXT) LIKE '%ssn%' OR CAST(arguments AS TEXT) LIKE '%diagnosis%'"
        ),
    },
    "164.312.b": {
        "name": "Audit Controls",
        "section": "45 CFR § 164.312(b)",
        "requirement": (
            "Implement hardware, software, and/or procedural mechanisms that record and examine "
            "activity in information systems that contain or use electronic protected health information."
        ),
        "how_agentiva_enforces": (
            "Every agent action is logged with: agent_id, tool_name, arguments, decision, risk_score, "
            "timestamp. Tamper-resistant audit trail stored in the database with full history."
        ),
        "evidence_query": (
            "SELECT COUNT(*) AS total_logged_actions, MIN(timestamp) AS earliest, MAX(timestamp) AS latest "
            "FROM action_logs"
        ),
    },
    "164.312.c.1": {
        "name": "Integrity Controls",
        "section": "45 CFR § 164.312(c)(1)",
        "requirement": (
            "Implement policies and procedures to protect electronic protected health information from "
            "improper alteration or destruction."
        ),
        "how_agentiva_enforces": (
            "Destructive operations (DELETE, UPDATE, DROP) on sensitive data are policy-controlled. "
            "Rollback engine captures state before modifications where configured."
        ),
        "evidence_query": (
            "SELECT COUNT(*) AS destructive_attempts, "
            "SUM(CASE WHEN decision='block' THEN 1 ELSE 0 END) AS blocked "
            "FROM action_logs WHERE CAST(arguments AS TEXT) LIKE '%DELETE%' "
            "OR CAST(arguments AS TEXT) LIKE '%UPDATE%' OR CAST(arguments AS TEXT) LIKE '%DROP%'"
        ),
    },
    "164.312.d": {
        "name": "Person or Entity Authentication",
        "section": "45 CFR § 164.312(d)",
        "requirement": (
            "Implement procedures to verify that a person or entity seeking access to electronic "
            "protected health information is the one claimed."
        ),
        "how_agentiva_enforces": (
            "Agent registry with API key authentication. Each agent has a unique ID and reputation score. "
            "Multi-tenant isolation ensures agents cannot access other tenants' data."
        ),
        "evidence_query": (
            "SELECT agent_id, COUNT(*) AS actions FROM action_logs GROUP BY agent_id"
        ),
    },
    "164.312.e.1": {
        "name": "Transmission Security",
        "section": "45 CFR § 164.312(e)(1)",
        "requirement": (
            "Implement technical security measures to guard against unauthorized access to electronic "
            "protected health information that is being transmitted over an electronic communications network."
        ),
        "how_agentiva_enforces": (
            "External transmission of sensitive data is intercepted and scored. Email and API actions to "
            "external recipients with sensitive content are blocked or shadowed per policy."
        ),
        "evidence_query": (
            "SELECT COUNT(*) AS external_sends_blocked FROM action_logs WHERE decision='block' "
            "AND (tool_name='send_email' OR tool_name='call_external_api') "
            "AND CAST(arguments AS TEXT) LIKE '%external%'"
        ),
    },
    "164.404": {
        "name": "Breach Notification",
        "section": "45 CFR § 164.404",
        "requirement": (
            "Notify affected individuals within 60 days of discovery of a breach of unsecured protected health information."
        ),
        "how_agentiva_enforces": (
            "High-risk and PHI-adjacent actions are logged with risk scores; alerts can be routed to "
            "compliance channels. Full forensic trail supports incident response."
        ),
        "evidence_query": (
            "SELECT id, tool_name, decision, risk_score, timestamp FROM action_logs "
            "WHERE risk_score > 0.9 AND (CAST(arguments AS TEXT) LIKE '%ssn%' "
            "OR CAST(arguments AS TEXT) LIKE '%medical%' OR CAST(arguments AS TEXT) LIKE '%diagnosis%') "
            "ORDER BY timestamp DESC LIMIT 10"
        ),
    },
}

SOC2_CONTROLS: Dict[str, dict] = {
    "CC6.1": {
        "name": "Logical Access Security",
        "section": "CC6.1",
        "requirement": (
            "The entity implements logical access security software, infrastructure, and architectures "
            "over protected information assets to protect them from security events."
        ),
        "how_agentiva_enforces": (
            "YAML policy engine evaluates every action. API key authentication. Role-based access control. "
            "Multi-tenant data isolation."
        ),
        "evidence_query": (
            "SELECT decision, COUNT(*) AS count, AVG(risk_score) AS avg_risk FROM action_logs GROUP BY decision"
        ),
    },
    "CC6.2": {
        "name": "User Authentication",
        "section": "CC6.2",
        "requirement": (
            "Prior to issuing system credentials and granting system access, the entity registers and "
            "authorizes new internal and external users."
        ),
        "how_agentiva_enforces": (
            "Agent registry tracks all agents with unique IDs. New agents start with restricted permissions. "
            "Reputation scoring adjusts visibility over time."
        ),
        "evidence_query": (
            "SELECT agent_id, COUNT(*) AS actions, AVG(risk_score) AS avg_risk FROM action_logs GROUP BY agent_id"
        ),
    },
    "CC7.1": {
        "name": "Threat Detection",
        "section": "CC7.1",
        "requirement": (
            "To meet its objectives, the entity uses detection and monitoring procedures to identify "
            "changes to configurations that result in the introduction of new vulnerabilities."
        ),
        "how_agentiva_enforces": (
            "Multi-signal risk scoring, behavioral drift, and anomaly detection flag unusual patterns."
        ),
        "evidence_query": "SELECT COUNT(*) AS high_risk_actions FROM action_logs WHERE risk_score > 0.7",
    },
    "CC7.2": {
        "name": "Incident Response",
        "section": "CC7.2",
        "requirement": (
            "The entity monitors system components and the operation of those components for anomalies "
            "that are indicative of malicious acts."
        ),
        "how_agentiva_enforces": (
            "Automatic blocking of dangerous actions. Real-time feed via WebSocket. Full audit trail for review."
        ),
        "evidence_query": (
            "SELECT tool_name, COUNT(*) AS blocked_count, MAX(risk_score) AS max_risk "
            "FROM action_logs WHERE decision='block' GROUP BY tool_name ORDER BY blocked_count DESC"
        ),
    },
    "CC7.3": {
        "name": "Recovery",
        "section": "CC7.3",
        "requirement": (
            "The entity identifies, develops, and implements activities to recover from identified security incidents."
        ),
        "how_agentiva_enforces": (
            "Rollback engine captures state before actions where enabled. Undo steps stored with each action record."
        ),
        "evidence_query": "SELECT COUNT(*) AS rollback_available FROM action_logs WHERE decision='allow'",
    },
    "CC8.1": {
        "name": "Change Management",
        "section": "CC8.1",
        "requirement": (
            "The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, "
            "and implements changes to infrastructure."
        ),
        "how_agentiva_enforces": (
            "Policy history and action logs provide traceability. Policy updates can be applied via API with logging."
        ),
        "evidence_query": "SELECT COUNT(*) AS policy_evaluations FROM action_logs",
    },
}

PCI_DSS_REQUIREMENTS: Dict[str, dict] = {
    "req_3": {
        "name": "Protect Stored Data",
        "section": "PCI-DSS Requirement 3",
        "requirement": "Protect stored cardholder data.",
        "how_agentiva_enforces": (
            "Sensitive field patterns in arguments increase risk; outbound content with card data is blocked "
            "or shadowed per policy."
        ),
        "evidence_query": (
            "SELECT COUNT(*) AS card_data_blocks FROM action_logs WHERE decision='block' "
            "AND (CAST(arguments AS TEXT) LIKE '%credit_card%' OR CAST(arguments AS TEXT) LIKE '%cvv%')"
        ),
    },
    "req_7": {
        "name": "Restrict Access",
        "section": "PCI-DSS Requirement 7",
        "requirement": "Restrict access to cardholder data by business need to know.",
        "how_agentiva_enforces": (
            "Role-based policies restrict which tools and fields agents may access."
        ),
        "evidence_query": (
            "SELECT agent_id, COUNT(*) AS financial_access FROM action_logs "
            "WHERE tool_name LIKE '%payment%' OR tool_name LIKE '%transaction%' GROUP BY agent_id"
        ),
    },
    "req_10": {
        "name": "Track and Monitor",
        "section": "PCI-DSS Requirement 10",
        "requirement": "Track and monitor all access to network resources and cardholder data.",
        "how_agentiva_enforces": (
            "Every payment-related tool invocation is logged with decision and risk score."
        ),
        "evidence_query": (
            "SELECT COUNT(*) AS financial_actions, "
            "SUM(CASE WHEN decision='block' THEN 1 ELSE 0 END) AS blocked "
            "FROM action_logs WHERE tool_name LIKE '%transfer%' OR tool_name LIKE '%payment%' OR tool_name LIKE '%refund%'"
        ),
    },
}


def get_compliance_context(question: str) -> str:
    """Return relevant compliance rule text for the user's question (no DB access)."""
    question_lower = question.lower()
    context_parts: list[str] = []

    if any(
        k in question_lower
        for k in ("hipaa", "health", "phi", "patient", "medical", "164.")
    ):
        context_parts.append("=== HIPAA COMPLIANCE RULES ===")
        for _key, rule in HIPAA_RULES.items():
            context_parts.append(f"\n{rule['section']} — {rule['name']}")
            context_parts.append(f"Requirement: {rule['requirement']}")
            context_parts.append(f"How Agentiva enforces: {rule['how_agentiva_enforces']}")

    if any(
        k in question_lower
        for k in ("soc2", "soc 2", "soc-2", "audit", "compliance", "cc6", "cc7", "cc8")
    ):
        context_parts.append("=== SOC2 TYPE II CONTROLS ===")
        for _key, control in SOC2_CONTROLS.items():
            context_parts.append(f"\n{control['section']} — {control['name']}")
            context_parts.append(f"Requirement: {control['requirement']}")
            context_parts.append(f"How Agentiva enforces: {control['how_agentiva_enforces']}")

    if any(
        k in question_lower
        for k in ("pci", "payment", "credit card", "cardholder", "cvv")
    ):
        context_parts.append("=== PCI-DSS REQUIREMENTS ===")
        for _key, req in PCI_DSS_REQUIREMENTS.items():
            context_parts.append(f"\n{req['section']} — {req['name']}")
            context_parts.append(f"Requirement: {req['requirement']}")
            context_parts.append(f"How Agentiva enforces: {req['how_agentiva_enforces']}")

    if not context_parts:
        context_parts.append("Available compliance frameworks: HIPAA, SOC2 Type II, PCI-DSS.")
        context_parts.append("Ask specifically about HIPAA, SOC2, or PCI-DSS for detailed analysis.")

    return "\n".join(context_parts)


def get_evidence_queries(framework: str) -> Dict[str, str]:
    """Return SQL queries that provide evidence for compliance controls."""
    fw = framework.lower().strip()
    if fw == "hipaa":
        return {k: v["evidence_query"] for k, v in HIPAA_RULES.items()}
    if fw in ("soc2", "soc_2"):
        return {k: v["evidence_query"] for k, v in SOC2_CONTROLS.items()}
    if fw == "pci":
        return {k: v["evidence_query"] for k, v in PCI_DSS_REQUIREMENTS.items()}
    return {}
