import Link from "next/link";
import { ROLE_LABEL } from "../lib/auth/roles";
import { requireProfile } from "../lib/auth/require-profile";

export default async function PreviewPage() {
  const { profile } = await requireProfile();

  return (
    <main className="migration-shell">
      <section className="migration-card">
        <p className="eyebrow">Sesion autenticada</p>
        <h1>Base de migracion conectada</h1>
        <p>
          Sesion validada como <strong>{ROLE_LABEL[profile.role]}</strong>. La agenda y la cola médica
          leen directamente las tablas clínicas migradas.
        </p>
        <ul className="preview-checklist">
          <li>Supabase Auth con cookies de sesion.</li>
          <li>Perfil activo y rol controlado desde la base.</li>
          <li>Agenda operativa y cola clínica según permisos.</li>
          <li>Escrituras clínicas bloqueadas hasta implementar y probar cada Server Action.</li>
        </ul>
        <form action="/auth/signout" method="post">
          <button className="secondary-button">Cerrar sesion</button>
        </form>
        <Link className="text-link" href="/agenda">Abrir agenda</Link>
      </section>
    </main>
  );
}
