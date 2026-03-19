# AgentShield

**Preview deployments for AI agents.**

![Tests](https://img.shields.io/badge/tests-64%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-lightgrey)

AgentShield is an open-source runtime that intercepts, simulates, negotiates, approves, and rolls back AI agent actions before they hit production systems.

## 4-Line Example

```python
from agentshield import AgentShield
shield = AgentShield(mode="shadow")
tools = shield.protect([your_gmail_tool, your_slack_tool])
print(shield.get_audit_log())
```

## What AgentShield Catches

Output from `examples/live_demo.py` (12 realistic scenarios):

```text
[1/12] Agent sends internal team update
   SHADOW  | Risk: 0.10 | shadow (internal, low risk)
[2/12] Agent tries to email external investor with financials
   BLOCKED | Risk: 0.90 | BLOCKED (external + confidential)
[3/12] Agent posts to #general Slack channel
   SHADOW  | Risk: 0.30 | shadow (wide broadcast)
[4/12] Agent creates a routine bug ticket
   SHADOW  | Risk: 0.20 | shadow (low risk)
[5/12] Agent tries to DELETE production database table
   BLOCKED | Risk: 0.95 | BLOCKED (destructive SQL)
[6/12] Agent reads customer PII
   SHADOW  | Risk: 0.40 | shadow (sensitive data access)
[7/12] Agent calls unknown external API
   BLOCKED | Risk: 0.99 | BLOCKED (suspicious external endpoint)
[8/12] Agent tries to delete user accounts
   BLOCKED | Risk: 0.90 | BLOCKED (bulk destructive)
[9/12] Agent attempts unauthorized fund transfer
   BLOCKED | Risk: 0.95 | BLOCKED (financial + external)
[10/12] Agent creates high-priority security ticket
   SHADOW  | Risk: 0.20 | shadow (internal, but high priority)
[11/12] Agent sends password reset to user
   SHADOW  | Risk: 0.10 | shadow (contains credential)
[12/12] Agent posts deployment status to private channel
   SHADOW  | Risk: 0.30 | shadow (normal operation)
```

## Dashboard Screenshots

Placeholders for README visuals:

- `docs/screenshots/overview.png`
- `docs/screenshots/live-feed.png`
- `docs/screenshots/audit-log.png`
- `docs/screenshots/negotiation.png`

## Installation

### pip install

```bash
pip install agentshield
agentshield serve --port 8000 --mode shadow
```

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Backend: [http://localhost:8000](http://localhost:8000)  
Dashboard: [http://localhost:3000](http://localhost:3000)

### From Source

```bash
git clone https://github.com/your-org/agentshield.git
cd agentshield
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn agentshield.api.server:app --reload --port 8000
```

## Quick Start

1. Start backend:
   - `agentshield serve --port 8000 --mode shadow`
2. Start dashboard:
   - `cd dashboard && npm install && npm run dev`
3. Run live demo:
   - `agentshield demo`
4. Open:
   - `http://localhost:3000/live`

## Features

- **Shadow Mode**: preview actions without execution.
- **Policy Engine**: YAML-based allow/shadow/block enforcement.
- **Negotiation Protocol**: blocked actions return explanation + safe alternatives.
- **Retry Flow**: agents resubmit modified actions through negotiation chain.
- **Simulation Engine**: human-readable diffs before execution.
- **Rollback Engine**: undo plans for reversible actions.
- **Smart Risk Scoring**: deterministic multi-signal risk model.
- **Audit + Metrics**: structured logs, filters, and API metrics.
- **Realtime Dashboard**: WebSocket live feed for intercepted actions.

## Architecture (ASCII)

```text
                +----------------------+
                |   LangChain Agent    |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |     AgentShield      |
                |  Interceptor Layer   |
                +----+---------+-------+
                     |         |
                     v         v
          +----------------+  +------------------+
          | Policy + Risk  |  | Simulation/Undo  |
          | (Rules+Scorer) |  | (Diff+Rollback)  |
          +--------+-------+  +---------+--------+
                   |                    |
                   v                    v
              +-------------------------------+
              | API + Negotiation + Retry     |
              | FastAPI / WebSocket / Metrics |
              +-------------------------------+
                          |
                          v
              +-------------------------------+
              | DB + Dashboard + Audit Trail  |
              +-------------------------------+
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for:
- setup instructions
- coding standards
- test expectations
- PR workflow

## License

Apache 2.0. See [`LICENSE`](LICENSE).
