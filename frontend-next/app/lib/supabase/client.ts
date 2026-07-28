"use client";

import { createBrowserClient } from "@supabase/ssr";
import { getSupabasePublicEnvironment } from "./env";

export function createClient(persistSession = true) {
  const { url, publishableKey } = getSupabasePublicEnvironment();
  return createBrowserClient(url, publishableKey, {
    auth: { persistSession, autoRefreshToken: true, detectSessionInUrl: true },
  });
}
