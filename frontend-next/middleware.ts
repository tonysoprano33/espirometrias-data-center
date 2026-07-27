import { NextRequest, NextResponse } from "next/server";

const djangoOrigin = process.env.DJANGO_ORIGIN || "https://clinica-espiro-api.onrender.com";

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  // The Django application is the stable production UI. A browser redirect,
  // rather than a Vercel rewrite, preserves Django's own routes, sessions,
  // PDF downloads and form actions without proxy-induced 404/500 failures.
  const target = new URL(`${pathname}${search}`, djangoOrigin);
  return NextResponse.redirect(target, 307);
}

export const config = {
  matcher: ["/((?!_next|api|static|media|favicon.ico).*)"],
};
