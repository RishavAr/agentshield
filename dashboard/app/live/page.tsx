"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { getHttpApiBase, getWsBase } from "@/lib/api-base";

type ActionFeedItem = {
  action_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  agent_id: string;
  decision: string;
  risk_score: number;
  mode: string;
  timestamp: string;
};

const API_BASE = getHttpApiBase();
const WS_BASE = getWsBase();

function relTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s} seconds ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.floor(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

function borderForDecision(d: string) {
  if (d === "block") return "border-l-red-500";
  if (d === "allow" || d === "approve") return "border-l-emerald-500";
  return "border-l-amber-400";
}

export default function LiveFeedPage() {
  const [actions, setActions] = useState<ActionFeedItem[]>([]);
  const [status, setStatus] = useState("connecting");
  const [filter, setFilter] = useState<"all" | "block" | "shadow" | "allow">("all");
  const [soundOn, setSoundOn] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const prevBlocked = useRef(0);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/actions`);
    ws.onopen = () => setStatus("connected");
    ws.onclose = () => setStatus("disconnected");
    ws.onerror = () => setStatus("error");
    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as ActionFeedItem;
        setActions((prev) => [parsed, ...prev].slice(0, 50));
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, []);

  useEffect(() => {
    const blocked = actions.filter((a) => a.decision === "block").length;
    if (soundOn && blocked > prevBlocked.current) {
      try {
        const ctx = new AudioContext();
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.connect(g);
        g.connect(ctx.destination);
        o.frequency.value = 880;
        g.gain.value = 0.05;
        o.start();
        setTimeout(() => {
          o.stop();
          void ctx.close();
        }, 120);
      } catch {
        /* ignore */
      }
    }
    prevBlocked.current = blocked;
  }, [actions, soundOn]);

  const filtered = useMemo(() => {
    if (filter === "all") return actions;
    if (filter === "allow") return actions.filter((a) => a.decision === "allow" || a.decision === "approve");
    return actions.filter((a) => a.decision === filter);
  }, [actions, filter]);

  const chips: { id: typeof filter; label: string }[] = [
    { id: "all", label: "All" },
    { id: "block", label: "Blocked" },
    { id: "shadow", label: "Shadowed" },
    { id: "allow", label: "Allowed" },
  ];

  return (
    <div className="page-enter space-y-6 pb-12">
      <PageHeader
        title="Live feed"
        subtitle="Real-time WebSocket stream"
        breadcrumbs={[{ label: "Live Feed" }]}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {chips.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setFilter(c.id)}
              className={`rounded-full px-4 py-1.5 text-xs font-semibold uppercase tracking-wide transition ${
                filter === c.id
                  ? "bg-[#1f6feb] text-white shadow-lg shadow-blue-900/30"
                  : "border border-[#30363d] bg-[#161b22] text-[#8b949e] hover:border-[#58a6ff]/40"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-[#8b949e]">
          <input type="checkbox" checked={soundOn} onChange={(e) => setSoundOn(e.target.checked)} className="rounded" />
          Sound on block
        </label>
      </div>

      <div className="glass-card flex items-center gap-3 px-4 py-3">
        <span className="relative flex h-3 w-3">
          {status === "connected" ? (
            <>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-500" />
            </>
          ) : (
            <span className="relative inline-flex h-3 w-3 rounded-full bg-amber-500" />
          )}
        </span>
        <span className="text-sm font-semibold uppercase tracking-wide text-[#c9d1d9]">
          {status === "connected" ? "Connected" : status}
        </span>
        <span className="text-xs text-[#8b949e]">{WS_BASE}/ws/actions</span>
      </div>

      <div ref={listRef} className="glass-card max-h-[calc(100vh-280px)] space-y-3 overflow-y-auto p-4">
        {filtered.length === 0 && actions.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
            <div className="relative h-32 w-32">
              <div className="absolute inset-0 animate-pulse rounded-full bg-gradient-to-br from-[#1f6feb]/30 to-purple-600/20 blur-xl" />
              <div className="relative flex h-full w-full items-center justify-center rounded-full border border-[#30363d] bg-[#161b22] text-4xl">
                ⚡
              </div>
            </div>
            <div className="max-w-md space-y-2">
              <p className="text-lg font-medium text-[#f0f6fc]">Waiting for actions</p>
              <p className="text-sm text-[#8b949e]">
                No actions yet. Run the demo to see Agentiva in action:
              </p>
              <code className="block rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2 text-left font-mono text-xs text-[#79c0ff]">
                python demo/real_agent.py --mode protected
              </code>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-[#8b949e]">No items match this filter.</p>
        ) : (
          filtered.map((action) => {
            const pct = Math.max(0, Math.min(100, Math.round(action.risk_score * 100)));
            const open = expanded === action.action_id;
            return (
              <article
                key={action.action_id}
                className={`glass-card glass-card-hover rounded-xl border-l-4 p-4 ${borderForDecision(
                  action.decision,
                )}`}
                style={{ animation: "slide-in-right 230ms ease-out both" }}
              >
                <button type="button" className="w-full text-left" onClick={() => setExpanded(open ? null : action.action_id)}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="text-base font-bold text-[#f0f6fc]">{action.tool_name}</p>
                      <span className="inline-block rounded-full bg-[#21262d] px-2 py-0.5 font-mono text-[11px] text-[#79c0ff]">
                        {action.agent_id}
                      </span>
                    </div>
                    <div className="text-right">
                      <DecisionPill decision={action.decision} />
                      <p className="mt-1 text-xs text-[#8b949e]">{relTime(action.timestamp)}</p>
                    </div>
                  </div>
                  <div className="mt-3">
                    <div className="mb-1 flex justify-between text-xs text-[#8b949e]">
                      <span>Risk</span>
                      <span className="font-mono">{action.risk_score.toFixed(2)}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-[#21262d]">
                      <div
                        className={`h-2 rounded-full ${pct > 70 ? "bg-red-500" : pct >= 40 ? "bg-amber-500" : "bg-emerald-500"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </button>
                {open ? (
                  <pre className="mt-3 max-h-48 overflow-auto rounded-lg border border-[#30363d] bg-[#0d1117] p-3 font-mono text-xs text-[#c9d1d9]">
                    {JSON.stringify(action.arguments, null, 2)}
                  </pre>
                ) : null}
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}

function DecisionPill({ decision }: { decision: string }) {
  const cls =
    decision === "block"
      ? "bg-red-500/20 text-red-200 ring-red-500/40"
      : decision === "allow" || decision === "approve"
        ? "bg-emerald-500/20 text-emerald-200 ring-emerald-500/40"
        : "bg-amber-500/20 text-amber-200 ring-amber-500/40";
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ring-1 ${cls}`}>
      {decision}
    </span>
  );
}
