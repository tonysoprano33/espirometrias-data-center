import Link from "next/link";
import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";

type Patient = { id: string; full_name: string; dni: string | null; phone: string; patient_code: string };
type Encounter = { patient_id: string; encounter_date: string };

const formatDni = (value: string | null) => {
  if (!value) return "-";
  const digits = value.replace(/\D/g, "");
  return digits ? new Intl.NumberFormat("es-AR").format(Number(digits)) : value;
};

export default async function PatientsPage({ searchParams }: { searchParams: Promise<{ q?: string; page?: string }> }) {
  await requireProfile(["admin", "espirometrista"]);
  const { q = "", page: rawPage = "1" } = await searchParams;
  const query = q.trim();
  const page = Math.max(1, Number.parseInt(rawPage, 10) || 1);
  const pageSize = 20;
  const supabase = await createClient();
  let patientsQuery = supabase.from("patients")
    .select("id, full_name, dni, phone, patient_code", { count: "exact" })
    .is("deleted_at", null)
    .order("full_name", { ascending: true })
    .range((page - 1) * pageSize, page * pageSize - 1);
  if (query) {
    const safeQuery = query.replace(/[,%]/g, " ").trim();
    patientsQuery = patientsQuery.or(`full_name.ilike.%${safeQuery}%,dni.ilike.%${safeQuery}%,phone.ilike.%${safeQuery}%,patient_code.ilike.%${safeQuery}%`);
  }
  const { data: patientData, error, count } = await patientsQuery;
  const patients = (patientData ?? []) as Patient[];
  const totalPages = Math.max(1, Math.ceil((count ?? 0) / pageSize));
  const ids = patients.map((patient) => patient.id);
  const { data: encounterData } = ids.length
    ? await supabase.from("encounters").select("patient_id, encounter_date").in("patient_id", ids).is("deleted_at", null)
    : { data: [] };
  const summary = new Map<string, { count: number; lastDate: string | null }>();
  for (const visit of (encounterData ?? []) as Encounter[]) {
    const current = summary.get(visit.patient_id) ?? { count: 0, lastDate: null };
    current.count += 1;
    current.lastDate = !current.lastDate || visit.encounter_date > current.lastDate ? visit.encounter_date : current.lastDate;
    summary.set(visit.patient_id, current);
  }
  const pageUrl = (target: number) => `/pacientes?${new URLSearchParams({ ...(query ? { q: query } : {}), page: String(target) })}`;

  return <main className="shell patient-page-shell">
    <section className="card patient-hero"><div className="patient-hero-head"><div><p className="pill">Base de pacientes</p><h1 className="section-title">Pacientes</h1><p className="muted">Busca por DNI, nombre, telefono o codigo sin perder de vista la historia clinica.</p></div><Link className="button" href="/agenda">Nuevo paciente</Link></div></section>
    <section className="card patient-filter-card"><form className="clinical-search-form" method="get"><label className="field clinical-search-field" htmlFor="q"><span>Buscador clinico</span><input className="clinical-search-input" id="q" name="q" defaultValue={query} placeholder="Nombre, DNI, telefono o codigo..." /></label><button className="button clinical-search-button" type="submit">Buscar</button><p className="clinical-search-hint">Ejemplos: <strong>Grassi</strong>, <strong>32.455.323</strong> o <strong>RLOMS</strong>.</p></form></section>
    {error && <p className="notice error">No se pudieron cargar los pacientes: {error.message}</p>}
    <section className="patient-table-wrap" aria-label="Listado de pacientes"><table className="table patient-table"><thead><tr><th>Paciente</th><th>DNI</th><th>Telefono</th><th>Codigo</th><th>Atenciones</th><th>Ultima atencion</th><th>Acciones</th></tr></thead><tbody>
      {patients.length === 0 ? <tr><td colSpan={7}>No hay pacientes que coincidan con la busqueda.</td></tr> : patients.map((patient) => { const visits = summary.get(patient.id) ?? { count: 0, lastDate: null }; return <tr key={patient.id}><td data-label="Paciente"><div className="patient-primary"><span className="patient-accent" /><strong>{patient.full_name}</strong></div></td><td data-label="DNI"><span className="data-pill dni">{formatDni(patient.dni)}</span></td><td data-label="Telefono"><span className="data-pill phone">{patient.phone || "-"}</span></td><td data-label="Codigo"><span className="data-pill code">{patient.patient_code || "-"}</span></td><td data-label="Atenciones"><span className="count-badge">{visits.count}</span></td><td data-label="Ultima atencion"><div className="last-visit"><strong>{visits.lastDate ? new Intl.DateTimeFormat("es-AR").format(new Date(`${visits.lastDate}T12:00:00`)) : "-"}</strong><span>Ultima visita</span></div></td><td data-label="Acciones"><div className="patient-actions"><Link href={`/pacientes/${patient.id}`} className="primary">Abrir historia</Link></div></td></tr>; })}
    </tbody></table></section>
    <nav className="patient-pagination" aria-label="Paginacion de pacientes">{page > 1 ? <Link href={pageUrl(page - 1)}>Anterior</Link> : <span className="patient-pagination-disabled">Anterior</span>}<span className="patient-pagination-current">Pagina {page} de {totalPages}</span>{page < totalPages ? <Link href={pageUrl(page + 1)}>Siguiente</Link> : <span className="patient-pagination-disabled">Siguiente</span>}{query && <Link href="/pacientes">Limpiar busqueda</Link>}</nav>
  </main>;
}
