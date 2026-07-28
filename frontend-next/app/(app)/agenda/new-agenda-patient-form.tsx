"use client";

import { useActionState } from "react";
import { createAgendaEntry, type CreateAgendaState } from "./actions";

const initialState: CreateAgendaState = { ok: false, message: "" };

export function NewAgendaPatientForm({ today }: { today: string }) {
  const [state, action, isPending] = useActionState(createAgendaEntry, initialState);

  return (
    <section className="next-add-patient">
      <div><p className="eyebrow">Recepcion</p><h2>Agregar paciente</h2></div>
      <form action={action}>
        <label>Nombre<input name="fullName" required maxLength={180} autoComplete="off" /></label>
        <label>DNI <small>opcional</small><input name="dni" inputMode="numeric" maxLength={20} autoComplete="off" /></label>
        <label>Fecha<input name="encounterDate" type="date" defaultValue={today} required /></label>
        <label>Hora<input name="encounterTime" type="time" /></label>
        <label>Estudio<select name="studyType" defaultValue="Ciclometria"><option>Ciclometria</option><option>Espirometria</option></select></label>
        <label>Cobertura<select name="coverageType" defaultValue="Particular"><option>Particular</option><option>Mutual</option></select></label>
        <label>Mutual <small>si corresponde</small><input name="coverageName" maxLength={120} autoComplete="off" /></label>
        <label className="add-control"><input name="medicalControlToday" type="checkbox" /> Control medico hoy</label>
        <button className="primary-action" disabled={isPending}>{isPending ? "Guardando..." : "Agregar paciente"}</button>
      </form>
      {state.message && <p className={`agenda-form-message ${state.ok ? "success" : "error"}`} role="status">{state.message}</p>}
    </section>
  );
}
