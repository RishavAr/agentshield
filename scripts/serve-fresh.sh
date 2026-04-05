#!/usr/bin/env bash
# Free ports 8000 and 3001, then start the Agentiva API on 8000.
# Usage: from anywhere —  ~/agentshield/scripts/serve-fresh.sh
#    or:  ./scripts/serve-fresh.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source venv/bin/activate
elif [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

for port in 8000 3001; do
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti ":${port}" 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      echo "Stopping listener(s) on port ${port}: ${pids}"
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
done

exec agentiva serve --port 8000
