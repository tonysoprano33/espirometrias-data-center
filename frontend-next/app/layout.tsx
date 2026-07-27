import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agenda | Clinica Espiro",
  description: "Nueva interfaz de agenda en validacion interna.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
