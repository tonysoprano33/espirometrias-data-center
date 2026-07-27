import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const djangoOrigin = process.env.DJANGO_ORIGIN || "http://127.0.0.1:8000";
const djangoBypassSecret = process.env.DJANGO_BYPASS_SECRET;

const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "x-csrftoken",
] as const;

const HOP_BY_HOP_RESPONSE_HEADERS = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "keep-alive",
  "transfer-encoding",
]);

function isLoginRedirect(response: Response) {
  if (response.status < 300 || response.status >= 400) return false;
  const location = response.headers.get("location") || "";
  return location.startsWith("/login/") || location.includes("/login/");
}

async function proxyToDjango(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const url = new URL(`/api/v1/${path.join("/")}/`, djangoOrigin);
  url.search = request.nextUrl.search;

  const headers = new Headers();
  for (const headerName of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(headerName);
    if (value) {
      headers.set(headerName, value);
    }
  }

  // Vercel rewrites terminate TLS before reaching Django. Preserve the original
  // public scheme so Django keeps its secure-session and CSRF guarantees.
  headers.set("x-forwarded-proto", "https");
  headers.set("x-forwarded-host", request.headers.get("host") || "");
  if (djangoBypassSecret) {
    headers.set("x-vercel-protection-bypass", djangoBypassSecret);
  }

  const upstream = await fetch(url, {
    method: request.method,
    headers,
    body:
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer(),
    redirect: "manual",
    cache: "no-store",
  });

  // A browser fetch does not navigate when Django redirects an expired session
  // to /login/. Return JSON instead so the client can send the user to login
  // explicitly rather than rendering every list as empty.
  if (isLoginRedirect(upstream)) {
    return Response.json(
      { ok: false, code: "authentication_required", message: "Inicia sesion para cargar los datos." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_RESPONSE_HEADERS.has(key.toLowerCase())) {
      responseHeaders.append(key, value);
    }
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxyToDjango;
export const POST = proxyToDjango;
