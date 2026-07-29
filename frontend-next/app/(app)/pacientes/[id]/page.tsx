import Link from "next/link";
import { notFound } from "next/navigation";
import { requireProfile } from "../../../lib/auth/require-profile";
import { createClient } from "../../../lib/supabase/server";

export default async function PatientDetailPage({ params }: { params: Promise<{ id: string }> }) {
  await requireProfile(["admin", "espirometrista"]);
  const { id } = await params;
  const supabase = await createClient();
  const [{ data: patient }, { data: encounters }] = await Promise.all([
    supabase.from("patients").select("id, full_name, dni, patient_code, phone, birth_date, gender, bmi, smoking_status, notes").eq("id", id).is("deleted_at", null).maybeSingle(),
    supabase.from("encounters").select("id, encounter_date, encounter_time, study_type, coverage_type, coverage_name, attendance_status, workflow_status, medical_control_today").eq("patient_id", id).is("deleted_at", null).order("encounter_date", { ascending: false }).order("encounter_time", { ascending: false }),
  ]);
  if (!patient) notFound();

  return <main className="shell patient-detail-shell">
    <header className="patient-detail-hero"><div><p className="pill">Historia del paciente</p><h1>{patient.full_name}</h1><span>{patient.dni ? `DNI ${new Intl.NumberFormat("es-AR").format(Number(patient.dni.replace(/\D/g, "")))}` : "Sin DNI"} · Código {patient.patient_code || "-"}</span></div><Link className="button alt" href="/pacientes">Volver a pacientes</Link></header>
    <section className="patient-detail-facts"><div><small>Teléfono</small><b>{patient.phone || "-"}</b></div><div><small>Fecha de nacimiento</small><b>{patient.birth_date || "-"}</b></div><div><small>Género</small><b>{patient.gender || "-"}</b></div><div><small>BMI</small><b>{patient.bmi || "-"}</b></div><div><small>Fumador</small><b>{patient.smoking_status || "-"}</b></div></section>
    {patient.notes && <section className="card patient-detail-note"><h2>Notas</h2><p>{patient.notes}</p></section>}
    <section className="card patient-history-card"><header><div><p className="pill">Análisis y pruebas previas</p><h2>Atenciones guardadas</h2></div><strong>{encounters?.length ?? 0} registro(s)</strong></header>
      <div className="patient-history-table"><div className="patient-history-head"><span>Fecha</span><span>Hora</span><span>Estudio</span><span>Cobertura</span><span>Estado</span><span>Acciones</span></div>
        {(encounters ?? []).length === 0 ? <p className="empty">Todavía no hay atenciones guardadas.</p> : (encounters ?? []).map((entry) => <article key={entry.id}><time>{new Intl.DateTimeFormat("es-AR").format(new Date(`${entry.encounter_date}T12:00:00`))}</time><span>{entry.encounter_time?.slice(0, 5) || "--:--"}</span><span>{entry.study_type}</span><span>{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</span><b className={entry.attendance_status}>{entry.workflow_status === "informe_generado" ? "Informe generado" : entry.attendance_status === "atendido" ? "Atendido" : entry.attendance_status === "esperando" ? "Esperando" : "No llegó"}</b><span className="patient-history-actions"><Link href={`/atenciones/${entry.id}/editar`}>Editar</Link><Link href={`/revision-medica/${entry.id}`}>Revisión</Link></span></article>)}
      </div>
    </section>
  </main>;
}
