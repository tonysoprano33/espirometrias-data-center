import Link from "next/link";
import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";

type EncounterRow = {
  id: string;
  encounter_date: string;
  encounter_time: string | null;
  attendance_status: "no_llego" | "esperando" | "atendido";
  coverage_type: "Mutual" | "Particular";
  study_type: "Ciclometria" | "Espirometria";
  patient: { full_name: string; dni: string | null } | null;
};

const weekDays = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"];
const pad = (value: number) => String(value).padStart(2, "0");
const isoDate = (date: Date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

function monthStart(value: string | undefined) {
  const parsed = value && /^\d{4}-\d{2}$/.test(value) ? new Date(`${value}-01T12:00:00`) : new Date();
  return new Date(parsed.getFullYear(), parsed.getMonth(), 1, 12);
}

function formatDni(value: string | null) {
  if (!value) return "Sin DNI";
  const numeric = Number(value.replace(/\D/g, ""));
  return Number.isFinite(numeric) ? new Intl.NumberFormat("es-AR").format(numeric) : value;
}

export default async function CalendarPage({ searchParams }: { searchParams: Promise<{ mes?: string; fecha?: string }> }) {
  await requireProfile(["admin", "espirometrista"]);
  const params = await searchParams;
  const month = monthStart(params.mes);
  const nextMonth = new Date(month.getFullYear(), month.getMonth() + 1, 1, 12);
  const startIso = isoDate(month);
  const nextIso = isoDate(nextMonth);
  const selectedDate = params.fecha && /^\d{4}-\d{2}-\d{2}$/.test(params.fecha) ? params.fecha : isoDate(new Date());
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("encounters")
    .select("id, encounter_date, encounter_time, attendance_status, coverage_type, study_type, patient:patients(full_name,dni)")
    .gte("encounter_date", startIso)
    .lt("encounter_date", nextIso)
    .is("deleted_at", null)
    .order("encounter_time", { ascending: true, nullsFirst: false });
  const entries = (data ?? []) as unknown as EncounterRow[];
  const byDate = new Map<string, EncounterRow[]>();
  for (const entry of entries) byDate.set(entry.encounter_date, [...(byDate.get(entry.encounter_date) ?? []), entry]);
  const selectedRows = byDate.get(selectedDate) ?? [];
  const monthName = new Intl.DateTimeFormat("es-AR", { month: "long", year: "numeric" }).format(month);
  const selectedLabel = new Intl.DateTimeFormat("es-AR", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(`${selectedDate}T12:00:00`));
  const today = isoDate(new Date());
  const gridStart = new Date(month);
  gridStart.setDate(gridStart.getDate() - ((gridStart.getDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart);
    date.setDate(gridStart.getDate() + index);
    const dateIso = isoDate(date);
    const dayEntries = byDate.get(dateIso) ?? [];
    const attended = dayEntries.filter((entry) => entry.attendance_status === "atendido").length;
    return { date, dateIso, entries: dayEntries, attended, inMonth: date.getMonth() === month.getMonth() };
  });
  const mutual = selectedRows.filter((entry) => entry.coverage_type === "Mutual").length;
  const attended = selectedRows.filter((entry) => entry.attendance_status === "atendido").length;
  const noShow = selectedRows.filter((entry) => entry.attendance_status === "no_llego").length;

  return <main className="shell">
    <section className="legacy-calendar-board">
      <header className="legacy-calendar-head">
        <div><p className="pill">Mes activo</p><h1>{monthName}</h1><span>Dias normalmente no laborables: Lunes, Miercoles, Sabado, Domingo.</span></div>
        <div className="legacy-month-actions"><Link href={`/calendario?mes=${new Date(month.getFullYear(), month.getMonth() - 1, 1).toISOString().slice(0, 7)}&fecha=${selectedDate}`}>Anterior</Link><Link href="/calendario">Hoy</Link><Link href={`/calendario?mes=${nextIso.slice(0, 7)}&fecha=${selectedDate}`}>Siguiente</Link></div>
      </header>
      {error && <p className="notice error">No se pudo cargar el calendario: {error.message}</p>}
      <div className="legacy-calendar-legend"><span><i className="has" /> Dia con pacientes</span><span><i className="done" /> Dia completo / todos atendidos</span><span><i className="off" /> Dia no habitual</span><span><i className="empty" /> Sin agenda cargada</span></div>
      <div className="legacy-calendar-grid" aria-label={`Calendario de ${monthName}`}>
        {weekDays.map((day) => <b key={day}>{day}</b>)}
        {days.map((day) => {
          const allDone = day.entries.length > 0 && day.attended === day.entries.length;
          return <Link key={day.dateIso} className={`legacy-calendar-day ${day.inMonth ? "" : "outside"} ${day.entries.length ? "has-patients" : ""} ${allDone ? "all-done" : ""} ${day.dateIso === selectedDate ? "selected" : ""}`} href={`/calendario?mes=${startIso.slice(0, 7)}&fecha=${day.dateIso}`}>
            <strong>{day.date.getDate()}</strong>
            {day.entries.length ? <><span>{day.entries.length} pacientes</span><small>{allDone ? `Atendidos ${day.attended}` : `${day.attended} atendidos`}</small></> : <small>Sin pacientes</small>}
          </Link>;
        })}
      </div>
    </section>
    <section className="legacy-selected-day">
      <header><div><p className="pill">Dia seleccionado</p><h2>{selectedLabel}</h2><span>Aca tenes el resumen del dia y la lista completa de pacientes.</span></div><b>{selectedRows.length ? "Dia con actividad" : "Sin actividad"}</b></header>
      <div className="legacy-day-metrics"><div><span>Pacientes</span><strong>{selectedRows.length}</strong></div><div><span>Mutuales</span><strong>{mutual}</strong></div><div><span>Atendidos</span><strong>{attended}</strong></div><div><span>Pendientes</span><strong>{selectedRows.length - attended - noShow}</strong></div><div><span>No llego</span><strong>{noShow}</strong></div></div>
      <div className="legacy-selected-list">{selectedRows.length === 0 ? <p className="empty">No hay pacientes cargados para este dia.</p> : selectedRows.map((entry) => <article key={entry.id}><time>{entry.encounter_time?.slice(0, 5) || "--:--"}</time><div><strong>{entry.patient?.full_name ?? "Paciente sin nombre"}</strong><span>{formatDni(entry.patient?.dni ?? null)}</span></div><span>{entry.study_type}</span><span>{entry.coverage_type}</span><b className={entry.attendance_status}>{entry.attendance_status === "atendido" ? "Atendido" : entry.attendance_status === "esperando" ? "Esperando" : "No llego"}</b></article>)}</div>
    </section>
  </main>;
}
