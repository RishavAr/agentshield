"use client";

import { useState } from "react";

const API_BASE = "http://localhost:8000";
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

export default function PoliciesPage() {
  const [policyYaml, setPolicyYaml] = useState(DEFAULT_POLICY);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

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
        setStatus("Policy endpoint not available yet. Draft saved locally.");
      } else {
        setStatus("Policy saved.");
      }
      localStorage.setItem("agentshield-policy-draft", policyYaml);
    } catch {
      localStorage.setItem("agentshield-policy-draft", policyYaml);
      setStatus("Saved locally. API unavailable.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm text-[#8b949e]">Policy Management</p>
        <h2 className="text-3xl font-semibold text-[#f0f6fc]">Policies</h2>
      </header>

      <section className="rounded-xl border border-[#30363d] bg-[#161b22] p-4">
        <textarea
          value={policyYaml}
          onChange={(e) => setPolicyYaml(e.target.value)}
          className="h-[520px] w-full resize-none rounded-md border border-[#30363d] bg-[#0d1117] p-3 font-mono text-sm text-[#c9d1d9] outline-none"
          placeholder="Enter YAML policy..."
        />
        <div className="mt-3 flex items-center justify-between">
          <button
            onClick={onSave}
            disabled={saving}
            className="rounded-md border border-[#30363d] bg-[#1f6feb] px-4 py-2 text-sm text-white hover:bg-[#388bfd] disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save Policy"}
          </button>
          {status && <span className="text-sm text-[#8b949e]">{status}</span>}
        </div>
      </section>
    </div>
  );
}
