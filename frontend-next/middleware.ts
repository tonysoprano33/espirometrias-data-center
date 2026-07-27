import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  // Until the migration is complete, every clinical route belongs to the
  // established Django app. This includes secondary actions such as print,
  // inline agenda updates and report downloads, not only the main screens.
  if (pathname === "/django" || pathname.startsWith("/django/")) {
    return NextResponse.next();
  }

  const target = new URL(`/django${pathname}${search}`, request.url);
  return NextResponse.redirect(target, 307);
}

export const config = {
  matcher: ["/((?!_next|api|login|logout|static|media|favicon.ico).*)"],
};
