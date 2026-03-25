"use client";

import Link from "next/link";
import { ChevronRight, Home } from "lucide-react";

type Crumb = { label: string; href?: string };

export function PageHeader({
  title,
  subtitle,
  breadcrumbs,
  actions,
}: {
  title: string;
  subtitle?: string;
  breadcrumbs?: Crumb[];
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-enter relative z-[120] mb-8 space-y-3 pointer-events-auto">
      {breadcrumbs && breadcrumbs.length > 0 ? (
        <nav className="relative z-[121] flex flex-wrap items-center gap-1 text-xs text-[#8b949e] pointer-events-auto">
          <Link href="/" className="inline-flex items-center gap-1 hover:text-[#58a6ff]">
            <Home className="h-3.5 w-3.5" />
            Home
          </Link>
          {breadcrumbs.map((c) => (
            <span key={c.label} className="inline-flex items-center gap-1">
              <ChevronRight className="h-3.5 w-3.5 opacity-50" />
              {c.href ? (
                <Link href={c.href} className="hover:text-[#58a6ff]">
                  {c.label}
                </Link>
              ) : (
                <span className="text-[#c9d1d9]">{c.label}</span>
              )}
            </span>
          ))}
        </nav>
      ) : null}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          {subtitle ? <p className="text-sm font-medium text-[#64748b]">{subtitle}</p> : null}
          <h1 className="text-3xl font-semibold tracking-tight text-[#f8fafc]">{title}</h1>
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
