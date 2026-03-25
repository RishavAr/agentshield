"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { getHttpApiBase } from "@/lib/api-base";
import { toast } from "@/components/toast-host";

type AuditEntry = {
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
const PAGE_SIZE = 20;

function buildFilterParams(toolName: string, decision: string, minRisk: string) {
  const params = new URLSearchParams();
  if (toolName) params.set("tool_name", toolName);
  if (decision) params.set("decision", decision);
  if (minRisk) params.set("min_risk", minRisk);
  return params;
}

function buildExportQuery(exportStart: string, exportEnd: string) {
  const params = new URLSearchParams();
  if (exportStart) {
    params.set("start", new Date(`${exportStart}T00:00:00.000Z`).toISOString());
  }
  if (exportEnd) {
    params.set("end", new Date(`${exportEnd}T23:59:59.999Z`).toISOString());
  }
  return params.toString();
}

function riskBadgeClass(score: number) {
  if (score > 0.7) return "bg-red-500/20 text-red-200 ring-red-500/40";
  if (score >= 0.4) return "bg-amber-500/20 text-amber-200 ring-amber-500/40";
  return "bg-emerald-500/20 text-emerald-200 ring-emerald-500/40";
}

function riskDot(score: number) {
  if (score > 0.7) return "bg-red-400";
  if (score >= 0.4) return "bg-amber-400";
  return "bg-emerald-400";
}

function decisionPill(decision: string) {
  if (decision === "block") return "bg-red-500/15 text-red-200 ring-red-500/35";
  if (decision === "allow" || decision === "approve") return "bg-emerald-500/15 text-emerald-200 ring-emerald-500/35";
  if (decision === "shadow") return "bg-amber-500/15 text-amber-200 ring-amber-500/35";
  return "bg-slate-500/15 text-slate-200 ring-slate-500/35";
}

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [toolName, setToolName] = useState("");
  const [decision, setDecision] = useState("");
  const [minRisk, setMinRisk] = useState("");
  const [page, setPage] = useState(0);
  const [exportStart, setExportStart] = useState("");
  const [exportEnd, setExportEnd] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<string | null>(null);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    try {
      const fp = buildFilterParams(toolName, decision, minRisk);
      const q = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      });
      fp.forEach((v, k) => q.set(k, v));
      const [dataRes, countRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/audit?${q.toString()}`),
        fetch(`${API_BASE}/api/v1/audit/count?${fp.toString()}`),
      ]);
      const json = (await dataRes.json()) as AuditEntry[];
      setRows(Array.isArray(json) ? json : []);
      if (countRes.ok) {
        const c = (await countRes.json()) as { total: number };
        setTotal(typeof c.total === "number" ? c.total : null);
      } else {
        setTotal(null);
      }
    } finally {
      setLoading(false);
    }
  }, [decision, minRisk, page, toolName]);

  useEffect(() => {
    void loadAudit();
  }, [loadAudit]);

  async function onApplyFilters() {
    setPage(0);
    await loadAudit();
  }

  async function downloadPdf(kind: "soc2" | "hipaa" | "pci", filename: string) {
    const key = `${kind}-pdf`;
    setExporting(key);
    const q = buildExportQuery(exportStart, exportEnd);
    const path = `${API_BASE}/api/v1/compliance/${kind}/report${q ? `?${q}` : ""}`;
    try {
      const res = await fetch(path);
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      if (blob.type.includes("json") || blob.size < 100) {
        const t = await blob.text();
        throw new Error(t.slice(0, 200));
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast("Report generated", "success");
    } catch {
      toast("Generating report… falling back to JSON export", "info");
      try {
        const fb = buildExportQuery(exportStart, exportEnd);
        let url = `${API_BASE}/api/v1/compliance/soc2?`;
        if (fb) {
          url += fb;
        } else {
          const end = new Date();
          const start = new Date();
          start.setDate(start.getDate() - 30);
          url += `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`;
        }
        const fallback = await fetch(url);
        if (fallback.ok) {
          const data = await fallback.json();
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `agentiva-compliance-fallback.json`;
          a.click();
          URL.revokeObjectURL(url);
          toast("JSON report downloaded", "success");
        } else {
          toast("Export failed", "error");
        }
      } catch {
        toast("Export failed", "error");
      }
    } finally {
      setExporting(null);
    }
  }

  const startIdx = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const endIdx = page * PAGE_SIZE + rows.length;

  return (
    <div className="page-enter space-y-6 pb-12">
      <PageHeader title="Audit log" subtitle="Searchable history & compliance exports" breadcrumbs={[{ label: "Audit Log" }]} />

      <section className="glass-card p-5">
        <h3 className="mb-1 text-sm font-semibold text-[#f0f6fc]">Compliance export</h3>
        <p className="mb-4 text-xs text-[#8b949e]">
          PDF reports from persisted <code className="text-[#79c0ff]">action_logs</code>. Optional date range.
        </p>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-[#8b949e]">
            Start
            <input
              type="date"
              value={exportStart}
              onChange={(e) => setExportStart(e.target.value)}
              className="rounded-lg border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm text-[#f0f6fc]"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-[#8b949e]">
            End
            <input
              type="date"
              value={exportEnd}
              onChange={(e) => setExportEnd(e.target.value)}
              className="rounded-lg border border-[#30363d] bg-[#0d1117] px-2 py-1.5 text-sm text-[#f0f6fc]"
            />
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          {(
            [
              ["soc2", "SOC 2", "agentiva-soc2-report.pdf"],
              ["hipaa", "HIPAA", "agentiva-hipaa-report.pdf"],
              ["pci", "PCI-DSS", "agentiva-pci-report.pdf"],
            ] as const
          ).map(([k, label, file]) => (
            <button
              key={k}
              type="button"
              disabled={!!exporting}
              onClick={() => void downloadPdf(k, file)}
              className="inline-flex items-center gap-2 rounded-xl border border-[#334155] bg-[#131b2e] px-4 py-2 text-sm font-medium text-[#f0f6fc] transition hover:shadow-lg hover:shadow-blue-900/30 hover:border-[#3b82f6]/60 disabled:opacity-50"
            >
              {exporting === `${k}-pdf` ? (
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[#8b949e] border-t-transparent" />
              ) : null}
              Export {label}
            </button>
          ))}
        </div>
      </section>

      <section className="glass-card grid grid-cols-1 gap-3 p-4 md:grid-cols-5">
        <input
          value={toolName}
          onChange={(e) => setToolName(e.target.value)}
          placeholder="Tool name"
          className="rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm outline-none ring-0 focus:border-[#58a6ff]"
        />
        <select
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          className="rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm outline-none"
        >
          <option value="">All decisions</option>
          <option value="allow">allow</option>
          <option value="shadow">shadow</option>
          <option value="block">block</option>
          <option value="approve">approve</option>
          <option value="pending">pending</option>
        </select>
        <input
          value={minRisk}
          onChange={(e) => setMinRisk(e.target.value)}
          placeholder="Min risk (0-1)"
          className="rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm outline-none"
        />
        <button
          type="button"
          onClick={() => void onApplyFilters()}
          className="rounded-lg bg-[#1f6feb] px-3 py-2 text-sm font-medium text-white shadow-lg shadow-blue-900/20 transition hover:bg-[#388bfd]"
        >
          Apply filters
        </button>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-[#8b949e]">
        <span>
          {total !== null
            ? `Showing ${startIdx}-${endIdx} of ${total} actions`
            : loading
              ? "Loading…"
              : `Showing ${rows.length} actions`}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="rounded-lg border border-[#30363d] px-3 py-1.5 text-sm transition hover:bg-[#161b22] disabled:opacity-40"
            disabled={page === 0}
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border border-[#30363d] px-3 py-1.5 text-sm transition hover:bg-[#161b22] disabled:opacity-40"
            disabled={rows.length < PAGE_SIZE || (total !== null && endIdx >= total)}
          >
            Next
          </button>
        </div>
      </div>

      <section className="glass-card overflow-hidden">
        <table className="min-w-full text-sm">
          <thead className="bg-[#0d1117] text-left text-xs font-semibold uppercase tracking-wide text-[#8b949e]">
            <tr>
              <th className="px-4 py-3">Tool</th>
              <th className="px-4 py-3">Decision</th>
              <th className="px-4 py-3">Risk</th>
              <th className="px-4 py-3">Agent</th>
              <th className="px-4 py-3">Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-[#8b949e]">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-[#58a6ff]" />
                    Loading audit log…
                  </span>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td className="px-4 py-3 text-[#8b949e]" colSpan={5}>
                  No rows found.
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr
                  key={row.action_id}
                  className={`border-t border-[#30363d] transition hover:bg-[#1c2128] ${i % 2 === 1 ? "bg-[#0d1117]/80" : ""}`}
                >
                  <td className="px-4 py-3 font-medium text-[#f0f6fc]">{row.tool_name}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ring-1 ${decisionPill(row.decision)}`}>
                      {row.decision}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-mono text-xs ring-1 ${riskBadgeClass(row.risk_score)}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${riskDot(row.risk_score)}`} />
                      {row.risk_score.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-[#79c0ff]">{row.agent_id}</td>
                  <td className="px-4 py-3 text-[#8b949e]">{new Date(row.timestamp).toLocaleString()}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
