"use client";

import { useActionState } from "react";
import { createAgendaEntry, type CreateAgendaState } from "./actions";
import type { AppRole } from "../../lib/auth/roles";
import type { PhysicianOption } from "./agenda-types";

const initialState: CreateAgendaState = { ok: false, message: "" };

export function NewAgendaPatientForm({ today, role, physicians }: { today: string; role: AppRole; physicians: PhysicianOption[] }) {
  const [state, action, isPending] = useActionState(createAgendaEntry, initialState);

  return (
    <div className="agenda-entry-panel">
      <section className="quick-add-box">
        <div className="quick-add-heading">
          <span className="quick-add-mark" aria-hidden="true">+</span>
          <div><p className="quick-add-eyebrow">Recepcion</p><h2 className="mini-title">Agregar paciente</h2></div>
        </div>
        <p className="quick-hint">Carga rapida de recepcion: con el nombre ya alcanza. Estudio y cobertura ya quedan listos con sus valores por defecto.</p>
        <form action={action}>
          <input name="encounterDate" type="hidden" value={today} />
          <div className="quick-core-grid">
            <label className="field">Nombre<input name="fullName" required maxLength={180} autoComplete="off" /></label>
            <label className="field">DNI<input name="dni" inputMode="numeric" maxLength={20} autoComplete="off" placeholder="Opcional" /></label>
            <label className="field">Hora<input name="encounterTime" type="time" /></label>
            <label className="field">Tipo de estudio<select name="studyType" defaultValue="Ciclometria"><option>Ciclometria</option><option>Espirometria</option></select></label>
            <label className="field">Cobertura<select name="coverageType" defaultValue="Particular"><option>Particular</option><option>Mutual</option></select></label>
            <label className="quick-control-toggle"><input name="medicalControlToday" type="checkbox" /> Control medico hoy</label>
            <button className="button" disabled={isPending}>{isPending ? "Guardando..." : "Agregar paciente"}</button>
          </div>
          <details className="quick-secondary">
            <summary>Datos opcionales</summary>
            <div className="quick-secondary-grid">
              <label className="field">Mutual<input name="coverageName" maxLength={120} autoComplete="off" placeholder="Solo si corresponde" /></label>
              <label className="field">Doctor derivante<select name="referringPhysicianId" defaultValue={physicians.find((item) => item.is_default)?.physician_id ?? ""}><option value="">Sin especificar</option>{physicians.map((item) => <option value={item.physician_id} key={item.physician_id}>{item.full_name}</option>)}</select></label>
            </div>
          </details>
        </form>
        {role !== "secretaria" && <p className="quick-form-stage">Despues podes completar DNI, medico, signos y resultado directamente en la fila del paciente.</p>}
      </section>
      {state.message && <p className={`agenda-form-message ${state.ok ? "success" : "error"}`} role="status">{state.message}</p>}
    </div>
  );
}
