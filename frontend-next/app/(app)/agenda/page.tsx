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
        {entries.length === 0 ? (
          <p className="empty">Todavia no hay pacientes cargados para hoy.</p>
        ) : entries.map((entry) => (
          <article className={`legacy-agenda-row ${entry.attendance_status}`} key={entry.encounter_id}>
            <time>{entry.encounter_time?.slice(0, 5) || "--:--"}</time>
            <div className="legacy-patient"><strong>{entry.patient_name}</strong><span>{formatDni(entry.dni)}</span></div>
            <span className="legacy-study">{entry.study_type}</span>
            <span className="legacy-coverage">{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</span>
            <div className="legacy-attendance"><strong className={entry.attendance_status}>{attendanceLabel[entry.attendance_status]}</strong>{entry.medical_control_today && <span>Control medico hoy</span>}</div>
          </article>
        ))}
      </section>
    </main>
  );
}
