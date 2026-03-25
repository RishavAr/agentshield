"use client";

import { usePathname } from "next/navigation";

import { Sidebar } from "@/components/sidebar";
import { ShieldChatPanel } from "@/components/shield-chat";
import { ToastHost } from "@/components/toast-host";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isMinimalChrome = pathname === "/" || pathname === "/marketing";

  if (isMinimalChrome) {
    return (
      <>
        <main className="min-h-screen bg-[#0a0a0a]">{children}</main>
        <ToastHost />
      </>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#0a0e14]">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto bg-[#0a0f1e] px-4 pb-12 pt-16 md:px-10 md:pt-10">
        <div className="mx-auto max-w-7xl">{children}</div>
      </main>
      <ShieldChatPanel />
      <ToastHost />
    </div>
  );
}

