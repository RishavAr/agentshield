import { auth } from "@/auth";
import { NextResponse } from "next/server";

const PROTECTED_PREFIXES = ["/dashboard", "/live", "/agents", "/audit", "/policies"];

export const proxy = auth((req) => {
  if (process.env.NEXT_PUBLIC_AUTH_DISABLED === "true") {
    return NextResponse.next();
  }
  if (!process.env.AUTH_SECRET) {
    return NextResponse.next();
  }

  const path = req.nextUrl.pathname;
  const isProtected = PROTECTED_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`));

  if (!isProtected) {
    return NextResponse.next();
  }

  if (!req.auth) {
    const login = new URL("/login", req.nextUrl.origin);
    login.searchParams.set("callbackUrl", path);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
