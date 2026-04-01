#!/usr/bin/env bash
# Run the real-incidents demo with the repo venv (has httpx; avoids macOS "python" not found).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for VENV in "$ROOT/.venv" "$ROOT/venv"; do
  if [[ -x "$VENV/bin/python" ]]; then
    exec "$VENV/bin/python" "$ROOT/demo/real_incidents_demo.py" "$@"
  fi
done
echo "No virtualenv at .venv or venv with Python." >&2
echo "Create and install: python3 -m venv .venv && source .venv/bin/activate && pip install -e ." >&2
exit 1
