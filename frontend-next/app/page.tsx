import { redirect } from "next/navigation";
import { requireProfile } from "./lib/auth/require-profile";

export default async function HomePage() {
  const { profile } = await requireProfile();
  redirect(profile.role === "medico" ? "/revision-medica" : "/agenda");
}
