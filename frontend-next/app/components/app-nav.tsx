import Link from "next/link";
import { type AppRole, ROLE_LABEL } from "../lib/auth/roles";

type AppNavProps = {
  role: AppRole;
  displayName: string | null;
};

export function AppNav({ role, displayName }: AppNavProps) {
  const canReview = role === "admin" || role === "medico" || role === "espirometrista";

  return (
    <header className="next-app-header">
      <Link className="next-brand" href="/agenda">
        <span>Clinica Espiro</span>
        <small>Agenda respiratoria</small>
      </Link>
      <nav aria-label="Navegacion principal">
        <Link href="/agenda">Agenda</Link>
        {canReview && <Link href="/revision-medica">Revision medica</Link>}
      </nav>
      <div className="next-session">
        <span>{displayName || ROLE_LABEL[role]}</span>
        <form action="/auth/signout" method="post">
          <button type="submit">Salir</button>
        </form>
      </div>
    </header>
  );
}
