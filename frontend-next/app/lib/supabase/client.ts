"use client";

import { createBrowserClient } from "@supabase/ssr";
import { getSupabasePublicEnvironment } from "./env";

export function createClient() {
  const { url, publishableKey } = getSupabasePublicEnvironment();
  return createBrowserClient(url, publishableKey);
}
