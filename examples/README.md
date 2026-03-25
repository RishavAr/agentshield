# Agentiva Examples

This folder contains runnable demos that showcase Agentiva in realistic workflows.

## Available Examples

- `live_demo.py`  
  End-to-end simulation of a LangChain-like agent making **100+** realistic actions across email, Slack, databases, Jira, finance, DevOps, APIs, customer data, and admin permissions — designed for the live dashboard feed.  
  Actions stream into the dashboard live feed over the Agentiva API.

- **`../demo/` — real SQLite + tool logs**  
  See `demo/README.md`: creates a real `demo.db` (Faker data), optional LangChain `StructuredTool` smoke, and `real_agent.py` modes `protected` (HTTP intercepts), `interactive`, `unprotected` (destructive SQL — confirms first), and `langchain-smoke`.

## Run the Live Demo

1. Start backend:

```bash
agentiva serve --port 8000 --mode shadow
```

2. Start dashboard (optional but recommended):

```bash
cd dashboard
npm install
npm run dev
```

3. Run the example:

```bash
venv/bin/python examples/live_demo.py
```

## Expected Outcome

- You should see `SHADOW` and `BLOCKED` decisions in terminal output.
- Dashboard live feed should update in near real-time.
- Audit log and report endpoints should reflect the full scenario sequence.
