import Link from "next/link";
import { type AppRole, ROLE_LABEL } from "../lib/auth/roles";

type AppNavProps = {
  role: AppRole;
  displayName: string | null;
};

export function AppNav({ role, displayName }: AppNavProps) {
  const isClinicalOperator = role === "admin" || role === "espirometrista";
  const canReview = isClinicalOperator || role === "medico";
  const roleLabel = displayName || ROLE_LABEL[role];

  return (
    <header className="topbar" data-work-mode={role}>
      <div className="topbar-inner">
        <div className="brand-block">
          <Link className="brand" href="/agenda">
            Clinica Espiro
            <small>Agenda respiratoria e informes</small>
          </Link>
          <div className="work-mode-session" aria-label="Sesion activa">
            <span>Sesion</span>
            <strong>{roleLabel}</strong>
          </div>
        </div>
        <nav className="nav" aria-label="Navegacion principal">
          {(role === "secretaria" || isClinicalOperator) && <Link className="current" href="/agenda">Inicio</Link>}
          {isClinicalOperator && <span className="nav-preview-item">Calendario</span>}
          {isClinicalOperator && <span className="nav-preview-item">Estadistica</span>}
          {isClinicalOperator && <span className="nav-preview-item">Pacientes</span>}
          {isClinicalOperator && <span className="nav-preview-item">Papelera</span>}
          {canReview && <Link href="/revision-medica">Revision medica</Link>}
          {isClinicalOperator && <form action="/auth/signout" method="post"><button className="button alt" type="submit">Salir</button></form>}
        </nav>
      </div>
    </header>
  );
}
