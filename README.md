# Agentiva

**Preview deployments for AI agents.**

See what your AI agent would do before it does it.

[![Tests](https://img.shields.io/badge/tests-24%2C599%20passing-brightgreen)]()
[![OWASP](https://img.shields.io/badge/OWASP%20LLM%20Top%2010-100%25-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)]()

> litellm was compromised March 24, 2026 — SSH keys, AWS credentials, and database passwords stolen from 97M monthly downloads.
> Agentiva catches this class of attack at the action layer.

## Quick start (2 minutes)

```bash
pip install agentiva
agentiva serve --port 8000
# Open localhost:3000 for the dashboard (from repo: cd dashboard && npm run dev)
```

## Protect your agent (3 lines)

```python
from agentiva import Agentiva

shield = Agentiva(mode="shadow")
tools = shield.protect([your_existing_tools])

# Your agent works exactly the same.
# Every action is intercepted, scored, and logged.
```

## Run the demo

```bash
# See 4 real incident recreations
python demo/real_incidents_demo.py

# See PayBot (fintech startup) demo
python demo/paybot_demo.py

# See proof: before vs after comparison
python demo/proof_demo.py
```

Or use the project venv so dependencies resolve: `source .venv/bin/activate` then the commands above.

## What it catches

Tested against real-world incidents:

- **litellm supply chain attack** (March 2026) — credential exfiltration blocked
- **Amazon Kiro** (December 2025) — infrastructure destruction blocked
- **Microsoft Copilot** (January 2026) — zero-click data theft blocked
- **Replit agent** (2026) — mass record deletion blocked

## Verified results

| Benchmark | Result |
|-----------|--------|
| Agentiva test suite | 24,599 tests passing |
| OWASP LLM Top 10 | 21/21 (100%) |
| DeepTeam (Confident AI) | 38/47 (80.85%) |
| Garak (NVIDIA) | 2,500 probes scanned |
| PyRIT (Microsoft) | 9/9 scenarios completed |

Run benchmarks yourself:

```bash
python -m pytest tests/ -m "slow or not slow"  # Full test suite
python benchmarks/run_benchmark.py              # OWASP + incidents
python benchmarks/run_all_benchmarks.py         # All frameworks
```

## Five operating modes

| Mode | What it does |
|------|--------------|
| Shadow | Observe without executing |
| Simulation | Preview impact before acting |
| Approval | Human-in-the-loop for risky actions |
| Negotiation | Agent learns to self-correct |
| Rollback | Undo what the agent did |

## Dashboard

Real-time monitoring at localhost:3000:

- **Overview** — stats, charts, recent activity
- **Live Feed** — actions streaming via WebSocket
- **Audit Log** — searchable history with compliance exports
- **Agents** — registry with reputation and kill switch
- **Policies** — YAML rule editor
- **Security Co-pilot** — ask questions about your agent's behavior

## Security co-pilot

Ask naturally:

- "What was blocked?" → real data from your audit log
- "Why was send_email blocked?" → specific tool analysis
- "Is this HIPAA compliant?" → compliance check with regulation citations
- "Is my agent safe for production?" → honest assessment

Basic mode works without any API key. Add `OPENROUTER_API_KEY` for Claude-powered deep analysis via OpenRouter.

## Works with

LangChain, CrewAI, OpenAI Agents SDK, Anthropic, MCP Protocol, or any custom agent via REST API.

## Compliance-ready evidence

Generates audit trails aligned with:

- **HIPAA** — PHI access logs per 45 CFR § 164.312
- **SOC2** — Evidence for CC6-CC8 controls
- **PCI-DSS** — Cardholder data monitoring per Req 3, 7, 10

Note: Agentiva helps prepare for compliance audits. Certification requires a third-party assessor.

## Pricing

| Tier | Price | Agents |
|------|-------|--------|
| Free | $0/forever | 1 agent |
| Pro | $18/month | Up to 3 |
| Team | $54/month | Unlimited |
| Enterprise | Custom | Custom |

Self-hosted is free forever. Cloud dashboard on waitlist.

## Architecture

```
┌────────────────────┐
│  AI Agent          │  LangChain · CrewAI · OpenAI · MCP · custom tools
└─────────┬──────────┘
          │ tool_call
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AGENTIVA API (FastAPI)                        │
│  /api/v1/intercept · /api/v1/audit · /api/v1/chat · WebSocket feed   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
┌──────────────────────┐                 ┌──────────────────────┐
│  Interceptor         │                 │  Shield Chat          │
│  PolicyEngine (YAML) │                 │  Sessions + messages  │
│  SmartRiskScorer     │                 │  (SQLite persistence) │
│  PHI detector        │                 │  + optional LLM layer │
│  Behavior / drift    │                 └──────────┬────────────┘
└──────────┬───────────┘                            │
           │                                        │
           ▼                                        ▼
┌──────────────────────┐                 ┌──────────────────────┐
│  Modes               │                 │  Compliance KB        │
│  Shadow · Approve ·  │                 │  HIPAA · SOC 2 ·      │
│  Live · Negotiation  │                 │  PCI-DSS citations +  │
│  Simulator · Rollback│                 │  evidence SQL hooks   │
└──────────┬───────────┘                 └──────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Persistence: action_logs (audit) · agent registry · approvals ·     │
│  chat_sessions / chat_messages                                       │
└─────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐
│  Tools / APIs        │  Email · DB · Slack · shell · payments…
└──────────────────────┘
```

## API reference (short)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check + mode + risk threshold |
| `/api/v1/intercept` | POST | Intercept an agent action |
| `/api/v1/audit` | GET | Query audit log |
| `/api/v1/report` | GET | Summary report |
| `/api/v1/settings` | PUT | Runtime mode + risk threshold |
| `/ws/actions` | WebSocket | Real-time action stream |

Full OpenAPI at `http://localhost:8000/docs`.

## Testing

```bash
python -m pytest tests/ -q
python -m pytest tests/ -m "slow or not slow" -q
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Built by

**[Rishav Aryan](https://rishavar.github.io)** — ML Engineer, George Mason University

[GitHub](https://github.com/RishavAr) · [Twitter](https://twitter.com/RishavAr)
