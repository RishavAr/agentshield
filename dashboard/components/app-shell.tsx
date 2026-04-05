"use client";

import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";

import { Sidebar } from "@/components/sidebar";
import { ToastHost } from "@/components/toast-host";

/** Client-only: avoids hydration mismatches (API-backed state, floating UI, dev HMR skew). */
const ShieldChatPanel = dynamic(
  () => import("@/components/shield-chat").then((m) => m.ShieldChatPanel),
  { ssr: false },
);

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isMinimalChrome = pathname === "/" || pathname === "/marketing";

  if (isMinimalChrome) {
    return (
      <>
        <main className="min-h-screen bg-[#050403]">{children}</main>
        <ToastHost />
      </>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#080604]">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto bg-[#0a0805] px-4 pb-12 pt-16 md:px-10 md:pt-10">
        <div className="mx-auto max-w-7xl">{children}</div>
      </main>
      <ShieldChatPanel />
      <ToastHost />
    </div>
  );
}

