import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";
import { RestoreEncounterButton, RestorePatientButton } from "./trash-actions";

type DeletedPatient = { id: string; full_name: string; dni: string | null; deleted_at: string | null };
type DeletedEncounter = { id: string; encounter_date: string; study_type: string; deleted_at: string | null; patient: { full_name: string } | null };

export default async function TrashPage() {
  await requireProfile(["admin", "espirometrista"]);
  const supabase = await createClient();
  const [{ data: patientData, error: patientError }, { data: encounterData, error: encounterError }] = await Promise.all([
    supabase.from("patients").select("id, full_name, dni, deleted_at").not("deleted_at", "is", null).order("deleted_at", { ascending: false }).limit(20),
    supabase.from("encounters").select("id, encounter_date, study_type, deleted_at, patient:patients(full_name)").not("deleted_at", "is", null).order("deleted_at", { ascending: false }).limit(20),
  ]);
  const patients = (patientData ?? []) as DeletedPatient[];
  const encounters = (encounterData ?? []) as unknown as DeletedEncounter[];
  const formatDateTime = (value: string | null) => value ? new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "-";

  return <main className="shell trash-page-shell">
    <section className="card trash-hero">
      <div><p className="pill">Papelera de reciclaje</p><h1 className="section-title">Elementos eliminados</h1><p className="muted">Los elementos borrados permanecen disponibles para restauración. Las acciones se conectan después de validar la migración.</p></div>
      <button className="button danger" type="button" disabled>Vaciar papelera</button>
    </section>
    {(patientError || encounterError) && <p className="notice error">No se pudo cargar la papelera: {patientError?.message ?? encounterError?.message}</p>}
    <section className="stats-strip trash-stats"><div className="stat"><span>Pacientes eliminados</span><strong>{patients.length}</strong></div><div className="stat amber"><span>Atenciones eliminadas</span><strong>{encounters.length}</strong></div><div className="stat green"><span>Borrado automático</span><strong>Desactivado</strong></div></section>
    <TrashTable title="Pacientes en papelera" description="Restaurar recupera también sus atenciones borradas." headers={["Paciente", "DNI", "Eliminado el", "Acciones"]} empty="No hay pacientes eliminados.">
      {patients.map((patient) => <tr key={patient.id}><td><strong>{patient.full_name}</strong></td><td>{patient.dni || "-"}</td><td>{formatDateTime(patient.deleted_at)}</td><td><div className="trash-actions"><RestorePatientButton patientId={patient.id} /><button className="danger" type="button" disabled title="El borrado definitivo requiere una politica de purga separada">Borrar definitivo</button></div></td></tr>)}
    </TrashTable>
    <TrashTable title="Atenciones en papelera" description="Podés restaurar una atención individual aunque el paciente siga activo." headers={["Paciente", "Fecha", "Estudio", "Eliminado el", "Acciones"]} empty="No hay atenciones eliminadas.">
      {encounters.map((encounter) => <tr key={encounter.id}><td><strong>{encounter.patient?.full_name ?? "Paciente eliminado"}</strong></td><td>{new Intl.DateTimeFormat("es-AR").format(new Date(`${encounter.encounter_date}T12:00:00`))}</td><td>{encounter.study_type}</td><td>{formatDateTime(encounter.deleted_at)}</td><td><div className="trash-actions"><RestoreEncounterButton encounterId={encounter.id} /><button className="danger" type="button" disabled title="El borrado definitivo requiere una politica de purga separada">Borrar definitivo</button></div></td></tr>)}
    </TrashTable>
  </main>;
}

function TrashTable({ title, description, headers, empty, children }: { title: string; description: string; headers: string[]; empty: string; children: React.ReactNode }) {
  const hasRows = Array.isArray(children) ? children.length > 0 : Boolean(children);
  return <section className="card trash-section"><header><div><h2 className="section-title">{title}</h2><p className="muted">{description}</p></div></header><div className="table-wrap"><table className="table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{hasRows ? children : <tr><td colSpan={headers.length}>{empty}</td></tr>}</tbody></table></div></section>;
}
