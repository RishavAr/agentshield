"use client";

import dynamic from "next/dynamic";

const MarketingLanding = dynamic(() => import("./marketing-landing"), {
  ssr: false,
  loading: () => (
    <div className="min-h-screen bg-[#060504] text-[#ebe4d4]">
      <div className="mx-auto max-w-6xl px-6 py-24 text-center text-sm text-[#64748b]">Loading…</div>
    </div>
  ),
});

export default function MarketingShell() {
  return <MarketingLanding />;
}
