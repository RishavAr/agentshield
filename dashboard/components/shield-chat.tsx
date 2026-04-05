"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import { Menu, MessageCircle, Pencil, Send, Shield, X } from "lucide-react";

import { getHttpApiBase } from "@/lib/api-base";

const API_BASE = getHttpApiBase();

type ChatPayload = { answer: string; suggestions: string[] };

const FENCE_RE = /```[\s\S]*?```/g;

function sanitizeAnswer(text: string): string {
  const clean = (text || "").replace(FENCE_RE, "").trim();
  const lines = clean.split("\n").filter((line) => {
    const t = line.trim();
    if (!t) return true;
    if ((t.startsWith("{") && t.endsWith("}")) || (t.startsWith("[") && t.endsWith("]"))) return false;
    if (t.includes('"hint"') || t.includes("'hint'")) return false;
    return true;
  });
  return lines.join("\n").trim();
}

function riskColor(score: number): string {
  if (score > 0.7) return "text-[#ef4444]";
  if (score >= 0.4) return "text-[#f59e0b]";
  return "text-[#22c55e]";
}

function renderNumbers(segment: string): ReactNode[] {
  const out: ReactNode[] = [];
  const numRe = /\b\d+(?:\.\d+)?\b/g;
  let last = 0;
  for (const m of segment.matchAll(numRe)) {
    const idx = m.index ?? 0;
    const raw = m[0];
    if (idx > last) out.push(segment.slice(last, idx));
    out.push(<strong key={`${idx}-${raw}`}>{raw}</strong>);
    last = idx + raw.length;
  }
  if (last < segment.length) out.push(segment.slice(last));
  return out;
}

/** Backticks + risk highlighting (no ** — caller splits bold first). */
function renderCodeAndRisk(part: string): ReactNode[] {
  const out: ReactNode[] = [];
  const parts = part.split("`");
  for (let i = 0; i < parts.length; i++) {
    const segment = parts[i];
    if (!segment) continue;
    if (i % 2 === 1) {
      out.push(
        <span key={`code-${i}`} className="rounded bg-[#1a170f] px-1 font-mono text-[#c9d1d9]">
          {segment}
        </span>,
      );
    } else {
      const riskRe = /\b(risk\s*[:=]?\s*)(0(?:\.\d+)?|1(?:\.0+)?)\b/gi;
      let last = 0;
      for (const m of segment.matchAll(riskRe)) {
        const idx = m.index ?? 0;
        const full = m[0];
        const v = parseFloat(m[2]);
        if (idx > last) out.push(...renderNumbers(segment.slice(last, idx)));
        const prefix = m[1] ?? "risk: ";
        out.push(
          <span key={`risk-${idx}`}>
            {prefix}
            <span className={riskColor(v)}>
              <strong>{m[2]}</strong>
            </span>
          </span>,
        );
        last = idx + full.length;
      }
      if (last < segment.length) out.push(...renderNumbers(segment.slice(last)));
    }
  }
  return out;
}

/** Markdown-style **bold**, inline `code`, and risk/number emphasis. */
function renderInline(text: string): ReactNode[] {
  const boldChunks = text.split(/\*\*/);
  const out: ReactNode[] = [];
  for (let i = 0; i < boldChunks.length; i++) {
    const chunk = boldChunks[i];
    if (chunk === undefined) continue;
    if (i % 2 === 1) {
      out.push(
        <strong key={`md-bold-${i}`} className="font-semibold text-[#f0f6fc]">
          {renderCodeAndRisk(chunk)}
        </strong>,
      );
    } else {
      out.push(...renderCodeAndRisk(chunk));
    }
  }
  return out;
}

function FormattedAnswer({ text }: { text: string }) {
  const clean = sanitizeAnswer(text);
  if (!clean) return null;
  const lines = clean.split("\n");
  const nodes: ReactNode[] = [];
  const bulletRe = /^\s*[-*•]\s+/;
  const numberedRe = /^\s*\d+\.\s+/;
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) {
      i++;
      continue;
    }
    if (trimmed.startsWith("- name:")) {
      const yamlLines: string[] = [];
      while (i < lines.length) {
        const raw = lines[i];
        const t = raw.trim();
        if (!t) {
          yamlLines.push(raw);
          i++;
          continue;
        }
        if (t.startsWith("- name:") || raw.startsWith("  ") || raw.startsWith("\t")) {
          yamlLines.push(raw);
          i++;
          continue;
        }
        break;
      }
      nodes.push(
        <pre
          key={`yaml-${i}`}
          className="mt-2 whitespace-pre-wrap rounded border border-[#2e2918] bg-[#060504] p-2 font-mono text-[11px] leading-relaxed text-[#c9d1d9]"
        >
          {yamlLines.join("\n")}
        </pre>,
      );
      continue;
    }
    if (bulletRe.test(trimmed) || numberedRe.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length) {
        const t = lines[i].trim();
        if (!t || !(bulletRe.test(t) || numberedRe.test(t))) break;
        items.push(t.replace(bulletRe, "").replace(numberedRe, ""));
        i++;
      }
      nodes.push(
        <ul key={`ul-${i}`} className="mt-2 list-disc space-y-1 pl-5">
          {items.map((it, idx) => (
            <li key={`${i}-${idx}`} className="break-words">
              {renderInline(it)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }
    nodes.push(
      <p key={`p-${i}`} className="whitespace-pre-wrap leading-relaxed">
        {renderInline(trimmed)}
      </p>,
    );
    i++;
  }
  return <>{nodes}</>;
}

type UserMsg = { id: string; role: "user"; text: string };
type AssistantMsg = { id: string; role: "assistant"; answer: string; suggestions: string[] };
type Msg = UserMsg | AssistantMsg;

type SessionRow = {
  id: string;
  title: string;
  updated_at: string;
  last_message_preview?: string | null;
};

function relShort(iso: string) {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function ShieldChatPanel() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const sessionRef = useRef<string | null>(null);

  useEffect(() => {
    sessionRef.current = sessionId;
  }, [sessionId]);

  const loadSessions = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/v1/chat/sessions`);
      if (r.ok) {
        const rows = (await r.json()) as SessionRow[];
        const empty = rows.filter(
          (s) =>
            !(s.last_message_preview || "").trim() &&
            ["new chat", "new conversation", ""].includes((s.title || "").trim().toLowerCase()),
        );
        if (empty.length > 0) {
          await Promise.all(
            empty.map((s) =>
              fetch(`${API_BASE}/api/v1/chat/sessions/${encodeURIComponent(s.id)}`, { method: "DELETE" }),
            ),
          );
        }
        const kept = rows.filter((s) => !empty.some((e) => e.id === s.id));
        kept.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
        setSessions(kept);
      }
    } catch {
      /* ignore */
    }
  }, []);

  async function commitRename(sessionId: string) {
    const t = renameValue.trim();
    if (!t) {
      setRenameId(null);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: t }),
      });
      if (!res.ok) throw new Error(await res.text());
      setRenameId(null);
      await loadSessions();
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/chat/capabilities`)
      .then((r) => r.json() as Promise<{ llm_enabled: boolean }>)
      .then((b) => setLlmEnabled(b.llm_enabled))
      .catch(() => setLlmEnabled(false));
  }, []);

  useEffect(() => {
    if (open) void loadSessions();
  }, [open, loadSessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open]);

  async function ensureSession(): Promise<string> {
    if (sessionRef.current) return sessionRef.current;
    const r = await fetch(`${API_BASE}/api/v1/chat/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: "default", title: "New chat" }),
    });
    if (!r.ok) {
      const detail = await r.text();
      throw new Error(
        `Could not create chat session (${r.status}): ${detail.slice(0, 400) || r.statusText}. ` +
          `Run the API on port 8000 (agentiva serve --port 8000). If you use the dashboard proxy, set AGENTIVA_API_URL (default http://127.0.0.1:8000). ` +
          `Or set NEXT_PUBLIC_API_BASE to the API URL to call it directly.`,
      );
    }
    const j = (await r.json()) as { id: string };
    sessionRef.current = j.id;
    setSessionId(j.id);
    await loadSessions();
    return j.id;
  }

  async function selectSession(id: string) {
    sessionRef.current = id;
    setSessionId(id);
    setSidebarOpen(false);
    try {
      const r = await fetch(`${API_BASE}/api/v1/chat/sessions/${id}`);
      if (!r.ok) return;
      const detail = (await r.json()) as {
        messages: { role: string; content: string; suggestions?: string[] }[];
      };
      const mapped: Msg[] = [];
      for (const m of detail.messages || []) {
        const mid = crypto.randomUUID();
        if (m.role === "user") {
          mapped.push({ id: mid, role: "user", text: m.content });
        } else {
          mapped.push({ id: mid, role: "assistant", answer: m.content, suggestions: m.suggestions ?? [] });
        }
      }
      setMessages(mapped);
    } catch {
      /* ignore */
    }
  }

  async function newChat() {
    sessionRef.current = null;
    setSessionId(null);
    setMessages([]);
    const r = await fetch(`${API_BASE}/api/v1/chat/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: "default", title: "New chat" }),
    });
    if (r.ok) {
      const j = (await r.json()) as { id: string };
      sessionRef.current = j.id;
      setSessionId(j.id);
      await loadSessions();
    }
    setSidebarOpen(false);
  }

  async function deleteSession(id: string, e: MouseEvent) {
    e.stopPropagation();
    await fetch(`${API_BASE}/api/v1/chat/sessions/${id}`, { method: "DELETE" });
    if (sessionId === id) {
      sessionRef.current = null;
      setSessionId(null);
      setMessages([]);
    }
    await loadSessions();
  }

  async function clearAllSessions() {
    await fetch(`${API_BASE}/api/v1/chat/sessions/all`, { method: "DELETE" });
    sessionRef.current = null;
    setSessionId(null);
    setMessages([]);
    await loadSessions();
  }

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || loading) return;
      setInput("");
      const uid = crypto.randomUUID();
      setMessages((m) => [...m, { id: uid, role: "user", text: trimmed }]);
      setLoading(true);
      try {
        const sid = await ensureSession();
        const res = await fetch(`${API_BASE}/api/v1/chat/sessions/${sid}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: trimmed }),
        });
        if (!res.ok) throw new Error(await res.text());
        const payload = (await res.json()) as ChatPayload;
        const clean = sanitizeAnswer(payload.answer);
        setMessages((m) => [
          ...m,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            answer: clean,
            suggestions: payload.suggestions ?? [],
          },
        ]);
        await loadSessions();
      } catch (e) {
        setMessages((m) => [
          ...m,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            answer: `Something went wrong: ${e instanceof Error ? e.message : "request failed"}`,
            suggestions: ["Session overview"],
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [loading, loadSessions],
  );

  useEffect(() => {
    const handler = (ev: Event) => {
      const ce = ev as CustomEvent<{ message?: string }>;
      const msg = ce.detail?.message;
      if (typeof msg !== "string" || !msg.trim()) return;
      setOpen(true);
      void send(msg.trim());
    };
    window.addEventListener("agentiva:openChat", handler as EventListener);
    return () => window.removeEventListener("agentiva:openChat", handler as EventListener);
  }, [send]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  const busy = loading;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`fixed bottom-6 right-6 z-[60] flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-[#ca8a04] to-[#854d0e] text-[#0a0805] shadow-xl shadow-amber-950/50 transition hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 focus:ring-offset-[#060504] ${open ? "animate-none" : "animate-[pulse_5s_ease-in-out_infinite]"} ${
          open ? "pointer-events-none scale-0 opacity-0" : "scale-100 opacity-100"
        }`}
        aria-label="Open Agentiva chat"
      >
        <MessageCircle className="h-7 w-7" strokeWidth={2} />
      </button>

      <div
        className={`fixed bottom-0 right-0 z-[70] flex h-[min(92vh,600px)] w-full max-w-[450px] flex-col rounded-t-2xl border border-[#2e2918] bg-[#080604] shadow-2xl transition-transform duration-300 ease-out sm:bottom-6 sm:right-6 sm:rounded-2xl ${
          open ? "translate-y-0" : "pointer-events-none translate-y-[110%]"
        }`}
        aria-hidden={!open}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-[#2e2918] px-3 py-2.5">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setSidebarOpen((s) => !s)}
              className="rounded-lg p-2 text-[#8a8270] hover:bg-[#14110a] hover:text-white"
              aria-label="Sessions"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15">
              <Shield className="h-5 w-5 text-emerald-400" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-[#f0f6fc]">Security co-pilot</span>
              {llmEnabled !== null ? (
                <span className="text-[10px] uppercase tracking-wide text-[#8a8270]">
                  {llmEnabled ? "AI-powered" : "Deterministic"}
                </span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="flex shrink-0 items-center gap-1 rounded-lg border border-[#2e2918] px-2 py-1.5 text-xs font-medium text-[#c9d1d9] hover:border-[#a38f6a] hover:bg-[#14110a] hover:text-white"
            aria-label="Close chat"
          >
            <X className="h-4 w-4" strokeWidth={2.5} />
            <span>Close</span>
          </button>
        </div>

        <div className="relative flex min-h-0 flex-1">
          {sidebarOpen ? (
            <aside className="absolute inset-y-0 left-0 z-10 flex w-[min(100%,280px)] flex-col border-r border-[#2e2918] bg-[#060504] shadow-xl">
              <div className="flex items-center justify-between border-b border-[#2e2918] px-2 py-2">
                <span className="px-2 text-xs font-semibold uppercase tracking-wide text-[#8a8270]">History</span>
                <button
                  type="button"
                  onClick={() => void newChat()}
                  className="rounded-md bg-[#ca8a04]/25 px-2 py-1 text-xs font-medium text-[#fde047]"
                >
                  New chat
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-2">
                {sessions.map((s) => (
                  <div
                    key={s.id}
                    className={`group relative mb-1 rounded-lg border px-2 py-2 text-left text-xs ${
                      sessionId === s.id
                        ? "border-[#eab308]/45 bg-[#ca8a04]/12"
                        : "border-transparent hover:bg-[#14110a]"
                    }`}
                  >
                    {renameId === s.id ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void commitRename(s.id);
                          if (e.key === "Escape") {
                            setRenameId(null);
                          }
                        }}
                        onBlur={() => void commitRename(s.id)}
                        className="w-full rounded border border-[#2e2918] bg-[#060504] px-2 py-1 text-[#f0f6fc] focus:border-[#facc15] focus:outline-none"
                      />
                    ) : (
                      <>
                        <button type="button" className="w-full pr-14 text-left" onClick={() => void selectSession(s.id)}>
                          <p className="truncate font-medium text-[#f0f6fc]">
                            {(s.title || "Chat").length > 30 ? `${(s.title || "Chat").slice(0, 30)}…` : s.title || "Chat"}
                          </p>
                          {s.last_message_preview ? (
                            <p className="text-[10px] text-[#8a8270] line-clamp-2">{s.last_message_preview}</p>
                          ) : null}
                          <p className="text-[10px] text-[#8a8270]">{relShort(s.updated_at)}</p>
                        </button>
                        <button
                          type="button"
                          className="absolute right-8 top-1.5 rounded p-1 opacity-0 transition group-hover:opacity-100 hover:bg-[#1a170f]"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRenameId(s.id);
                            setRenameValue(s.title || "");
                          }}
                          aria-label="Rename session"
                        >
                          <Pencil className="h-3.5 w-3.5 text-[#8a8270]" />
                        </button>
                        <button
                          type="button"
                          className="absolute right-1 top-1 rounded p-1 opacity-0 transition group-hover:opacity-100 hover:bg-[#1a170f]"
                          onClick={(e) => void deleteSession(s.id, e)}
                          aria-label="Delete session"
                        >
                          <X className="h-3.5 w-3.5 text-[#8a8270]" />
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
              <div className="border-t border-[#2e2918] p-2">
                <button
                  type="button"
                  onClick={() => void clearAllSessions()}
                  className="w-full rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/15"
                >
                  Clear all history
                </button>
              </div>
            </aside>
          ) : null}

          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3">
              {messages.length === 0 && !loading && (
                <p className="text-sm text-[#8a8270]">
                  Ask about blocked actions, session summaries, HIPAA/SOC2, or policy tuning. Open the menu for chat
                  history.
                </p>
              )}
              {messages.map((m) => {
                const last = messages[messages.length - 1];
                const isLatestAssistantReply =
                  m.role === "assistant" && last?.role === "assistant" && last.id === m.id && !loading;
                return m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[88%] rounded-2xl rounded-br-md bg-gradient-to-br from-[#d4a10e] to-[#a16207] px-3 py-2 text-sm text-[#0a0805] shadow-md">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex gap-2">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#1a170f] ring-1 ring-[#2e2918]">
                      <Shield className="h-4 w-4 text-emerald-400" />
                    </div>
                    <div className="flex max-w-[90%] flex-col rounded-2xl rounded-bl-md border border-[#2e2918] bg-[#100e08] px-3 py-2 text-sm text-[#c9d1d9] shadow-inner">
                      <FormattedAnswer text={m.answer} />
                      {m.suggestions.length > 0 && isLatestAssistantReply ? (
                        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[#2e2918] pt-3">
                          {m.suggestions.map((s) => (
                            <button
                              key={s}
                              type="button"
                              onClick={() => void send(s)}
                              disabled={busy}
                              className="rounded-full border border-[#2e2918] bg-[#060504] px-2.5 py-1 text-left text-xs text-[#fde047] hover:border-[#eab308] disabled:opacity-50"
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
              {loading ? (
                <div className="flex gap-2 pl-1">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#1a170f]">
                    <Shield className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div className="flex flex-col gap-2 rounded-2xl border border-[#2e2918] bg-[#100e08] px-4 py-3">
                    <p className="text-xs text-[#8a8270]">Analyzing your data…</p>
                    <div className="flex items-center gap-1">
                      <span className="h-2 w-2 animate-bounce rounded-full bg-[#facc15] [animation-delay:-0.2s]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-[#facc15] [animation-delay:-0.1s]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-[#facc15]" />
                    </div>
                  </div>
                </div>
              ) : null}
              <div ref={bottomRef} />
            </div>

            <form onSubmit={onSubmit} className="shrink-0 border-t border-[#2e2918] p-3">
              <div className="flex gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask the security co-pilot…"
                  className="min-w-0 flex-1 rounded-xl border border-[#2e2918] bg-[#060504] px-3 py-2.5 text-sm text-[#f0f6fc] placeholder:text-[#484f58] focus:border-[#eab308] focus:outline-none focus:ring-1 focus:ring-[#ca8a04]"
                />
                <button
                  type="submit"
                  disabled={busy || !input.trim()}
                  className="flex shrink-0 items-center justify-center rounded-xl bg-emerald-600 px-3 py-2 text-white shadow-lg transition hover:bg-emerald-500 disabled:opacity-40"
                  aria-label="Send"
                >
                  <Send className="h-5 w-5" />
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </>
  );
}
