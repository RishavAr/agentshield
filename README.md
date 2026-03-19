# AgentShield

**Preview deployments for AI agents.**

AgentShield is an open-source runtime that intercepts, previews, approves, and rolls back AI agent actions before they touch production.

## Hero Example

```python
from agentshield import AgentShield
shield = AgentShield(mode="shadow")
tools = shield.protect([your_gmail_tool, your_slack_tool])
print(shield.get_audit_log())
```

## Features

- Shadow Mode
- Dry-Run Simulation
- Approval Workflows
- Rollback
- Audit Log
