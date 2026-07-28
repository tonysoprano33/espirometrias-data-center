import Link from "next/link";
import { createClient } from "../../lib/supabase/server";
import { requireProfile } from "../../lib/auth/require-profile";
import { NewAgendaPatientForm } from "./new-agenda-patient-form";

type AgendaEntry = {
  encounter_id: string;
  encounter_time: string | null;
  patient_name: string;
  dni: string | null;
  study_type: "Ciclometria" | "Espirometria";
  coverage_type: "Mutual" | "Particular";
  coverage_name: string;
  attendance_status: "no_llego" | "esperando" | "atendido";
  medical_control_today: boolean;
};

const attendanceLabel: Record<AgendaEntry["attendance_status"], string> = {
  no_llego: "No llego",
  esperando: "Esperando",
  atendido: "Atendido",
};

function formatDni(value: string | null) {
  if (!value) return "Sin DNI";
  return new Intl.NumberFormat("es-AR").format(Number(value));
}

function SecretaryAgenda({ entries }: { entries: AgendaEntry[] }) {
  return <section className="secretary-agenda-list" aria-label="Pacientes del dia para secretaria">
    <div className="secretary-agenda-head"><span>Hora</span><span>Paciente</span><span>DNI</span><span>Estudio</span><span>Cobertura</span><span>Asistencia</span></div>
    {entries.length === 0 ? <p className="empty">Todavia no hay pacientes cargados para hoy.</p> : entries.map((entry) => <article className={`secretary-agenda-row ${entry.attendance_status}`} key={entry.encounter_id}>
      <time>{entry.encounter_time?.slice(0, 5) || "--:--"}</time><strong>{entry.patient_name}</strong><b>{formatDni(entry.dni)}</b><span>{shortStudy(entry.study_type)}</span><span>{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</span><div><strong className={entry.attendance_status}>{attendanceLabel[entry.attendance_status]}</strong>{entry.medical_control_today && <small>Control hoy</small>}</div>
    </article>)}
  </section>;
}

function shortStudy(value: AgendaEntry["study_type"]) {
  return value === "Ciclometria" ? "Ciclometria" : "Espirometria";
}

export default async function AgendaPage() {
  const { profile } = await requireProfile(["admin", "secretaria", "espirometrista"]);
  const supabase = await createClient();
  const today = new Date().toISOString().slice(0, 10);
  const { data, error } = await supabase.rpc("secretary_agenda_entries", { target_date: today });
  const entries = (data ?? []) as AgendaEntry[];

  const summary = entries.reduce(
    (result, entry) => {
      result.total += 1;
      result[entry.attendance_status] += 1;
      return result;
    },
    { total: 0, no_llego: 0, esperando: 0, atendido: 0 },
  );

  return (
    <main className="shell">
      <section className={`card agenda-card ${profile.role === "secretaria" ? "secretary-agenda" : "espirometrista-agenda"}`}>
        <div className="agenda-head">
          <div>
            <p className="pill">Agenda {today.split("-").reverse().join("/")}</p>
            <h1 className="section-title">Pacientes del dia</h1>
          </div>
          {profile.role !== "secretaria" && <button className="button alt" type="button" disabled title="La impresion se habilita al portar los informes a Next.">Imprimir todo el dia</button>}
        </div>
        {error && <p className="notice error">No se pudo cargar la agenda: {error.message}</p>}
        <section className="agenda-attendance-summary" aria-label="Resumen de pacientes de hoy">
          <div className="agenda-count total"><strong>{summary.total}</strong><span>Pacientes hoy</span></div>
          <div className="agenda-count attended"><strong>{summary.atendido}</strong><span>Atendidos</span></div>
          <div className="agenda-count no-show"><strong>{summary.no_llego}</strong><span>No llegaron</span></div>
          <div className="agenda-count waiting"><strong>{summary.esperando}</strong><span>Esperando</span></div>
        </section>
        <NewAgendaPatientForm today={today} role={profile.role} />
        {profile.role === "secretaria" && <SecretaryAgenda entries={entries} />}
        <section className={`agenda-work-grid ${profile.role === "secretaria" ? "is-secretary" : "is-operator"}`} aria-label="Pacientes del día">
          <div className="agenda-work-head">
            <span>Hora</span><span>Paciente</span><span>DNI</span><span>Estudio</span><span>Cobertura</span>
            {profile.role !== "secretaria" && <><span>Dr. deriva</span><span>SO2 / FC reposo</span><span>Bronco</span><span>SO2 / FC post</span><span>Resultado</span></>}
            <span>Asistencia</span>{profile.role !== "secretaria" && <><span>Estado</span><span>Acciones</span></>}
          </div>
          {entries.length === 0 ? <p className="empty">Todavía no hay pacientes cargados para hoy.</p> : entries.map((entry) => (
            <article className={`agenda-work-row ${entry.attendance_status}`} key={entry.encounter_id}>
              <time><b>{entry.encounter_time?.slice(0, 5) || "--:--"}</b><span>◷</span></time>
              <label className="agenda-name"><input defaultValue={entry.patient_name} disabled /><span className="sr-only">Paciente</span></label>
              <strong className="agenda-dni">{formatDni(entry.dni)}</strong>
              <select aria-label="Estudio" defaultValue={entry.study_type} disabled><option>{shortStudy(entry.study_type)}</option></select>
              <select aria-label="Cobertura" defaultValue={entry.coverage_type} disabled><option>{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</option></select>
              {profile.role !== "secretaria" && <>
                <label className="agenda-physician"><input defaultValue="Dr. Gustavo Piguillem" disabled /><small>Escribí y elegí un doctor.</small></label>
                <div className="agenda-vitals"><span className="so2">-</span><b>/</b><span className="fc">-</span><button disabled>Guardar</button></div>
                <button className="agenda-bronco" disabled>Bronco</button>
                <div className="agenda-vitals"><span className="so2">-</span><b>/</b><span className="fc">-</span><button disabled>Guardar</button></div>
                <label className="agenda-result"><input placeholder="N, OL, RL, RLOMS..." disabled /></label>
              </>}
              <div className="agenda-attendance"><strong className={entry.attendance_status}>{attendanceLabel[entry.attendance_status]}</strong>{entry.medical_control_today && <span>Control hoy</span>}</div>
              {profile.role !== "secretaria" && <><span className="agenda-status">{entry.attendance_status === "atendido" ? "Cargada" : "Pendiente"}</span><div className="agenda-actions"><button className="agenda-print" disabled>Imprimir</button><span>Editar</span><Link href={`/revision-medica/${entry.encounter_id}`}>Revision</Link><span>Eliminar</span></div></>}
            </article>
          ))}
        </section>
      </section>
    </main>
  );
}
