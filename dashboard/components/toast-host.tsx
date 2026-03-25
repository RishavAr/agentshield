"use client";

import { useEffect, useState } from "react";

type ToastItem = { id: string; message: string; kind: "success" | "error" | "info" };

export function toast(message: string, kind: ToastItem["kind"] = "success") {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("agentiva:toast", { detail: { message, kind } }));
}

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    const onToast = (e: Event) => {
      const ce = e as CustomEvent<{ message: string; kind?: ToastItem["kind"] }>;
      const id = crypto.randomUUID();
      const kind = ce.detail?.kind ?? "success";
      setItems((prev) => [...prev, { id, message: ce.detail.message, kind }]);
      window.setTimeout(() => {
        setItems((prev) => prev.filter((x) => x.id !== id));
      }, 4500);
    };
    window.addEventListener("agentiva:toast", onToast as EventListener);
    return () => window.removeEventListener("agentiva:toast", onToast as EventListener);
  }, []);

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[300] flex max-w-sm flex-col gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto rounded-xl border px-4 py-3 text-sm font-medium shadow-2xl backdrop-blur-sm ${
            t.kind === "success"
              ? "border-emerald-500/40 bg-emerald-950/95 text-emerald-100"
              : t.kind === "error"
                ? "border-red-500/40 bg-red-950/95 text-red-100"
                : "border-sky-500/40 bg-slate-950/95 text-sky-100"
          }`}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
