import NextAuth from "next-auth";
import type { NextAuthConfig } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";

function buildProviders() {
  const list = [];
  if (process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET) {
    list.push(
      Google({
        clientId: process.env.AUTH_GOOGLE_ID,
        clientSecret: process.env.AUTH_GOOGLE_SECRET,
      }),
    );
  }
  if (process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET) {
    list.push(
      GitHub({
        clientId: process.env.AUTH_GITHUB_ID,
        clientSecret: process.env.AUTH_GITHUB_SECRET,
      }),
    );
  }
  if (process.env.AUTH_DEMO_EMAIL && process.env.AUTH_DEMO_PASSWORD) {
    list.push(
      Credentials({
        id: "demo",
        name: "Demo account",
        credentials: {
          email: { label: "Email", type: "email" },
          password: { label: "Password", type: "password" },
        },
        async authorize(credentials) {
          const email = credentials?.email as string | undefined;
          const password = credentials?.password as string | undefined;
          if (
            email &&
            password &&
            email === process.env.AUTH_DEMO_EMAIL &&
            password === process.env.AUTH_DEMO_PASSWORD
          ) {
            return { id: "demo-user", email, name: "Demo user" };
          }
          return null;
        },
      }),
    );
  }
  if (list.length === 0) {
    list.push(
      Credentials({
        id: "configure",
        name: "Not configured",
        credentials: {},
        async authorize() {
          return null;
        },
      }),
    );
  }
  return list;
}

const authConfig: NextAuthConfig = {
  trustHost: true,
  secret:
    process.env.AUTH_SECRET ||
    (process.env.NODE_ENV === "development" ? "dev-only-agentiva-auth-secret" : undefined),
  providers: buildProviders(),
  session: { strategy: "jwt", maxAge: 30 * 24 * 60 * 60 },
  pages: { signIn: "/login" },
};

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
