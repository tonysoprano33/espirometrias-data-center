import { NextRequest, NextResponse } from "next/server";

const djangoOnlyPaths = new Set([
  "/",
  "/calendario/",
  "/estadistica/",
  "/pacientes/",
  "/revision-medica/",
  "/papelera/",
  "/admin/",
]);

function shouldUseDjango(pathname: string) {
  return djangoOnlyPaths.has(pathname)
    || pathname.startsWith("/pacientes/")
    || pathname.startsWith("/revision-medica/")
    || pathname.startsWith("/papelera/");
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (!shouldUseDjango(pathname) || pathname.startsWith("/django/")) {
    return NextResponse.next();
  }

  const target = new URL(`/django${pathname}${search}`, request.url);
  return NextResponse.redirect(target, 307);
}

export const config = {
  matcher: ["/((?!_next|api|login|logout|static|media|favicon.ico).*)"],
};
