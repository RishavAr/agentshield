import { Suspense } from "react";

import { LoginClient } from "./login-client";

export default function LoginPage() {
  const authDisabled = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";
  const authSecretConfigured = !!process.env.AUTH_SECRET;

  return (
    <Suspense fallback={<div className="p-8 text-center text-[#8b949e]">Loading…</div>}>
      <LoginClient
        hasGoogle={!!process.env.AUTH_GOOGLE_ID && !!process.env.AUTH_GOOGLE_SECRET}
        hasGitHub={!!process.env.AUTH_GITHUB_ID && !!process.env.AUTH_GITHUB_SECRET}
        hasDemo={!!process.env.AUTH_DEMO_EMAIL && !!process.env.AUTH_DEMO_PASSWORD}
        authDisabled={authDisabled}
        authSecretConfigured={authSecretConfigured}
      />
    </Suspense>
  );
}
