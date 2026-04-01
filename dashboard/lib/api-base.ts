/**
 * HTTP API base for the dashboard.
 * - Default: same-origin `/api/v1/...` → proxied by `app/api/v1/[...path]/route.ts` to Agentiva (see `AGENTIVA_API_URL`).
 * - Override: set `NEXT_PUBLIC_API_BASE` to call the API directly (e.g. `http://127.0.0.1:8000`).
 */
export function getHttpApiBase(): string {
  const v = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (v) {
    return v.replace(/\/$/, "");
  }
  return "";
}

/**
 * WebSocket base when HTTP uses same-origin proxy (rewrites do not apply to WS).
 */
export function getWsBase(): string {
  const b = process.env.NEXT_PUBLIC_API_BASE;
  if (b && b.length > 0) {
    return b.replace(/^http/, "ws");
  }
  return process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8000";
}
