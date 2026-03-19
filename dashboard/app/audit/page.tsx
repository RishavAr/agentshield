"use client";

import { useEffect, useState } from "react";
import { useCallback } from "react";

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

const API_BASE = "http://localhost:8000";
const PAGE_SIZE = 25;

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [toolName, setToolName] = useState("");
  const [decision, setDecision] = useState("");
  const [minRisk, setMinRisk] = useState("");
  const [page, setPage] = useState(0);

  const loadAudit = useCallback(async () => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (toolName) params.set("tool_name", toolName);
    if (decision) params.set("decision", decision);
    if (minRisk) params.set("min_risk", minRisk);

    const response = await fetch(`${API_BASE}/api/v1/audit?${params.toString()}`);
    const json = (await response.json()) as AuditEntry[];
    setRows(Array.isArray(json) ? json : []);
  }, [decision, minRisk, page, toolName]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadAudit();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadAudit]);

  async function onApplyFilters() {
    setPage(0);
    await loadAudit();
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm text-[#8b949e]">GET http://localhost:8000/api/v1/audit</p>
        <h2 className="text-3xl font-semibold text-[#f0f6fc]">Audit Log</h2>
      </header>

      <section className="grid grid-cols-1 gap-3 rounded-xl border border-[#30363d] bg-[#161b22] p-4 md:grid-cols-5">
        <input
          value={toolName}
          onChange={(e) => setToolName(e.target.value)}
          placeholder="Tool name"
          className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm outline-none"
        />
        <select
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm outline-none"
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
          className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm outline-none"
        />
        <button
          onClick={onApplyFilters}
          className="rounded-md border border-[#30363d] bg-[#1f6feb] px-3 py-2 text-sm text-white hover:bg-[#388bfd]"
        >
          Apply Filters
        </button>
      </section>

      <section className="overflow-hidden rounded-xl border border-[#30363d] bg-[#161b22]">
        <table className="min-w-full text-sm">
          <thead className="bg-[#0d1117] text-left text-[#8b949e]">
            <tr>
              <th className="px-4 py-3">Tool</th>
              <th className="px-4 py-3">Decision</th>
              <th className="px-4 py-3">Risk</th>
              <th className="px-4 py-3">Agent</th>
              <th className="px-4 py-3">Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-3 text-[#8b949e]" colSpan={5}>
                  No rows found.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.action_id} className="border-t border-[#30363d]">
                  <td className="px-4 py-3 text-[#f0f6fc]">{row.tool_name}</td>
                  <td className="px-4 py-3">{row.decision}</td>
                  <td className="px-4 py-3">{row.risk_score.toFixed(2)}</td>
                  <td className="px-4 py-3">{row.agent_id}</td>
                  <td className="px-4 py-3 text-[#8b949e]">{new Date(row.timestamp).toLocaleString()}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <div className="flex items-center gap-2">
        <button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          className="rounded-md border border-[#30363d] px-3 py-1 text-sm hover:bg-[#161b22]"
          disabled={page === 0}
        >
          Previous
        </button>
        <span className="text-sm text-[#8b949e]">Page {page + 1}</span>
        <button
          onClick={() => setPage((p) => p + 1)}
          className="rounded-md border border-[#30363d] px-3 py-1 text-sm hover:bg-[#161b22]"
          disabled={rows.length < PAGE_SIZE}
        >
          Next
        </button>
      </div>
    </div>
  );
}
