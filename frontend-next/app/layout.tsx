import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Preview | Clinica Espiro",
  description: "Migracion controlada a Next.js y Supabase.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
