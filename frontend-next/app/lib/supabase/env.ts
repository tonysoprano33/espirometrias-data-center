// These values are intentionally public: Supabase publishable keys are meant
// for browser clients. Privileged service keys must never be placed here.
const PREVIEW_SUPABASE_URL = "https://pltkxisxhrhafvegovlc.supabase.co";
const PREVIEW_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_4XVdvONdfdAwl98xQilzUg_ujmYd2UU";

export function getSupabasePublicEnvironment() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || PREVIEW_SUPABASE_URL;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || PREVIEW_SUPABASE_PUBLISHABLE_KEY;

  if (!url || !publishableKey) {
    throw new Error(
      "Falta configurar NEXT_PUBLIC_SUPABASE_URL o NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY en el preview.",
    );
  }

  return { url, publishableKey };
}

export function isSupabaseConfigured() {
  return true;
}
