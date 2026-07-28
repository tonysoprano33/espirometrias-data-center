import Link from "next/link";
import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";

type Encounter = { id: string; encounter_date: string; attendance_status: "no_llego" | "esperando" | "atendido"; coverage_type: "Mutual" | "Particular"; coverage_name: string };
type Result = { encounter_id: string; respiratory_pattern: string | null; bronchodilator_positive: boolean };

const pad = (value: number) => String(value).padStart(2, "0");
const monthValue = (value: string | undefined) => /^\d{4}-\d{2}$/.test(value ?? "") ? value! : new Date().toISOString().slice(0, 7);

export default async function StatisticsPage({ searchParams }: { searchParams: Promise<{ mes?: string }> }) {
  await requireProfile(["admin", "espirometrista"]);
  const params = await searchParams;
  const month = monthValue(params.mes);
  const [year, monthNumber] = month.split("-").map(Number);
  const nextMonth = `${year + (monthNumber === 12 ? 1 : 0)}-${pad(monthNumber === 12 ? 1 : monthNumber + 1)}`;
  const previousMonth = `${year - (monthNumber === 1 ? 1 : 0)}-${pad(monthNumber === 1 ? 12 : monthNumber - 1)}`;
  const supabase = await createClient();
  const { data: encounterData, error } = await supabase.from("encounters").select("id, encounter_date, attendance_status, coverage_type, coverage_name").gte("encounter_date", `${month}-01`).lt("encounter_date", `${nextMonth}-01`).is("deleted_at", null);
  const encounters = (encounterData ?? []) as Encounter[];
  const ids = encounters.map((encounter) => encounter.id);
  const { data: resultData } = ids.length ? await supabase.from("spirometry_results").select("encounter_id, respiratory_pattern, bronchodilator_positive").in("encounter_id", ids) : { data: [] };
  const results = (resultData ?? []) as Result[];
  const attended = encounters.filter((entry) => entry.attendance_status === "atendido").length;
  const noShow = encounters.filter((entry) => entry.attendance_status === "no_llego").length;
  const mutuals = encounters.filter((entry) => entry.coverage_type === "Mutual").length;
  const resultTotal = results.filter((entry) => entry.respiratory_pattern).length;
  const normal = results.filter((entry) => entry.respiratory_pattern === "N").length;
  const bronco = results.filter((entry) => entry.bronchodilator_positive).length;
  const coverageRows = [...encounters.filter((entry) => entry.coverage_type === "Mutual").reduce((map, entry) => map.set(entry.coverage_name || "Mutual", (map.get(entry.coverage_name || "Mutual") ?? 0) + 1), new Map<string, number>())].sort((a, b) => b[1] - a[1]);
  const resultRows = [...results.filter((entry) => entry.respiratory_pattern).reduce((map, entry) => map.set(entry.respiratory_pattern!, (map.get(entry.respiratory_pattern!) ?? 0) + 1), new Map<string, number>())].sort((a, b) => b[1] - a[1]);
  const days = new Map<string, Encounter[]>();
  for (const encounter of encounters) days.set(encounter.encounter_date, [...(days.get(encounter.encounter_date) ?? []), encounter]);
  const label = new Intl.DateTimeFormat("es-AR", { month: "long", year: "numeric" }).format(new Date(`${month}-01T12:00:00`));
  const attendancePercent = encounters.length ? Math.round((attended / encounters.length) * 100) : 0;
  const maxCoverage = Math.max(...coverageRows.map(([, total]) => total), 1);
  const maxResult = Math.max(...resultRows.map(([, total]) => total), 1);

  return <main className="shell">
    <section className="legacy-statistics-head"><div><p className="pill">Analisis mensual</p><h1>{label} en una sola vista</h1><span>Actividad, asistencia, resultados y mutuales del periodo seleccionado.</span></div><div><Link href={`/estadistica?mes=${previousMonth}`}>Anterior</Link><Link href={`/estadistica?mes=${nextMonth}`}>Siguiente</Link></div></section>
    {error && <p className="notice error">No se pudieron cargar las estadisticas: {error.message}</p>}
    <section className="legacy-stat-metrics"><Metric value={encounters.length} label="Pacientes cargados" tone="blue" /><Metric value={`${attendancePercent}%`} label="Asistencia" tone="green" /><Metric value={resultTotal} label="Resultados guardados" tone="teal" /><Metric value={mutuals} label="Atenciones mutuales" tone="amber" /><Metric value={noShow} label="No llegaron" tone="rose" /><Metric value={bronco} label="Bronco positivo" tone="purple" /></section>
    <section className="legacy-stat-grid"><StatPanel title="Mutuales del mes" description="Distribucion por cobertura mutual."><Bars rows={coverageRows} max={maxCoverage} empty="No hubo atenciones mutuales en este periodo." /></StatPanel><StatPanel title="Resultados finales" description="Solo diagnosticos guardados en la historia clinica."><Bars rows={resultRows} max={maxResult} empty="Todavia no hay resultados guardados este mes." /></StatPanel></section>
    <section className="legacy-stat-grid"><StatPanel title="Lectura clinica" description="Resumen rapido de los resultados confirmados."><div className="legacy-clinical-metrics"><div><strong>{normal}</strong><span>Normales</span></div><div><strong>{Math.max(resultTotal - normal, 0)}</strong><span>Con alteracion</span></div><div><strong>{bronco}</strong><span>Broncodilatador positivo</span></div></div></StatPanel><StatPanel title="Actividad diaria" description="Pacientes y asistencia por jornada."><div className="legacy-daily-list">{[...days.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, entries]) => <div key={date}><strong>{new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit" }).format(new Date(`${date}T12:00:00`))}</strong><span>{entries.length} pacientes</span><b>{entries.filter((entry) => entry.attendance_status === "atendido").length} atendidos</b></div>)}{days.size === 0 && <p className="empty">No hay actividad en este periodo.</p>}</div></StatPanel></section>
  </main>;
}

function Metric({ value, label, tone }: { value: string | number; label: string; tone: string }) { return <div className={tone}><strong>{value}</strong><span>{label}</span></div>; }
function StatPanel({ title, description, children }: { title: string; description: string; children: React.ReactNode }) { return <section className="legacy-stat-panel"><header><h2>{title}</h2><p>{description}</p></header>{children}</section>; }
function Bars({ rows, max, empty }: { rows: [string, number][]; max: number; empty: string }) { return rows.length ? <div className="legacy-bars">{rows.map(([label, total]) => <div key={label}><span><b>{label}</b><small>{total} casos</small></span><i><em style={{ width: `${Math.max(8, Math.round((total / max) * 100))}%` }} /></i><strong>{total}</strong></div>)}</div> : <p className="empty">{empty}</p>; }
