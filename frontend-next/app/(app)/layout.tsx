import { AppNav } from "../components/app-nav";
import { requireProfile } from "../lib/auth/require-profile";

export default async function ProtectedLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const { profile } = await requireProfile();

  return (
    <>
      <AppNav role={profile.role} displayName={profile.display_name} />
      {children}
    </>
  );
}
