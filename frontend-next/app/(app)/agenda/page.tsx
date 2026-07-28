import { createClient } from "../../lib/supabase/server";
import { requireProfile } from "../../lib/auth/require-profile";
import { NewAgendaPatientForm } from "./new-agenda-patient-form";
import { OperatorAgendaRow } from "./operator-agenda-row";

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
  so2_rest?: number | null;
  fc_rest?: number | null;
  so2_post?: number | null;
  fc_post?: number | null;
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

function shortStudy(value: AgendaEntry["study_type"]) {
  return value === "Ciclometria" ? "Ciclometria" : "Espirometria";
}

function SecretaryAgenda({ entries }: { entries: AgendaEntry[] }) {
  return <section className="secretary-agenda-list" aria-label="Pacientes del dia para secretaria">
    <div className="secretary-agenda-head"><span>Hora</span><span>Paciente</span><span>DNI</span><span>Estudio</span><span>Cobertura</span><span>Asistencia</span></div>
    {entries.length === 0 ? <p className="empty">Todavia no hay pacientes cargados para hoy.</p> : entries.map((entry) => <article className={`secretary-agenda-row ${entry.attendance_status}`} key={entry.encounter_id}>
      <time>{entry.encounter_time?.slice(0, 5) || "--:--"}</time><strong>{entry.patient_name}</strong><b>{formatDni(entry.dni)}</b><span>{shortStudy(entry.study_type)}</span><span>{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</span><div><strong className={entry.attendance_status}>{attendanceLabel[entry.attendance_status]}</strong>{entry.medical_control_today && <small>Control hoy</small>}</div>
    </article>)}
  </section>;
}

export default async function AgendaPage() {
  const { profile } = await requireProfile(["admin", "secretaria", "espirometrista"]);
  const supabase = await createClient();
  const today = new Date().toISOString().slice(0, 10);
  const { data, error } = await supabase.rpc("secretary_agenda_entries", { target_date: today });
  let entries = (data ?? []) as AgendaEntry[];

  if (entries.length > 0 && profile.role !== "secretaria") {
    const { data: vitalRows } = await supabase.from("vital_signs").select("encounter_id, so2_rest, fc_rest, so2_post, fc_post").in("encounter_id", entries.map((entry) => entry.encounter_id));
    const vitalMap = new Map((vitalRows ?? []).map((row) => [row.encounter_id, row]));
    entries = entries.map((entry) => ({ ...entry, ...(vitalMap.get(entry.encounter_id) ?? {}) }));
  }

  const summary = entries.reduce(
    (result, entry) => { result.total += 1; result[entry.attendance_status] += 1; return result; },
    { total: 0, no_llego: 0, esperando: 0, atendido: 0 },
  );

  return <main className="shell">
    <section className={`card agenda-card ${profile.role === "secretaria" ? "secretary-agenda" : "espirometrista-agenda"}`}>
      <div className="agenda-head"><div><p className="pill">Agenda {today.split("-").reverse().join("/")}</p><h1 className="section-title">Pacientes del dia</h1></div>
        {profile.role !== "secretaria" && <button className="button alt" type="button" disabled title="La impresion se habilita al portar los informes a Next.">Imprimir todo el dia</button>}
      </div>
      {error && <p className="notice error">No se pudo cargar la agenda: {error.message}</p>}
      <section className="agenda-attendance-summary" aria-label="Resumen de pacientes de hoy">
        <div className="agenda-count total"><strong>{summary.total}</strong><span>Pacientes hoy</span></div><div className="agenda-count attended"><strong>{summary.atendido}</strong><span>Atendidos</span></div><div className="agenda-count no-show"><strong>{summary.no_llego}</strong><span>No llegaron</span></div><div className="agenda-count waiting"><strong>{summary.esperando}</strong><span>Esperando</span></div>
      </section>
      <NewAgendaPatientForm today={today} role={profile.role} />
      {profile.role === "secretaria" && <SecretaryAgenda entries={entries} />}
      <section className={`agenda-work-grid ${profile.role === "secretaria" ? "is-secretary" : "is-operator"}`} aria-label="Pacientes del dia">
        <div className="agenda-work-head"><span>Hora</span><span>Paciente</span><span>DNI</span><span>Estudio</span><span>Cobertura</span>{profile.role !== "secretaria" && <><span>Dr. deriva</span><span>SO2 / FC reposo</span><span>SO2 / FC post</span><span>Resultado</span></>}<span>Asistencia</span>{profile.role !== "secretaria" && <><span>Estado</span><span>Acciones</span></>}</div>
        {entries.length === 0 ? <p className="empty">Todavia no hay pacientes cargados para hoy.</p> : entries.map((entry) => profile.role !== "secretaria" ? <OperatorAgendaRow key={entry.encounter_id} entry={entry} /> : null)}
      </section>
    </section>
  </main>;
}
