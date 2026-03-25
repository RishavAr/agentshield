# Agentiva real demo environment

This folder contains a **real SQLite** database and a **real_agent** script that exercises the same tool names Agentiva intercepts (`update_database`, `send_email`, `send_slack_message`, `run_shell_command`, `read_customer_data`).

- **Email** and **Slack** are **not** sent to real SMTP or Slack — side effects are **append-only logs in memory** (and SQLite for mail-like audit if you extend the demo).
- **SQL** in `--mode unprotected` runs **for real** against `demo/demo.db` (including destructive statements).

## Setup

From the repository root:

```bash
source venv/bin/activate
pip install -r requirements.txt
python demo/setup_demo_environment.py
```

This creates `demo/demo.db` with 100 customers and 50 transactions (Faker-generated realistic rows).

## Run Agentiva API

```bash
agentiva serve --port 8000
```

Optional: dashboard on `http://localhost:3000` (`cd dashboard && npm run dev`).

## Run the demo agent

```bash
# Intercept every tool call via Agentiva (recommended)
python demo/real_agent.py --mode protected --api http://localhost:8000

# Step pauses between scenarios
python demo/real_agent.py --mode interactive

# LangChain StructuredTool smoke (local SQLite only)
python demo/real_agent.py --mode langchain-smoke
```

### Unprotected mode (destructive)

This executes **real** `DROP` / `DELETE` / `UPDATE` against `demo.db`. You will be prompted to confirm.

```bash
python demo/real_agent.py --mode unprotected
```

Recreate the DB afterward with `python demo/setup_demo_environment.py`.

## Policy notes

Protected mode posts `update_database` (not `database_query`) to match `policies/default.yaml`. Extra rules cover demo-specific attacker domains and Slack/AWS secret strings.

## Environment

| Variable            | Meaning                    |
|---------------------|----------------------------|
| `AGENTIVA_API_BASE` | Default base URL for `--api` (fallback `http://localhost:8000`) |
