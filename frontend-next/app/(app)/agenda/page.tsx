import { createClient } from "../../lib/supabase/server";
import { requireProfile } from "../../lib/auth/require-profile";
import { NewAgendaPatientForm } from "./new-agenda-patient-form";
import { OperatorAgendaRow } from "./operator-agenda-row";
import Link from "next/link";
import { DrappImport } from "./drapp-import";
import type { AgendaEntry, PhysicianOption } from "./agenda-types";

const attendanceLabel: Record<AgendaEntry["attendance_status"], string> = {
  no_llego: "No llego",
  esperando: "Esperando",
  atendido: "Atendido",
};

function formatDni(value: string | null) {
  if (!value) return "Sin DNI";
  return new Intl.NumberFormat("es-AR").format(Number(value));
}

function shortStudy(value: AgendaEntry["study_type"]) {
  return value === "Ciclometria" ? "Ciclometria" : "Espirometria";
}

function SecretaryAgenda({ entries }: { entries: AgendaEntry[] }) {
  return <section className="secretary-agenda-list" aria-label="Pacientes del dia para secretaria">
    <div className="secretary-agenda-head"><span>Hora</span><span>Paciente</span><span>Estudio</span><span>Cobertura</span><span>Asistencia</span></div>
    {entries.length === 0 ? <p className="empty">Todavia no hay pacientes cargados para hoy.</p> : entries.map((entry) => <article className={`secretary-agenda-row ${entry.attendance_status}`} key={entry.encounter_id}>
      <time>{entry.encounter_time?.slice(0, 5) || "--:--"}</time><div className="secretary-patient-cell"><strong>{entry.patient_name}</strong><span>DNI {formatDni(entry.dni)}</span></div><span>{shortStudy(entry.study_type)}</span><span>{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</span><div><strong className={entry.attendance_status}>{attendanceLabel[entry.attendance_status]}</strong>{entry.medical_control_today && <small>Control hoy</small>}</div>
    </article>)}
  </section>;
}

export default async function AgendaPage() {
  const { profile } = await requireProfile(["admin", "secretaria", "espirometrista"]);
  const supabase = await createClient();
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).format(new Date());
  const [{ data, error }, { data: physicianData }] = await Promise.all([
    supabase.rpc("agenda_entries_v3", { target_date: today }),
    supabase.rpc("agenda_physicians"),
  ]);
  const entries = (data ?? []) as AgendaEntry[];
  const physicians = (physicianData ?? []) as PhysicianOption[];

  const summary = entries.reduce(
    (result, entry) => { result.total += 1; result[entry.attendance_status] += 1; return result; },
    { total: 0, no_llego: 0, esperando: 0, atendido: 0 },
  );

  return <main className="shell">
    <section className={`card agenda-card ${profile.role === "secretaria" ? "secretary-agenda" : "espirometrista-agenda"}`}>
      <div className="agenda-head"><div><p className="pill">Agenda {today.split("-").reverse().join("/")}</p><h1 className="section-title">Pacientes del dia</h1></div>
        {profile.role !== "secretaria" && (entries.length > 0
          ? <Link className="button alt print-day-button" href={`/imprimir-dia?date=${today}`} target="_blank">Imprimir todo el dia</Link>
          : <span className="button alt print-day-button is-disabled" title="Todavia no hay pacientes listos para imprimir">Imprimir todo el dia</span>)}
      </div>
      {error && <p className="notice error">No se pudo cargar la agenda: {error.message}</p>}
      <section className="agenda-attendance-summary" aria-label="Resumen de pacientes de hoy">
        <div className="agenda-count total"><strong>{summary.total}</strong><span>Pacientes hoy</span></div><div className="agenda-count attended"><strong>{summary.atendido}</strong><span>Atendidos</span></div><div className="agenda-count no-show"><strong>{summary.no_llego}</strong><span>No llegaron</span></div><div className="agenda-count waiting"><strong>{summary.esperando}</strong><span>Esperando</span></div>
      </section>
      <NewAgendaPatientForm today={today} role={profile.role} physicians={physicians} />
      {profile.role !== "secretaria" && <DrappImport today={today} physicians={physicians} />}
      {profile.role === "secretaria" && <SecretaryAgenda entries={entries} />}
      <section className={`agenda-work-grid ${profile.role === "secretaria" ? "is-secretary" : "is-operator"}`} aria-label="Pacientes del dia">
        <div className="agenda-work-head"><span>Hora</span><span>Paciente</span><span>DNI</span><span>Est.</span><span>Cob.</span>{profile.role !== "secretaria" && <><span>Médico</span><span>SO2 / FC reposo</span><span>SO2 / FC post</span><span>Prueba</span><span>Resultado</span></>}<span>Asistencia</span>{profile.role !== "secretaria" && <span>Acciones</span>}</div>
        {entries.length === 0 ? <p className="empty">Todavia no hay pacientes cargados para hoy.</p> : entries.map((entry) => profile.role !== "secretaria" ? <OperatorAgendaRow key={entry.encounter_id} entry={entry} physicians={physicians} /> : null)}
      </section>
    </section>
  </main>;
}
