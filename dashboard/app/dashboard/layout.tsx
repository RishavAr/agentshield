import type { ReactNode } from "react";
import { unstable_noStore as noStore } from "next/cache";

/** Avoid stale RSC/HTML for dashboard after edits (Turbopack “stale” + hydration mismatches). */
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  noStore();
  return <>{children}</>;
}
