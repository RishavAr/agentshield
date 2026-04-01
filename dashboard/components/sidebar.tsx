"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { signOut, useSession } from "next-auth/react";
import { Activity, ClipboardList, Eye, LogOut, Menu, Shield, Users, X } from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: Shield },
  { href: "/live", label: "Live Feed", icon: Activity },
  { href: "/audit", label: "Audit Log", icon: ClipboardList },
  { href: "/agents", label: "Agents", icon: Users },
  { href: "/policies", label: "Policies", icon: Eye },
];

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { data: session } = useSession();

  const Nav = (
    <>
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#1f6feb] to-[#a855f7] shadow-lg shadow-blue-900/30">
          <Shield className="h-5 w-5 text-white" strokeWidth={2.2} />
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#58a6ff]">Agentiva</p>
          <p className="text-lg font-semibold text-[#f0f6fc]">Dashboard</p>
        </div>
      </div>

      <nav className="space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className={`relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                active
                  ? "bg-[#1f6feb]/10 text-[#79c0ff]"
                  : "text-[#c9d1d9] hover:bg-[#161b22] hover:text-[#f0f6fc]"
              }`}
            >
              {active ? <span className="absolute -left-3 top-1/2 h-6 w-0.5 -translate-y-1/2 rounded bg-[#3b82f6]" /> : null}
              <Icon size={18} className={active ? "text-[#58a6ff]" : "text-[#8b949e]"} />
              {label}
            </Link>
          );
        })}
      </nav>
    </>
  );

  return (
    <>
      <button
        type="button"
        className="fixed left-4 top-4 z-50 flex h-11 w-11 items-center justify-center rounded-xl border border-[#30363d] bg-[#161b22] text-[#f0f6fc] shadow-lg md:hidden"
        onClick={() => setOpen(true)}
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      {open ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm md:hidden"
          aria-label="Close menu"
          onClick={() => setOpen(false)}
        />
      ) : null}

      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 border-r border-[#30363d] bg-[#0a0e14] p-6 shadow-2xl transition-transform duration-200 md:static md:z-0 md:translate-x-0 md:shadow-none ${
          open ? "translate-x-0" : "-translate-full md:translate-x-0"
        }`}
      >
        <button
          type="button"
          className="absolute right-4 top-4 rounded-lg p-2 text-[#8b949e] hover:bg-[#161b22] hover:text-white md:hidden"
          onClick={() => setOpen(false)}
          aria-label="Close sidebar"
        >
          <X className="h-5 w-5" />
        </button>
        {Nav}
        {session?.user ? (
          <div className="mt-10 border-t border-[#30363d] pt-4">
            <p className="mb-2 truncate text-xs text-[#8b949e]" title={session.user.email ?? ""}>
              {session.user.email ?? session.user.name ?? "Signed in"}
            </p>
            <button
              type="button"
              onClick={() => signOut({ callbackUrl: "/login" })}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-[#c9d1d9] hover:bg-[#161b22]"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        ) : null}
      </aside>
    </>
  );
}
