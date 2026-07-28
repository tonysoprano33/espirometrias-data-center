import Link from "next/link";
import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";

type Patient = {
  id: string;
  full_name: string;
  dni: string | null;
  phone: string;
  patient_code: string;
};

type Encounter = {
  patient_id: string;
  encounter_date: string;
};

const formatDni = (value: string | null) => {
  if (!value) return "-";
  const digits = value.replace(/\D/g, "");
  return digits ? new Intl.NumberFormat("es-AR").format(Number(digits)) : value;
};

export default async function PatientsPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  await requireProfile(["admin", "espirometrista"]);
  const { q = "" } = await searchParams;
  const query = q.trim();
  const supabase = await createClient();
  let patientsQuery = supabase
    .from("patients")
    .select("id, full_name, dni, phone, patient_code")
    .is("deleted_at", null)
    .order("full_name", { ascending: true })
    .limit(20);

  if (query) {
    const safeQuery = query.replace(/[,%]/g, " ").trim();
    patientsQuery = patientsQuery.or(`full_name.ilike.%${safeQuery}%,dni.ilike.%${safeQuery}%,phone.ilike.%${safeQuery}%,patient_code.ilike.%${safeQuery}%`);
  }

  const { data: patientData, error } = await patientsQuery;
  const patients = (patientData ?? []) as Patient[];
  const ids = patients.map((patient) => patient.id);
  const { data: encounterData } = ids.length
    ? await supabase.from("encounters").select("patient_id, encounter_date").in("patient_id", ids).is("deleted_at", null)
    : { data: [] };
  const visits = (encounterData ?? []) as Encounter[];
  const summary = new Map<string, { count: number; lastDate: string | null }>();
  for (const visit of visits) {
    const current = summary.get(visit.patient_id) ?? { count: 0, lastDate: null };
    current.count += 1;
    current.lastDate = !current.lastDate || visit.encounter_date > current.lastDate ? visit.encounter_date : current.lastDate;
    summary.set(visit.patient_id, current);
  }

  return (
    <main className="shell patient-page-shell">
      <section className="card patient-hero">
        <div className="patient-hero-head">
          <div>
            <p className="pill">Base de pacientes</p>
            <h1 className="section-title">Pacientes</h1>
            <p className="muted">Busca por DNI, nombre, teléfono o código sin perder de vista la historia clínica.</p>
          </div>
          <button className="button" type="button" disabled title="La creación se conecta después de validar este flujo.">Nuevo paciente</button>
        </div>
      </section>

      <section className="card patient-filter-card">
        <form className="clinical-search-form" method="get">
          <label className="field clinical-search-field" htmlFor="q">
            <span>Buscador clínico</span>
            <input className="clinical-search-input" id="q" name="q" defaultValue={query} placeholder="Nombre, DNI, teléfono o código..." />
          </label>
          <button className="button clinical-search-button" type="submit">Buscar</button>
          <p className="clinical-search-hint">Ejemplos: <strong>Grassi</strong>, <strong>32.455.323</strong> o <strong>RLOMS</strong>.</p>
        </form>
        <details className="advanced-filters">
          <summary>Filtros detallados</summary>
          <div className="patient-filter-grid">
            <label className="field"><span>Fecha</span><input disabled type="date" /></label>
            <label className="field"><span>Obra social</span><select disabled><option>Todas</option></select></label>
            <label className="field"><span>Diagnóstico</span><input disabled placeholder="N, OL, OMS, RLOMS..." /></label>
            <label className="field"><span>Estado</span><select disabled><option>Todos</option></select></label>
          </div>
        </details>
      </section>

      {error && <p className="notice error">No se pudieron cargar los pacientes: {error.message}</p>}
      <section className="patient-table-wrap" aria-label="Listado de pacientes">
        <table className="table patient-table">
          <thead><tr><th>Paciente</th><th>DNI</th><th>Teléfono</th><th>Código</th><th>Atenciones</th><th>Última atención</th><th>Acciones</th></tr></thead>
          <tbody>
            {patients.length === 0 ? <tr><td colSpan={7}>No hay pacientes que coincidan con la búsqueda.</td></tr> : patients.map((patient) => {
              const visitsForPatient = summary.get(patient.id) ?? { count: 0, lastDate: null };
              return <tr key={patient.id}>
                <td data-label="Paciente"><div className="patient-primary"><span className="patient-accent" /><strong>{patient.full_name}</strong></div></td>
                <td data-label="DNI"><span className="data-pill dni">{formatDni(patient.dni)}</span></td>
                <td data-label="Teléfono"><span className="data-pill phone">{patient.phone || "-"}</span></td>
                <td data-label="Código"><span className="data-pill code">{patient.patient_code || "-"}</span></td>
                <td data-label="Atenciones"><span className="count-badge">{visitsForPatient.count}</span></td>
                <td data-label="Última atención"><div className="last-visit"><strong>{visitsForPatient.lastDate ? new Intl.DateTimeFormat("es-AR").format(new Date(`${visitsForPatient.lastDate}T12:00:00`)) : "-"}</strong><span>Última visita</span></div></td>
                <td data-label="Acciones"><div className="patient-actions"><button type="button" className="primary" disabled>Abrir</button><button type="button" className="secondary" disabled>Editar</button><button type="button" className="danger" disabled>Eliminar</button></div></td>
              </tr>;
            })}
          </tbody>
        </table>
      </section>
      <nav className="patient-pagination" aria-label="Paginación de pacientes"><span className="patient-pagination-disabled">Anterior</span><span className="patient-pagination-current">Mostrando hasta 20 pacientes</span><Link href="/pacientes">Limpiar búsqueda</Link><span className="patient-pagination-disabled">Siguiente</span></nav>
    </main>
  );
}
