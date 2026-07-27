"use client";

import { useEffect, useState } from "react";

type CalendarRow = {
  encounter_id: number;
  encounter_time: string;
  patient_name: string;
  patient_dni_display: string;
  study_type: string;
  coverage_type: string;
  attendance_label: string;
  result_code: string;
  attended: boolean;
  no_show: boolean;
  patient_url: string;
  print_url: string;
  can_print_result: boolean;
};

type CalendarDay = {
  date: string;
  day_number: number;
  in_month: boolean;
  today: boolean;
  selected: boolean;
  total: number;
  attended: number;
  no_show: number;
  mutual: number;
  pending: number;
  all_attended: boolean;
};

type CalendarPayload = {
  month: string;
  month_label: string;
  previous_month: string;
  next_month: string;
  selected_date: string;
  selected_date_label: string;
  weekdays: string[];
  weeks: CalendarDay[][];
  summary: { total: number; mutual: number; attended: number; pending: number; no_show: number };
  rows: CalendarRow[];
};

function queryValue(name: string) {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) || "";
}

export default function CalendarPage() {
  const [month, setMonth] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [data, setData] = useState<CalendarPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setMonth((current) => current || queryValue("month"));
    setSelectedDate((current) => current || queryValue("date"));
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const params = new URLSearchParams();
        if (month) params.set("month", month);
        if (selectedDate) params.set("date", selectedDate);
        const response = await fetch(`/api/v1/calendario/?${params.toString()}`, { cache: "no-store", credentials: "same-origin" });
        if (!response.ok) throw new Error(response.status === 403 ? "Esta sesion no tiene acceso al calendario." : "No se pudo cargar el calendario.");
        const payload = await response.json() as CalendarPayload;
        if (!active) return;
        setData(payload);
        setError("");
        const nextUrl = `/calendario/?month=${payload.month}&date=${payload.selected_date}`;
        window.history.replaceState({}, "", nextUrl);
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Error de conexion.");
      }
    };
    void load();
    return () => { active = false; };
  }, [month, selectedDate]);

  const selectMonth = (nextMonth: string) => {
    setMonth(nextMonth);
    setSelectedDate(`${nextMonth}-01`);
  };

  return <main className="agenda-shell calendar-next">
    <header className="agenda-header">
      <div><p className="eyebrow">Agenda mensual</p><h1>Calendario</h1><p className="subtitle">Consulta los dias, estados y pacientes sin recargar toda la aplicacion.</p></div>
      <div className="header-actions"><nav className="next-nav" aria-label="Navegacion nueva"><a href="/">Agenda</a><a className="is-current" href="/calendario/">Calendario</a><a href="/estadistica/">Estadisticas</a><a href="/pacientes/">Pacientes</a><a href="/revision-medica/">Revision medica</a></nav><a className="back-link" href="/django/calendario/">Vista actual</a></div>
    </header>
    {error && <p className="notice error" role="alert">{error}</p>}
    {!data && !error && <p className="notice">Cargando calendario...</p>}
    {data && <>
      <section className="calendar-next-toolbar">
        <div><p className="eyebrow">Mes activo</p><h2>{data.month_label}</h2></div>
        <div className="month-controls"><button onClick={() => selectMonth(data.previous_month)}>Anterior</button><button onClick={() => { setMonth(""); setSelectedDate(""); }}>Hoy</button><button onClick={() => selectMonth(data.next_month)}>Siguiente</button></div>
      </section>
      <section className="calendar-next-board" aria-label={`Calendario ${data.month_label}`}>
        <div className="calendar-next-weekdays">{data.weekdays.map((day) => <span key={day}>{day}</span>)}</div>
        <div className="calendar-next-grid">
          {data.weeks.flat().map((day) => <button key={day.date} onClick={() => setSelectedDate(day.date)} className={`calendar-next-day ${!day.in_month ? "outside" : ""} ${day.today ? "today" : ""} ${day.selected ? "selected" : ""} ${day.all_attended ? "all-attended" : ""} ${day.total ? "has-patients" : ""}`}>
            <strong>{day.day_number}</strong>
            {day.total > 0 ? <><span>{day.total} paciente{day.total === 1 ? "" : "s"}</span><small>{day.pending ? `${day.pending} pendiente${day.pending === 1 ? "" : "s"}` : day.no_show ? `${day.no_show} no llego` : "Jornada cerrada"}</small></> : <small>Sin agenda</small>}
          </button>)}
        </div>
      </section>
      <section className="selected-day-card">
        <div className="selected-day-head"><div><p className="eyebrow">Dia seleccionado</p><h2>{data.selected_date_label}</h2></div><span className={data.summary.total ? "day-state active" : "day-state"}>{data.summary.total ? "Dia con actividad" : "Sin actividad"}</span></div>
        <div className="summary summary-five"><Metric label="Pacientes" value={data.summary.total} tone="blue" /><Metric label="Mutuales" value={data.summary.mutual} tone="teal" /><Metric label="Atendidos" value={data.summary.attended} tone="green" /><Metric label="Pendientes" value={data.summary.pending} tone="amber" /><Metric label="No llegaron" value={data.summary.no_show} tone="rose" /></div>
        <div className="calendar-row-list">
          {data.rows.map((row) => <article className={`calendar-next-row ${row.attended ? "attended" : row.no_show ? "no-show" : "waiting"}`} key={row.encounter_id}><time>{row.encounter_time || "Sin hora"}</time><div><strong>{row.patient_name}</strong><span>DNI {row.patient_dni_display}</span></div><div className="tags"><span>{row.study_type}</span><span>{row.coverage_type}</span><span>{row.attendance_label}</span></div><b className="result">{row.result_code || "Sin resultado"}</b><div className="row-actions"><a href={`/django${row.patient_url}`}>Abrir ficha</a>{row.can_print_result && <a className="print-link" href={`/django${row.print_url}`}>Imprimir</a>}</div></article>)}
          {!data.rows.length && <p className="empty">No hay pacientes cargados para este dia.</p>}
        </div>
      </section>
    </>}
  </main>;
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={`metric ${tone}`}><strong>{value}</strong><span>{label}</span></div>;
}
