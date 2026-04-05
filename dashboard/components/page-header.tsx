"use client";

import Link from "next/link";
import { ChevronRight, Home } from "lucide-react";

type Crumb = { label: string; href?: string };

/** Same markup on server and client — use `Link` only (no mount gate) to avoid hydration drift with Turbopack/HMR. */
function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="relative z-[121] flex flex-wrap items-center gap-1 text-xs text-[#8a8270] pointer-events-auto">
      <Link
        href="/"
        className="inline-flex cursor-pointer items-center gap-1 text-inherit no-underline hover:text-[#facc15]"
        title="Welcome and setup (register agent, demo)"
      >
        <Home className="h-3.5 w-3.5" />
        Home
      </Link>
      {items.map((c) => (
        <span key={c.label} className="inline-flex items-center gap-1">
          <ChevronRight className="h-3.5 w-3.5 opacity-50" />
          {c.href ? (
            <Link href={c.href} className="hover:text-[#facc15]">
              {c.label}
            </Link>
          ) : (
            <span className="text-[#e8e4d4]">{c.label}</span>
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
          {subtitle ? <p className="text-sm font-medium text-[#9a8f78]">{subtitle}</p> : null}
          <h1 className="text-3xl font-semibold tracking-tight text-[#faf6e8]">{title}</h1>
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
