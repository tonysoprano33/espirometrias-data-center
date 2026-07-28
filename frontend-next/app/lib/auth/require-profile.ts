import { redirect } from "next/navigation";
import { type AppRole } from "./roles";
import { createClient } from "../supabase/server";

export type AppProfile = {
  id: string;
  display_name: string | null;
  role: AppRole;
  is_active: boolean;
};

export async function requireProfile(allowedRoles?: readonly AppRole[]) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("id, display_name, role, is_active")
    .eq("id", user.id)
    .maybeSingle<AppProfile>();

  if (!profile || !profile.is_active) redirect("/login?error=profile");
  if (allowedRoles && !allowedRoles.includes(profile.role)) redirect("/preview?error=forbidden");

  return { user, profile };
}
