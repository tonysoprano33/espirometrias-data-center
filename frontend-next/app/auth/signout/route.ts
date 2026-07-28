import { NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getSupabasePublicEnvironment } from "../../lib/supabase/env";

export async function POST(request: Request) {
  const response = NextResponse.redirect(new URL("/login", request.url), { status: 303 });
  const cookieStore = await cookies();
  const sessionCookies = cookieStore.getAll().filter((cookie) => cookie.name.startsWith("sb-"));
  const { url, publishableKey } = getSupabasePublicEnvironment();
  const supabase = createServerClient(url, publishableKey, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (cookies) => {
        cookies.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });
  await supabase.auth.signOut({ scope: "local" });
  // Supabase refresh cookies may have been written by the proxy. Clear every
  // session cookie explicitly so a role switch cannot reuse the prior session.
  sessionCookies.forEach((cookie) => {
    response.cookies.set(cookie.name, "", { path: "/", maxAge: 0 });
  });
  return response;
}
