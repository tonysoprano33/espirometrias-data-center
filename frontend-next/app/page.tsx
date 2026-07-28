import Link from "next/link";
import { isSupabaseConfigured } from "./lib/supabase/env";

export default function MigrationHome() {
  const configured = isSupabaseConfigured();

  return (
    <main className="migration-shell">
      <section className="migration-card">
        <p className="eyebrow">Clinica Espiro · Migracion a Next.js</p>
        <h1>Nuevo sistema clinico</h1>
        <p>
          La agenda inicial y la cola médica ya leen los datos migrados desde Supabase.
          Las operaciones clínicas se activan por fases, con validación antes de reemplazar el sistema actual.
        </p>
        {configured ? (
          <Link className="primary-link" href="/login">Iniciar sesion</Link>
        ) : (
          <div className="setup-warning">
            <strong>Entorno pendiente de configuracion.</strong>
            <span>Faltan las variables publicas de Supabase. No se modificó la aplicación actual.</span>
          </div>
        )}
      </section>
    </main>
  );
}
