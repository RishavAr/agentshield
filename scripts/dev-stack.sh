#!/usr/bin/env bash
# Start Agentiva API (port 8000) + Next dashboard (port 3000) with matching proxy config.
# Usage: from repo root —  ./scripts/dev-stack.sh
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

PORT="${AGENTIVA_PORT:-8000}"
DASH_ENV="$ROOT/dashboard/.env.local"

if [[ ! -f "$DASH_ENV" ]]; then
  cat >"$DASH_ENV" <<EOF
# Auto-created by scripts/dev-stack.sh — dashboard proxies /api/v1/* to Agentiva
AGENTIVA_API_URL=http://127.0.0.1:${PORT}
EOF
  echo "Created $DASH_ENV"
else
  if ! grep -q '^AGENTIVA_API_URL=' "$DASH_ENV" 2>/dev/null; then
    echo "" >>"$DASH_ENV"
    echo "AGENTIVA_API_URL=http://127.0.0.1:${PORT}" >>"$DASH_ENV"
    echo "Appended AGENTIVA_API_URL to $DASH_ENV"
  fi
fi

if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "API already responding on port ${PORT}."
  if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"3000" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Dashboard already listening on port 3000 — open http://localhost:3000"
    echo "Stop the old dev server before starting another: kill \$(lsof -ti :3000)"
    exit 0
  fi
  echo "Starting dashboard only..."
  cd "$ROOT/dashboard"
  exec npm run dev
fi

echo "Starting Agentiva API on port ${PORT}..."
python3 -m agentiva.cli serve --port "${PORT}" &
API_PID=$!
cleanup() {
  kill "${API_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

if ! curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "API did not become healthy on port ${PORT}. Stop other servers using that port, then retry."
  exit 1
fi

if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"3000" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 3000 is already in use. Open http://localhost:3000 or stop it: kill \$(lsof -ti :3000)"
  echo "Stopping the API we just started (PID ${API_PID}) so you do not leave a stray process."
  kill "${API_PID}" 2>/dev/null || true
  exit 1
fi

echo "Starting dashboard (http://localhost:3000)..."
cd "$ROOT/dashboard"
trap - EXIT INT TERM
npm run dev
