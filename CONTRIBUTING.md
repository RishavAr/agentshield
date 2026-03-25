# Contributing to Agentiva

Thanks for contributing. Agentiva is building safety infrastructure for AI agents, so quality and reproducibility matter.

## Development Setup

```bash
git clone https://github.com/your-org/agentiva.git
cd agentiva
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Optional dashboard setup:

```bash
cd dashboard
npm install
```

## Running Tests

```bash
venv/bin/python -m pytest -q
```

Before opening a PR:

- run full test suite
- add/update tests for all behavior changes
- ensure no failing lint errors in changed files

## Coding Guidelines

- Keep changes scoped and reviewable.
- Prefer deterministic logic for safety-critical decisions.
- Document new APIs and user-facing behavior.
- Avoid breaking existing public interfaces unless absolutely necessary.
- Add clear failure messages and structured error responses.

## Pull Request Checklist

- [ ] Tests added/updated
- [ ] `pytest` passes locally
- [ ] README/docs updated if behavior changed
- [ ] New env vars added to `.env.example`
- [ ] New dependencies justified and added to packaging metadata

## Commit and Branching

- Use descriptive commit messages.
- Keep commits focused by concern (API, scoring, docs, etc.).
- Rebase/squash as needed before merge.

## Security and Responsible Disclosure

If you discover a critical vulnerability (policy bypass, escalation flaw, data leakage), do not file a public issue first. Contact maintainers privately.
