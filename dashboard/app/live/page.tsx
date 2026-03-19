"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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

function decisionStyles(decision: string) {
  if (decision === "allow") return "border-green-500/40 bg-green-500/10 text-green-300";
  if (decision === "block") return "border-red-500/40 bg-red-500/10 text-red-300";
  return "border-amber-500/40 bg-amber-500/10 text-amber-300";
}

export default function LiveFeedPage() {
  const [actions, setActions] = useState<ActionFeedItem[]>([]);
  const [status, setStatus] = useState("connecting");
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws/actions");
    ws.onopen = () => setStatus("connected");
    ws.onclose = () => setStatus("disconnected");
    ws.onerror = () => setStatus("error");
    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as ActionFeedItem;
        setActions((prev) => [...prev, parsed]);
      } catch {
        // Ignore malformed frames.
      }
    };
    return () => ws.close();
  }, []);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [actions]);

  const connectionColor = useMemo(() => {
    if (status === "connected") return "text-green-300";
    if (status === "connecting") return "text-amber-300";
    return "text-red-300";
  }, [status]);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm text-[#8b949e]">WebSocket: ws://localhost:8000/ws/actions</p>
          <h2 className="text-3xl font-semibold text-[#f0f6fc]">Live Feed</h2>
        </div>
        <span className={`text-sm uppercase ${connectionColor}`}>{status}</span>
      </header>

      <div
        ref={listRef}
        className="h-[calc(100vh-180px)] space-y-3 overflow-y-auto rounded-xl border border-[#30363d] bg-[#161b22] p-4"
      >
        {actions.length === 0 ? (
          <p className="text-[#8b949e]">Waiting for intercepted actions...</p>
        ) : (
          actions.map((action) => {
            const pct = Math.max(0, Math.min(100, Math.round(action.risk_score * 100)));
            return (
              <article key={action.action_id} className="rounded-lg border border-[#30363d] bg-[#0d1117] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="font-medium text-[#f0f6fc]">{action.tool_name}</h3>
                  <span className={`rounded-md border px-2 py-1 text-xs ${decisionStyles(action.decision)}`}>
                    {action.decision}
                  </span>
                </div>

                <div className="mb-3">
                  <div className="mb-1 flex justify-between text-xs text-[#8b949e]">
                    <span>Risk Score</span>
                    <span>{action.risk_score.toFixed(2)}</span>
                  </div>
                  <div className="h-2 rounded-full bg-[#21262d]">
                    <div className="h-2 rounded-full bg-[#1f6feb]" style={{ width: `${pct}%` }} />
                  </div>
                </div>

                <details className="rounded-md border border-[#30363d] bg-[#161b22] p-2">
                  <summary className="cursor-pointer text-sm text-[#79c0ff]">Arguments</summary>
                  <pre className="mt-2 overflow-x-auto text-xs text-[#c9d1d9]">
                    {JSON.stringify(action.arguments, null, 2)}
                  </pre>
                </details>
                <p className="mt-3 text-xs text-[#8b949e]">{new Date(action.timestamp).toLocaleString()}</p>
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}
