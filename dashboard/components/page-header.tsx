"use client";

import { useEffect, useState } from "react";
import { ChevronRight, Home } from "lucide-react";

type Crumb = { label: string; href?: string };

/**
 * Breadcrumbs render only after mount so SSR + first client paint match (avoids Turbopack/stale
 * SSR bundles shipping old markup like <button> while the client has <a>).
 */
function Breadcrumbs({ items }: { items: Crumb[] }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <nav
        className="relative z-[121] flex min-h-[1.25rem] flex-wrap items-center gap-1 text-xs text-[#8b949e] pointer-events-auto"
        aria-hidden="true"
      >
        <span className="inline-flex items-center gap-1 opacity-0">
          <Home className="h-3.5 w-3.5" />
          Home
        </span>
      </nav>
    );
  }

  return (
    <nav className="relative z-[121] flex flex-wrap items-center gap-1 text-xs text-[#8b949e] pointer-events-auto">
      <a
        href="/dashboard"
        className="inline-flex cursor-pointer items-center gap-1 text-inherit no-underline hover:text-[#58a6ff]"
      >
        <Home className="h-3.5 w-3.5" />
        Home
      </a>
      {items.map((c) => (
        <span key={c.label} className="inline-flex items-center gap-1">
          <ChevronRight className="h-3.5 w-3.5 opacity-50" />
          {c.href ? (
            <a href={c.href} className="hover:text-[#58a6ff]">
              {c.label}
            </a>
          ) : (
            <span className="text-[#c9d1d9]">{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

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
      {breadcrumbs && breadcrumbs.length > 0 ? <Breadcrumbs items={breadcrumbs} /> : null}
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
