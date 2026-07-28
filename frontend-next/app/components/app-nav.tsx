"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type AppRole, ROLE_LABEL } from "../lib/auth/roles";

type AppNavProps = {
  role: AppRole;
  displayName: string | null;
};

export function AppNav({ role, displayName }: AppNavProps) {
  const pathname = usePathname();
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
          {(role === "secretaria" || isClinicalOperator) && <Link className={pathname.startsWith("/agenda") ? "current" : ""} href="/agenda">Inicio</Link>}
          {isClinicalOperator && <Link className={pathname.startsWith("/calendario") ? "current" : ""} href="/calendario">Calendario</Link>}
          {isClinicalOperator && <Link className={pathname.startsWith("/estadistica") ? "current" : ""} href="/estadistica">Estadistica</Link>}
          {isClinicalOperator && <Link className={pathname.startsWith("/pacientes") ? "current" : ""} href="/pacientes">Pacientes</Link>}
          {isClinicalOperator && <Link className={pathname.startsWith("/papelera") ? "current" : ""} href="/papelera">Papelera</Link>}
          {canReview && <Link className={pathname.startsWith("/revision-medica") ? "current" : ""} href="/revision-medica">Revision medica</Link>}
          <form action="/auth/signout" method="post"><button className="button alt" type="submit">Salir</button></form>
        </nav>
      </div>
    </header>
  );
}
