"use client";

import { type ReactNode, useEffect, useState } from "react";

type MetricRow = { name?: string; code?: string; label: string; total: number; share_percent?: number; attendance_percent?: number; with_result?: number; percent?: number };
type StatisticsPayload = {
  month: string;
  month_label: string;
  range_label: string;
  previous_month: string;
  next_month: string;
  can_go_next: boolean;
  summary: { total: number; attended: number; no_show: number; mutual: number; mutual_percent: number; attendance_percent: number };
  clinical: { with_result: number; result_completion_percent: number; normal: number; altered: number; bronchodilator_positive: number; so2_drop_4_or_more: number };
  operational: { waiting_average_minutes: number | null; care_average_minutes: number | null; total_average_minutes: number | null; waiting_samples: number; care_samples: number; total_samples: number };
  mutuals: MetricRow[];
  diagnoses: MetricRow[];
  daily: Array<{ date: string; label: string; total: number; attended: number; no_show: number }>;
};

const valueOrDash = (value: number | null) => value == null ? "-" : `${value} min`;

export default function StatisticsPage() {
  const [month, setMonth] = useState("");
  const [data, setData] = useState<StatisticsPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { if (!month) setMonth(new URLSearchParams(window.location.search).get("month") || ""); }, [month]);
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/v1/estadistica/${month ? `?month=${month}` : ""}`, { cache: "no-store", credentials: "same-origin" });
        if (!response.ok) throw new Error(response.status === 403 ? "Esta sesion no tiene acceso a estadisticas." : "No se pudieron cargar las estadisticas.");
        const payload = await response.json() as StatisticsPayload;
        if (!active) return;
        setData(payload); setError(""); window.history.replaceState({}, "", `/estadistica/?month=${payload.month}`);
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : "Error de conexion."); }
    };
    void load(); return () => { active = false; };
  }, [month]);

  return <main className="agenda-shell statistics-next">
    <header className="agenda-header"><div><p className="eyebrow">Analisis operativo</p><h1>Estadisticas</h1><p className="subtitle">Indicadores mensuales de actividad, cobertura y resultados ya guardados.</p></div><div className="header-actions"><nav className="next-nav" aria-label="Navegacion nueva"><a href="/">Agenda</a><a href="/calendario/">Calendario</a><a className="is-current" href="/estadistica/">Estadisticas</a></nav><a className="back-link" href="/django/estadistica/">Analisis completo</a></div></header>
    {error && <p className="notice error" role="alert">{error}</p>}{!data && !error && <p className="notice">Calculando estadisticas...</p>}
    {data && <>
      <section className="statistics-next-head"><div><p className="eyebrow">Periodo</p><h2>{data.month_label}</h2><span>{data.range_label}</span></div><div className="month-controls"><button onClick={() => setMonth(data.previous_month)}>Anterior</button><button disabled={!data.can_go_next} onClick={() => setMonth(data.next_month)}>Siguiente</button></div></section>
      <section className="summary stat-summary"><Metric label="Pacientes del mes" value={data.summary.total} tone="blue" /><Metric label="Asistencia" value={`${data.summary.attendance_percent}%`} tone="green" /><Metric label="Resultados" value={data.clinical.with_result} tone="teal" /><Metric label="Mutuales" value={data.summary.mutual} tone="amber" /></section>
      <section className="statistics-grid"><Panel title="Tiempos operativos" description="Se calculan solo con etapas completas de la atencion."><div className="operational-grid"><DataMetric label="Espera promedio" value={valueOrDash(data.operational.waiting_average_minutes)} detail={`${data.operational.waiting_samples} registros`} /><DataMetric label="Atencion promedio" value={valueOrDash(data.operational.care_average_minutes)} detail={`${data.operational.care_samples} registros`} /><DataMetric label="Tiempo total" value={valueOrDash(data.operational.total_average_minutes)} detail={`${data.operational.total_samples} registros`} /></div></Panel>
      <Panel title="Lecturas finales" description="Solo cuenta resultados guardados por el medico."><div className="operational-grid"><DataMetric label="Normales" value={data.clinical.normal} detail="Resultado N" /><DataMetric label="Con alteracion" value={data.clinical.altered} detail="Resultados no normales" /><DataMetric label="Bronco positivo" value={data.clinical.bronchodilator_positive} detail="Marcado en informe" /><DataMetric label="Caida SO2 4+" value={data.clinical.so2_drop_4_or_more} detail="Reposo vs post" /></div></Panel></section>
      <section className="statistics-grid"><Panel title="Mutuales" description="Distribucion mensual por cobertura mutual."><BarList rows={data.mutuals} kind="mutual" empty="No hubo atenciones mutuales en este periodo." /></Panel><Panel title="Resultados por codigo" description="Distribucion de resultados finales guardados."><BarList rows={data.diagnoses} kind="diagnosis" empty="Todavia no hay resultados guardados este mes." /></Panel></section>
      <Panel title="Actividad diaria" description="Lectura rapida de pacientes cargados y atendidos por dia."><div className="daily-list">{data.daily.filter((day) => day.total > 0).map((day) => <div key={day.date}><strong>{day.label}</strong><span>{day.total} cargados</span><b>{day.attended} atendidos</b>{day.no_show > 0 && <em>{day.no_show} no llego</em>}</div>)}{!data.daily.some((day) => day.total > 0) && <p className="empty">No hay actividad en este periodo.</p>}</div></Panel>
    </>}
  </main>;
}

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) { return <section className="statistics-panel"><div><h2>{title}</h2><p>{description}</p></div>{children}</section>; }
function DataMetric({ label, value, detail }: { label: string; value: string | number; detail: string }) { return <div className="data-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Metric({ label, value, tone }: { label: string; value: string | number; tone: string }) { return <div className={`metric ${tone}`}><strong>{value}</strong><span>{label}</span></div>; }
function BarList({ rows, kind, empty }: { rows: MetricRow[]; kind: string; empty: string }) { if (!rows.length) return <p className="empty">{empty}</p>; return <div className="bar-list">{rows.map((row) => { const percent = row.share_percent ?? row.percent ?? 0; const label = kind === "mutual" ? row.name : `${row.code} - ${row.label}`; return <div className="bar-row" key={`${label}-${row.total}`}><div><strong>{label}</strong><span>{row.total} casos</span></div><span className="bar-track"><i style={{ width: `${Math.max(percent, 4)}%` }} /></span><b>{percent}%</b></div>; })}</div>; }
