"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Line,
  LineChart,
} from "recharts";
import { PageHeader } from "@/components/page-header";
import { toast } from "@/components/toast-host";
import { getHttpApiBase, getWsBase } from "@/lib/api-base";

type AuditEntry = {
  action_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  agent_id: string;
  decision: string;
  risk_score: number;
  mode: string;
  mandatory?: boolean;
  timestamp: string;
};

type ShadowReport = {
  total_actions: number;
  by_tool: Record<string, number>;
  by_decision: Record<string, number>;
  avg_risk_score: number;
};

type AgentRow = {
  id: string;
  name: string;
  reputation_score: number;
  total_actions: number;
  blocked_actions: number;
  status: string;
  last_active?: string | null;
};

const API_BASE = getHttpApiBase();
const WS_BASE = getWsBase();

function mergeReportWithAction(prev: ShadowReport | null, row: AuditEntry): ShadowReport {
  const base: ShadowReport = prev ?? {
    total_actions: 0,
    by_tool: {},
    by_decision: {},
    avg_risk_score: 0,
  };
  const dec = row.decision;
  const tool = row.tool_name;
  const by_decision = { ...base.by_decision, [dec]: (base.by_decision[dec] ?? 0) + 1 };
  const by_tool = { ...base.by_tool, [tool]: (base.by_tool[tool] ?? 0) + 1 };
  const total = base.total_actions + 1;
  const sum = base.avg_risk_score * base.total_actions + row.risk_score;
  return {
    total_actions: total,
    by_tool,
    by_decision,
    avg_risk_score: total ? sum / total : 0,
  };
}

function wsPayloadToAuditEntry(raw: Record<string, unknown>): AuditEntry | null {
  const actionId = (raw.action_id ?? raw.id) as string | undefined;
  if (!actionId || typeof raw.tool_name !== "string") return null;
  return {
    action_id: actionId,
    tool_name: raw.tool_name,
    arguments: (raw.arguments as Record<string, unknown>) ?? {},
    agent_id: typeof raw.agent_id === "string" ? raw.agent_id : "default",
    decision: typeof raw.decision === "string" ? raw.decision : "shadow",
    risk_score: typeof raw.risk_score === "number" ? raw.risk_score : 0,
    mode: typeof raw.mode === "string" ? raw.mode : "shadow",
    timestamp: typeof raw.timestamp === "string" ? raw.timestamp : new Date().toISOString(),
  };
}

const DONUT_COLORS: Record<string, string> = {
  block: "#ef4444",
  shadow: "#f59e0b",
  allow: "#22c55e",
  approve: "#3b82f6",
  pending: "#64748b",
};

function useAnimatedNumber(target: number, duration = 900) {
  const [v, setV] = useState(0);
  useEffect(() => {
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      setV(Math.round(target * (0.2 + 0.8 * (1 - Math.pow(1 - p, 3)))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return v;
}

function bucketActionsForChart(entries: AuditEntry[], maxPoints = 24) {
  const map = new Map<string, number>();
  for (const a of entries) {
    const d = new Date(a.timestamp);
    if (Number.isNaN(d.getTime())) continue;
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:00`;
    map.set(key, (map.get(key) ?? 0) + 1);
  }
  const sorted = [...map.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(-maxPoints);
  return sorted.map(([t, c]) => ({ t: t.slice(5), count: c }));
}

function sparkFromSeries(data: { count: number }[]) {
  if (!data.length) return [{ i: 0, v: 0 }];
  return data.map((d, i) => ({ i, v: d.count }));
}

function relTime(iso: string): string {
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "unknown";
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export default function DashboardOverviewPage() {
  const [report, setReport] = useState<ShadowReport | null>(null);
  const [recentActions, setRecentActions] = useState<AuditEntry[]>([]);
  const [seriesSource, setSeriesSource] = useState<AuditEntry[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [mode, setMode] = useState("shadow");
  const [modeSetting, setModeSetting] = useState("shadow");
  const [riskThreshold, setRiskThreshold] = useState(0.7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [relTick, setRelTick] = useState(0);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [reportRes, auditRes, seriesRes, agentsRes, healthRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/report`),
        fetch(`${API_BASE}/api/v1/audit?limit=10`),
        fetch(`${API_BASE}/api/v1/audit?limit=500`),
        fetch(`${API_BASE}/api/v1/agents`),
        fetch(`${API_BASE}/health`),
      ]);

      if (!reportRes.ok || !auditRes.ok || !seriesRes.ok || !healthRes.ok) {
        throw new Error("Failed to load dashboard data");
      }

      const reportJson = (await reportRes.json()) as ShadowReport;
      const auditJson = (await auditRes.json()) as AuditEntry[];
      const seriesJson = (await seriesRes.json()) as AuditEntry[];
      const healthJson = (await healthRes.json()) as { mode: string; risk_threshold?: number };

      setReport(reportJson);
      setRecentActions(auditJson);
      setSeriesSource(seriesJson);
      setMode(healthJson.mode);
      setModeSetting(healthJson.mode);
      if (typeof healthJson.risk_threshold === "number") {
        setRiskThreshold(healthJson.risk_threshold);
      }
      if (agentsRes.ok) {
        setAgents((await agentsRes.json()) as AgentRow[]);
      }
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const id = setInterval(() => setRelTick((t) => t + 1), 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/actions`);
    ws.onmessage = (event) => {
      try {
        const raw = JSON.parse(event.data) as Record<string, unknown>;
        const row = wsPayloadToAuditEntry(raw);
        if (!row) return;
        setReport((prev) => mergeReportWithAction(prev, row));
        setRecentActions((prev) => {
          const next = [row, ...prev.filter((a) => a.action_id !== row.action_id)];
          return next.slice(0, 50);
        });
        setSeriesSource((prev) => [row, ...prev].slice(0, 800));
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, []);

  const decisions = report?.by_decision ?? {};
  const total = report?.total_actions ?? 0;
  const blocked = decisions.block ?? 0;
  const shadowed = decisions.shadow ?? 0;
  const allowed = (decisions.allow ?? 0) + (decisions.approve ?? 0);

  const blockPct = total ? Math.round((blocked / total) * 100) : 0;

  const nTotal = useAnimatedNumber(total);
  const nBlock = useAnimatedNumber(blocked);
  const nShadow = useAnimatedNumber(shadowed);
  const nAllow = useAnimatedNumber(allowed);

  const lineData = useMemo(() => bucketActionsForChart(seriesSource), [seriesSource]);
  const sparkData = useMemo(() => sparkFromSeries(lineData), [lineData]);

  const donutData = useMemo(() => {
    const d = decisions;
    return Object.entries(d)
      .filter(([, v]) => (v ?? 0) > 0)
      .map(([name, value]) => ({ name, value: value as number }));
  }, [decisions]);

  const topRisks = useMemo(() => {
    return [...seriesSource].sort((a, b) => b.risk_score - a.risk_score).slice(0, 5);
  }, [seriesSource]);

  const nextMode = useMemo(() => {
    if (mode === "shadow") return "live";
    if (mode === "live") return "approval";
    return "shadow";
  }, [mode]);

  async function toggleMode() {
    const response = await fetch(`${API_BASE}/api/v1/mode/${nextMode}`, { method: "POST" });
    if (response.ok) {
      setMode(nextMode);
      setModeSetting(nextMode);
      await loadData();
    }
  }

  async function applySecuritySettings() {
    try {
      const r = await fetch(`${API_BASE}/api/v1/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ risk_threshold: riskThreshold, mode: modeSetting }),
      });
      if (!r.ok) throw new Error(await r.text());
      setMode(modeSetting);
      await loadData();
      toast("Security settings applied — new intercepts use this mode and threshold.", "success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply settings");
    }
  }

  const blockRate = total ? blocked / total : 0;
  const isEmptyDashboard =
    !loading && report !== null && total === 0 && agents.length === 0;
  const showTuningBanner = !loading && report && !isEmptyDashboard && blockRate > 0.4;

  async function runDemoSeed() {
    try {
      const r = await fetch(`${API_BASE}/api/v1/demo/seed`, { method: "POST" });
      if (!r.ok) throw new Error((await r.text()) || "Demo seed failed");
      await loadData();
      toast("Demo data loaded", "success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo failed");
      toast(err instanceof Error ? err.message : "Demo failed", "error");
    }
  }

  if (loading && !report) {
    return (
      <div className="space-y-6">
        <PageHeader title="Overview" subtitle="Agentiva" breadcrumbs={[{ label: "Overview" }]} />
        <div className="grid animate-pulse gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton h-32 rounded-2xl" />
          ))}
        </div>
        <div className="skeleton h-72 rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="page-enter space-y-8 pb-12">
      <PageHeader
        title="Overview"
        subtitle="Preview deployments for AI agents"
        breadcrumbs={[{ label: "Overview" }]}
        actions={
          <button
            type="button"
            onClick={() => void loadData()}
            className="rounded-lg border border-[#30363d] bg-[#161b22] px-4 py-2 text-sm text-[#c9d1d9] transition hover:border-[#58a6ff]/50 hover:bg-[#1c2128]"
          >
            Refresh
          </button>
        }
      />

      {error ? (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
      ) : null}

      {showTuningBanner ? (
        <button
          type="button"
          onClick={() =>
            window.dispatchEvent(
              new CustomEvent("agentiva:openChat", { detail: { message: "help me tune policies" } }),
            )
          }
          className="w-full rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 to-transparent px-5 py-4 text-left text-amber-100 shadow-lg transition hover:border-amber-500/50"
        >
          <div className="text-sm font-semibold">High block rate — open policy tuning</div>
          <div className="mt-1 text-xs text-amber-200/80">Block rate: {Math.round(blockRate * 100)}%</div>
        </button>
      ) : null}

      {isEmptyDashboard ? (
        <section className="glass-card space-y-6 p-6">
          <div>
            <h2 className="text-xl font-semibold text-[#f8fafc]">Welcome to Agentiva</h2>
            <p className="mt-1 text-sm text-[#64748b]">Your dashboard is empty. Let&apos;s get started!</p>
          </div>
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-[#0a0f1e]/80 px-4 py-3">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#3b82f6] opacity-40" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#3b82f6]" />
            </span>
            <p className="text-sm text-[#94a3b8]">Waiting for your agent&apos;s first action…</p>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <Link
              href="/agents?register=1"
              className="glass-card-hover rounded-2xl border border-white/10 bg-[#131b2e]/60 p-5 transition hover:border-[#3b82f6]/40"
            >
              <p className="font-semibold text-[#f8fafc]">Register your first agent</p>
              <p className="mt-1 text-xs text-[#64748b]">Opens agent registration on the Agents page.</p>
            </Link>
            <div className="glass-card-hover rounded-2xl border border-white/10 bg-[#131b2e]/60 p-5 transition hover:border-emerald-500/40">
              <p className="font-semibold text-[#f8fafc]">Run the demo</p>
              <p className="mt-1 text-xs text-[#64748b]">From the repo root (with venv active):</p>
              <code className="mt-2 block rounded-lg border border-white/10 bg-[#0a0f1e] px-3 py-2 font-mono text-xs text-[#93c5fd]">
                python demo/paybot_demo.py
              </code>
              <button
                type="button"
                onClick={() => void runDemoSeed()}
                className="mt-3 w-full rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/20"
              >
                Or load sample data in one click
              </button>
            </div>
            <a
              href="https://github.com/RishavAr/agentiva/blob/main/README.md"
              target="_blank"
              rel="noreferrer"
              className="glass-card-hover rounded-2xl border border-white/10 bg-[#131b2e]/60 p-5 transition hover:border-violet-500/40"
            >
              <p className="font-semibold text-[#f8fafc]">Read the docs</p>
              <p className="mt-1 text-xs text-[#64748b]">Install, configure policies, and export compliance.</p>
            </a>
          </div>
        </section>
      ) : null}

      {isEmptyDashboard ? null : (
        <>
      <section className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
        <div className="glass-card glass-card-hover group relative overflow-hidden p-6" style={{ background: "linear-gradient(135deg, #1E3A5F, #0A1628)" }}>
          <p className="text-xs font-medium uppercase tracking-wider text-blue-200/80">Total actions</p>
          <p className="mt-2 text-5xl font-bold tabular-nums text-white">{nTotal}</p>
          <div className="mt-3 h-10 w-full min-w-0 opacity-80">
            <ResponsiveContainer width="100%" height={40}>
              <LineChart data={sparkData}>
                <Line type="monotone" dataKey="v" stroke="#58a6ff" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass-card glass-card-hover group relative overflow-hidden p-6" style={{ background: "linear-gradient(135deg, #4A1520, #1A0A0F)" }}>
          <p className="text-xs font-medium uppercase tracking-wider text-red-200/80">Blocked</p>
          <p className="mt-2 text-5xl font-bold tabular-nums text-red-300">{nBlock}</p>
          <p className="mt-1 inline-flex rounded-full bg-red-500/20 px-2 py-0.5 text-xs text-red-200">{blockPct}% of total</p>
        </div>

        <div className="glass-card glass-card-hover group relative overflow-hidden p-6" style={{ background: "linear-gradient(135deg, #3D3215, #1A150A)" }}>
          <p className="text-xs font-medium uppercase tracking-wider text-amber-200/80">Shadowed</p>
          <p className="mt-2 text-5xl font-bold tabular-nums text-amber-200">{nShadow}</p>
          <p className="mt-1 text-sm text-amber-200/60">Observed, not executed</p>
        </div>

        <div className="glass-card glass-card-hover group relative overflow-hidden p-6" style={{ background: "linear-gradient(135deg, #0A3D2A, #0A1A15)" }}>
          <p className="text-xs font-medium uppercase tracking-wider text-emerald-200/80">Allowed</p>
          <p className="mt-2 text-5xl font-bold tabular-nums text-emerald-200">{nAllow}</p>
          <p className="mt-1 text-sm text-emerald-200/60">Including approve</p>
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-[#8b949e]">
          Mode: <span className="font-medium text-[#c9d1d9]">{mode}</span>
        </p>
        <button
          type="button"
          onClick={() => void toggleMode()}
          className="rounded-lg border border-[#30363d] bg-[#161b22] px-4 py-2 text-sm text-[#c9d1d9] transition hover:bg-[#1c2128]"
        >
          Switch to {nextMode}
        </button>
      </div>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="glass-card xl:col-span-2 p-6">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[#8b949e]">Actions over time</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={lineData}>
                <defs>
                  <linearGradient id="fillAct" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1f6feb" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#1f6feb" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#21262d" strokeDasharray="3 3" />
                <XAxis dataKey="t" tick={{ fill: "#8b949e", fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fill: "#8b949e", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8 }}
                  labelStyle={{ color: "#c9d1d9" }}
                />
                <Area type="monotone" dataKey="count" stroke="#3b82f6" fill="url(#fillAct)" strokeWidth={2.5} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass-card p-6">
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[#8b949e]">Decisions</h3>
          <div className="h-64 w-full min-w-0 min-h-[16rem]">
            <ResponsiveContainer width="100%" height={256}>
              <PieChart>
                <Pie data={donutData} dataKey="value" nameKey="name" innerRadius={52} outerRadius={84} paddingAngle={3}>
                  {donutData.map((entry) => (
                    <Cell key={entry.name} fill={DONUT_COLORS[entry.name] ?? "#64748b"} />
                  ))}
                </Pie>
                <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" fill="#f8fafc" fontSize={24} fontWeight={700}>
                  {total}
                </text>
                <Tooltip
                  contentStyle={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="mt-2 space-y-1 text-xs text-[#8b949e]">
            {donutData.map((d) => (
              <li key={d.name} className="flex justify-between">
                <span className="capitalize">{d.name}</span>
                <span className="font-mono text-[#c9d1d9]">{d.value}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="glass-card p-6">
          <h3 className="mb-4 text-lg font-semibold text-[#f0f6fc]">Recent activity</h3>
          {recentActions.length === 0 ? (
            <p className="text-sm text-[#8b949e]">No actions yet.</p>
          ) : (
            <ul key={relTick} className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
              {recentActions.slice(0, 10).map((action, idx) => (
                <li
                  key={action.action_id}
                  className="glass-card glass-card-hover flex items-start justify-between gap-3 border-l-4 border-l-[#64748b] px-3 py-2"
                  style={{
                    borderLeftColor:
                      action.decision === "block" ? "#ef4444" : action.decision === "shadow" ? "#f59e0b" : "#10b981",
                    animation: `page-enter 280ms ease ${idx * 55}ms both`,
                  }}
                >
                  <div>
                    <p className="font-medium text-[#f0f6fc]">{action.tool_name}</p>
                    <p className="text-xs text-[#8b949e]">{relTime(action.timestamp)}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <DecisionBadge decision={action.decision} />
                    <span className="font-mono text-xs text-[#8b949e]">{(action.risk_score ?? 0).toFixed(2)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="glass-card p-6">
          <h3 className="mb-4 text-lg font-semibold text-[#f0f6fc]">Top risks</h3>
          {topRisks.length === 0 ? (
            <p className="text-sm text-[#8b949e]">No data.</p>
          ) : (
            <ul className="space-y-3">
              {topRisks.map((a) => (
                <li key={a.action_id} className="rounded-xl border border-[#30363d] bg-[#0d1117] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-[#f0f6fc]">{a.tool_name}</span>
                    <RiskBadge score={a.risk_score} />
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#21262d]">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-amber-500 to-red-500"
                      style={{ width: `${Math.min(100, Math.round(a.risk_score * 100))}%` }}
                    />
                  </div>
                  <p className="mt-1 text-xs text-[#8b949e]">{a.agent_id}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="glass-card p-6">
        <h3 className="mb-4 text-lg font-semibold text-[#f0f6fc]">Security Settings</h3>
        <div className="space-y-4">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-[#c9d1d9]">Risk threshold</label>
              <span className="font-mono text-sm text-[#79c0ff]">{riskThreshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={riskThreshold}
              onChange={(e) => setRiskThreshold(Number(e.target.value))}
              className="w-full accent-[#58a6ff]"
            />
            <p className="mt-1 text-xs text-[#8b949e]">
              In <span className="text-[#c9d1d9]">live</span> mode, policy allows with risk at or above this level are
              treated as blocks. In <span className="text-[#c9d1d9]">shadow</span>, policy blocks and high-risk allows
              are logged as shadow (observe). Existing audit rows do not change until new actions run.
            </p>
          </div>
          <div>
            <p className="mb-2 text-sm font-medium text-[#c9d1d9]">Mode</p>
            <div className="grid gap-2 md:grid-cols-3">
              {[
                { value: "shadow", label: "Shadow", desc: "Observe only" },
                { value: "live", label: "Live", desc: "Block automatically" },
                { value: "approval", label: "Approval", desc: "Human review for high-risk" },
              ].map((m) => (
                <label
                  key={m.value}
                  className={`cursor-pointer rounded-lg border p-3 text-sm ${
                    modeSetting === m.value
                      ? "border-[#1f6feb]/50 bg-[#1f6feb]/10"
                      : "border-[#30363d] bg-[#0d1117]"
                  }`}
                >
                  <input
                    type="radio"
                    name="modeSetting"
                    value={m.value}
                    checked={modeSetting === m.value}
                    onChange={(e) => setModeSetting(e.target.value)}
                    className="sr-only"
                  />
                  <p className="font-semibold text-[#f0f6fc]">{m.label}</p>
                  <p className="text-xs text-[#8b949e]">{m.desc}</p>
                </label>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={() => void applySecuritySettings()}
            className="rounded-lg bg-[#238636] px-4 py-2 text-sm font-semibold text-white hover:bg-[#2ea043]"
          >
            Apply Changes
          </button>
        </div>
      </section>

      <section className="glass-card p-6">
        <h3 className="mb-4 text-lg font-semibold text-[#f0f6fc]">Agent health</h3>
        {agents.length === 0 ? (
          <Link href="/agents" className="text-sm text-[#58a6ff] hover:underline">
            Register your first agent →
          </Link>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {agents.map((ag) => (
              <Link
                key={ag.id}
                href={`/agents?agent=${encodeURIComponent(ag.id)}`}
                className="rounded-xl border border-[#30363d] bg-[#0d1117] p-4 transition hover:border-[#58a6ff]/40 hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-[#f0f6fc]">{ag.name}</p>
                    <p className="font-mono text-xs text-[#79c0ff]">{ag.id}</p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      ag.status === "active" ? "bg-emerald-500/15 text-emerald-300" : "bg-zinc-500/20 text-zinc-300"
                    }`}
                  >
                    {ag.status}
                  </span>
                </div>
                <p className="mt-2 text-xs text-[#8b949e]">
                  Actions: {ag.total_actions} · Blocked: {ag.blocked_actions}
                  {ag.last_active ? ` · Last active: ${new Date(ag.last_active).toLocaleString()}` : ""}
                </p>
                {ag.total_actions > 0 && ag.blocked_actions / ag.total_actions > 0.4 ? (
                  <div className="mt-2 inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    High block rate
                  </div>
                ) : null}
              </Link>
            ))}
          </div>
        )}
      </section>
        </>
      )}
    </div>
  );
}

function DecisionBadge({ decision }: { decision: string }) {
  const c =
    decision === "block"
      ? "bg-red-500/20 text-red-200 ring-red-500/40"
      : decision === "allow" || decision === "approve"
        ? "bg-emerald-500/20 text-emerald-200 ring-emerald-500/40"
        : "bg-amber-500/20 text-amber-200 ring-amber-500/40";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${c}`}>
      {decision}
    </span>
  );
}

function RiskBadge({ score }: { score: number }) {
  const c = score > 0.7 ? "text-red-300" : score >= 0.4 ? "text-amber-300" : "text-emerald-300";
  return <span className={`font-mono text-sm font-semibold ${c}`}>{score.toFixed(2)}</span>;
}
