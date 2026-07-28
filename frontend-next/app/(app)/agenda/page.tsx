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

export default async function AgendaPage() {
  await requireProfile(["admin", "secretaria", "espirometrista"]);
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
    <main className="next-screen">
      <section className="next-page-heading">
        <p className="eyebrow">Agenda actual</p>
        <h1>Pacientes de hoy</h1>
        <p>Vista de lectura conectada directamente a Supabase. Las ediciones siguen en el sistema actual durante la migracion.</p>
      </section>

      <NewAgendaPatientForm today={today} />

      {error && <p className="notice error">No se pudo cargar la agenda: {error.message}</p>}
      <section className="summary" aria-label="Resumen de agenda">
        <div className="metric blue"><strong>{summary.total}</strong><span>Pacientes</span></div>
        <div className="metric green"><strong>{summary.atendido}</strong><span>Atendidos</span></div>
        <div className="metric amber"><strong>{summary.esperando}</strong><span>Esperando</span></div>
        <div className="metric rose"><strong>{summary.no_llego}</strong><span>No llegaron</span></div>
      </section>

      <section className="agenda-card">
        <header className="agenda-card-head"><h2>Agenda del dia</h2><small>{today.split("-").reverse().join("/")}</small></header>
        {entries.length === 0 ? (
          <p className="empty">No hay pacientes cargados para hoy.</p>
        ) : entries.map((entry) => (
          <article className={`next-agenda-row ${entry.attendance_status}`} key={entry.encounter_id}>
            <time>{entry.encounter_time?.slice(0, 5) || "--:--"}</time>
            <div className="patient-main"><strong>{entry.patient_name}</strong><span>DNI {formatDni(entry.dni)}</span></div>
            <div className="tags"><span>{entry.study_type}</span><span>{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</span>{entry.medical_control_today && <span className="control">Control hoy</span>}</div>
            <span className={`attendance ${entry.attendance_status}`}>{attendanceLabel[entry.attendance_status]}</span>
          </article>
        ))}
      </section>
    </main>
  );
}
