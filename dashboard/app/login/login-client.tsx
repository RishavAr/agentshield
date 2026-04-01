"use client";

import { signIn } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Shield } from "lucide-react";

type Props = {
  hasGoogle: boolean;
  hasGitHub: boolean;
  hasDemo: boolean;
  authDisabled: boolean;
  authSecretConfigured: boolean;
};

export function LoginClient({
  hasGoogle,
  hasGitHub,
  hasDemo,
  authDisabled,
  authSecretConfigured,
}: Props) {
  const search = useSearchParams();
  const router = useRouter();
  const callbackUrl = search.get("callbackUrl") || "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);

  if (authDisabled || !authSecretConfigured) {
    return (
      <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
        <p className="text-center text-[#8b949e]">
          Sign-in is disabled (set <code className="text-[#c9d1d9]">AUTH_SECRET</code> to enable, or use{" "}
          <code className="text-[#c9d1d9]">NEXT_PUBLIC_AUTH_DISABLED=true</code> for local dev).{" "}
          <a className="text-[#58a6ff] underline" href="/dashboard">
            Dashboard
          </a>
        </p>
      </div>
    );
  }

  async function onDemoSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const res = await signIn("demo", { email, password, callbackUrl, redirect: false });
    if (res?.error) {
      setErr("Invalid demo credentials");
      return;
    }
    router.push(callbackUrl);
    router.refresh();
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <div className="mb-10 text-center">
        <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-[#21262d]">
          <Shield className="h-8 w-8 text-[#58a6ff]" aria-hidden />
        </div>
        <h1 className="text-2xl font-semibold text-[#f0f6fc]">Sign in</h1>
        <p className="mt-2 text-sm text-[#8b949e]">OAuth (Google / GitHub) or demo password</p>
      </div>

      <div className="flex flex-col gap-3">
        {hasGoogle && (
          <button
            type="button"
            className="rounded-lg border border-[#30363d] bg-[#21262d] px-4 py-3 text-sm font-medium text-[#f0f6fc] transition hover:bg-[#30363d]"
            onClick={() => signIn("google", { callbackUrl })}
          >
            Continue with Google
          </button>
        )}
        {hasGitHub && (
          <button
            type="button"
            className="rounded-lg border border-[#30363d] bg-[#21262d] px-4 py-3 text-sm font-medium text-[#f0f6fc] transition hover:bg-[#30363d]"
            onClick={() => signIn("github", { callbackUrl })}
          >
            Continue with GitHub
          </button>
        )}

        {hasDemo && (
          <form onSubmit={onDemoSubmit} className="mt-4 space-y-3 rounded-lg border border-[#30363d] bg-[#161b22] p-4">
            <p className="text-xs text-[#8b949e]">Demo login (set AUTH_DEMO_EMAIL + AUTH_DEMO_PASSWORD)</p>
            <input
              type="email"
              required
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#f0f6fc]"
            />
            <input
              type="password"
              required
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#f0f6fc]"
            />
            {err && <p className="text-sm text-[#f85149]">{err}</p>}
            <button
              type="submit"
              className="w-full rounded-lg bg-[#238636] px-4 py-2 text-sm font-medium text-white hover:bg-[#2ea043]"
            >
              Sign in with demo account
            </button>
          </form>
        )}

        {!hasGoogle && !hasGitHub && !hasDemo && (
          <p className="text-center text-sm text-[#f85149]">
            No OAuth or demo env vars. Add AUTH_GOOGLE_ID/SECRET, AUTH_GITHUB_ID/SECRET, or AUTH_DEMO_EMAIL/PASSWORD.
          </p>
        )}
      </div>
    </div>
  );
}
