"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { getHttpApiBase } from "@/lib/api-base";
import { toast } from "@/components/toast-host";
import { Trash2, FlaskConical } from "lucide-react";

const API_BASE = getHttpApiBase();

const DEFAULT_POLICY = `version: 1
default_mode: shadow

rules:
  - name: block_external_email
    tool: send_email
    condition:
      field: arguments.to
      operator: not_contains
      value: "@yourcompany.com"
    action: block
    risk_score: 0.9
`;

type RuleCard = { id: string; name: string; raw: string };

type ParsedRuleFields = {
  name: string;
  tool: string;
  condition: string;
  action: string;
  risk?: string;
};

function parseRuleFields(raw: string): ParsedRuleFields {
  const name = raw.match(/name:\s*([^\n]+)/)?.[1]?.trim() ?? "—";
  const tool = raw.match(/^\s*tool:\s*(.+)$/m)?.[1]?.trim() ?? "—";
  const action = raw.match(/^\s*action:\s*(.+)$/m)?.[1]?.trim() ?? "—";
  const risk = raw.match(/^\s*risk_score:\s*(.+)$/m)?.[1]?.trim();
  const field = raw.match(/field:\s*([^\n]+)/)?.[1]?.trim();
  const operator = raw.match(/operator:\s*([^\n]+)/)?.[1]?.trim();
  const value = raw.match(/value:\s*([^\n]+)/)?.[1]?.trim();
  let condition = "—";
  if (field && operator && value !== undefined) {
    condition = `${field} · ${operator} · ${value}`;
  } else if (field) {
    condition = `${field} (see YAML for full condition)`;
  }
  return { name, tool, condition, action, risk };
}

function parseRulesFromYaml(yaml: string): RuleCard[] {
  const idx = yaml.indexOf("rules:");
  if (idx < 0) return [];
  const tail = yaml.slice(idx);
  const parts = tail.split(/\n  - name:/);
  const out: RuleCard[] = [];
  for (let i = 1; i < parts.length; i++) {
    const raw = "  - name:" + parts[i];
    const nameMatch = raw.match(/name:\s*([^\n]+)/);
    const name = (nameMatch?.[1] ?? `rule-${i}`).trim();
    out.push({ id: `rule-${i}-${name}`, name, raw: raw.trimEnd() });
  }
  return out;
}

function highlightYaml(src: string) {
  return src.split("\n").map((line, i) => {
    let cls = "text-[#8b949e]";
    if (/^\s*-\s*name:/.test(line)) cls = "text-[#ff7b72]";
    else if (/^\s*(tool|action|risk_score|condition|field|operator|value):/.test(line)) cls = "text-[#fde047]";
    return (
      <span key={i} className={`block ${cls}`}>
        {line}
      </span>
    );
  });
}

export default function PoliciesPage() {
  const [policyYaml, setPolicyYaml] = useState(DEFAULT_POLICY);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [rules, setRules] = useState<RuleCard[]>([]);
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/v1/policies`);
        if (res.ok) {
          const j = (await res.json()) as { policy_yaml: string };
          if (!cancelled && j.policy_yaml) {
            setPolicyYaml(j.policy_yaml);
          }
        }
      } catch {
        /* keep default */
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setRules(parseRulesFromYaml(policyYaml));
  }, [policyYaml]);

  async function onSave() {
    setSaving(true);
    setStatus("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/policies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ policy_yaml: policyYaml }),
      });
      if (!response.ok) {
        const t = await response.text();
        throw new Error(t || "Save failed");
      }
      setStatus("Policy saved and reloaded.");
      toast("Policy saved", "success");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Save failed");
      toast("Could not save policy", "error");
    } finally {
      setSaving(false);
    }
  }

  function removeRule(id: string) {
    const r = rules.find((x) => x.id === id);
    if (!r) return;
    const escaped = r.raw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`\\n?${escaped}`);
    setPolicyYaml((prev) => prev.replace(re, "\n").trim());
  }

  async function testRule(rule: RuleCard) {
    setTestResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/audit?limit=50`);
      const rows = (await res.json()) as { tool_name: string; decision: string; risk_score: number }[];
      const toolMatch = rule.raw.match(/tool:\s*(.+)/);
      const pat = toolMatch?.[1]?.trim() ?? "*";
      const hits = rows.filter((row) => {
        if (pat === "*" || pat.endsWith("*")) {
          const base = pat.replace("*", "");
          return row.tool_name.includes(base.replace("*", ""));
        }
        return row.tool_name === pat;
      });
      setTestResult(
        `Rule “${rule.name}”: ${hits.length} of ${rows.length} recent actions match tool pattern (${pat}).`,
      );
    } catch {
      setTestResult("Could not load recent actions for simulation.");
    }
  }

  return (
    <div className="page-enter space-y-8 pb-12">
      <PageHeader title="Policies" subtitle="YAML rules & simulation" breadcrumbs={[{ label: "Policies" }]} />

      <div className="rounded-xl border border-[#2e2918] bg-[#060504] px-4 py-3 text-sm text-[#8a8270]">
        <p className="text-[#e8e4d4]">
          <span className="font-medium text-[#faf6e8]">Two ways to fix blocks / allow exceptions:</span> edit YAML here and
          save, or open the <span className="text-[#facc15]">Security co-pilot</span> and say e.g.{" "}
          <span className="font-mono text-xs text-[#fde047]">&quot;help me tune policies&quot;</span>,{" "}
          <span className="font-mono text-xs text-[#fde047]">&quot;help me unblock&quot;</span>, or{" "}
          <span className="font-mono text-xs text-[#fde047]">&quot;add an allow rule for …&quot;</span>
          — then confirm with <span className="font-mono text-xs">apply policy</span> when it offers a fix.
        </p>
      </div>

      {loading ? (
        <div className="h-40 animate-pulse rounded-2xl bg-[#100e08]" />
      ) : (
        <section className="grid gap-4 lg:grid-cols-2">
          {rules.length === 0 ? (
            <p className="text-sm text-[#8a8270]">No rules parsed — check YAML structure.</p>
          ) : (
            rules.map((rule) => {
              const f = parseRuleFields(rule.raw);
              return (
              <article
                key={rule.id}
                className="glass-card glass-card-hover p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-[#f0f6fc]">{f.name}</h3>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => void testRule(rule)}
                      className="rounded-lg border border-[#2e2918] p-2 text-[#8a8270] hover:text-[#facc15]"
                      title="Test against recent actions"
                    >
                      <FlaskConical className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => removeRule(rule.id)}
                      className="rounded-lg border border-[#2e2918] p-2 text-[#8a8270] hover:text-red-400"
                      title="Remove from editor"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-[10px] font-semibold uppercase tracking-wide text-[#8b949e]">Tool pattern</dt>
                    <dd className="font-mono text-[#fde047]">{f.tool}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] font-semibold uppercase tracking-wide text-[#8b949e]">Condition</dt>
                    <dd className="text-[#c9d1d9]">{f.condition}</dd>
                  </div>
                  <div className="flex flex-wrap gap-4">
                    <div>
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-[#8b949e]">Action</dt>
                      <dd className="capitalize text-[#f0f6fc]">{f.action}</dd>
                    </div>
                    {f.risk ? (
                      <div>
                        <dt className="text-[10px] font-semibold uppercase tracking-wide text-[#8b949e]">Risk</dt>
                        <dd className="font-mono text-[#c9d1d9]">{f.risk}</dd>
                      </div>
                    ) : null}
                  </div>
                </dl>
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-[#8b949e] hover:text-[#facc15]">Raw YAML</summary>
                  <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-[#2e2918] bg-[#060504] p-3 font-mono text-[11px] leading-relaxed text-[#c9d1d9]">
                    {highlightYaml(rule.raw)}
                  </pre>
                </details>
              </article>
              );
            })
          )}
        </section>
      )}

      {testResult ? (
        <div className="rounded-xl border border-[#eab308]/35 bg-[#ca8a04]/12 px-4 py-3 text-sm text-[#c9d1d9]">{testResult}</div>
      ) : null}

      <section className="glass-card p-4">
        <h3 className="mb-2 text-sm font-semibold text-[#f0f6fc]">Full YAML</h3>
        <textarea
          value={policyYaml}
          onChange={(e) => setPolicyYaml(e.target.value)}
          className="h-[420px] w-full resize-none rounded-xl border border-[#2e2918] bg-[#080604] p-4 font-mono text-sm text-[#e8e4d4] outline-none focus:border-[#eab308]"
          spellCheck={false}
        />
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={saving}
            className="rounded-xl bg-[#ca8a04] px-5 py-2.5 text-sm font-semibold text-[#0a0805] shadow-lg shadow-amber-950/35 hover:bg-[#eab308] disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save policy"}
          </button>
          {status ? <span className="text-sm text-[#8a8270]">{status}</span> : null}
        </div>
      </section>
    </div>
  );
}
