import type { NextRequest } from "next/server";

const BACKEND = process.env.AGENTIVA_API_URL ?? "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, pathSegments: string[]) {
  const sub = pathSegments.length ? pathSegments.join("/") : "";
  const target = `${BACKEND}/api/${sub}${request.nextUrl.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const k = key.toLowerCase();
    if (k === "host" || k === "connection") return;
    headers.set(key, value);
  });

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };

  if (!["GET", "HEAD"].includes(request.method)) {
    const buf = await request.arrayBuffer();
    if (buf.byteLength > 0) {
      init.body = buf;
    }
  }

  const res = await fetch(target, init);

  const outHeaders = new Headers();
  res.headers.forEach((value, key) => {
    const k = key.toLowerCase();
    if (k === "transfer-encoding") return;
    outHeaders.set(key, value);
  });

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: outHeaders,
  });
}

type Ctx = { params: Promise<{ path?: string[] }> };

export async function GET(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path ?? []);
}

export async function POST(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path ?? []);
}

export async function DELETE(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path ?? []);
}

export async function PUT(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path ?? []);
}

export async function PATCH(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path ?? []);
}

export async function OPTIONS() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, DELETE, PUT, PATCH, OPTIONS",
      "Access-Control-Allow-Headers": "*",
    },
  });
}
