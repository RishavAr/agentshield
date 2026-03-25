import { NextResponse } from "next/server";

const BACKEND = process.env.AGENTIVA_API_URL ?? "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/health`, { cache: "no-store" });
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable", backend: BACKEND }, { status: 502 });
  }
}
