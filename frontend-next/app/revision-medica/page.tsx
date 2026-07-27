"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../lib/api-client";

type ReviewRow = {
  encounter_id: number;
  date_short: string;
  time: string;
  patient_name: string;
  dni: string;
  study_type: string;
  coverage_type: string;
  medical_control_today: boolean;
  review_state: "pending" | "missing_pdf" | "done";
  state_label: string;
  state_help: string;
  file_status: string;
  file_status_key: string;
  action_label: string;
  review_url: string;
};

type ReviewPayload = { date: string; date_label: string; query: string; counters: { pending: number; missing_pdf: number; done: number }; page: number; pages: number; has_previous: boolean; has_next: boolean; rows: ReviewRow[] };

export default function ReviewQueuePage() {
  const [date, setDate] = useState("");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ReviewPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const params = new URLSearchParams({ page: String(page) });
        if (date) params.set("date", date);
        if (submittedQuery) params.set("q", submittedQuery);
        const response = await apiFetch(`/api/v1/revision-medica/?${params.toString()}`, { cache: "no-store" });
        if (!response.ok) throw new Error(response.status === 403 ? "Esta sesion no puede abrir Revision medica." : "No se pudo cargar la cola del medico.");
        const payload = await response.json() as ReviewPayload;
        if (!active) return;
        setData(payload); setError("");
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : "Error de conexion."); }
    };
    void load(); return () => { active = false; };
  }, [date, submittedQuery, page]);

  const submit = (event: FormEvent) => { event.preventDefault(); setPage(1); setSubmittedQuery(query.trim()); };

  return <main className="agenda-shell review-next">
    <header className="agenda-header"><div><p className="eyebrow">Para el medico</p><h1>Revision medica</h1><p className="subtitle">Primero aparecen los estudios atendidos con archivo listo para que el medico marque el resultado.</p></div><div className="header-actions"><nav className="next-nav" aria-label="Navegacion nueva"><a href="/">Agenda</a><a href="/calendario/">Calendario</a><a href="/estadistica/">Estadisticas</a><a href="/pacientes/">Pacientes</a><a className="is-current" href="/revision-medica/">Revision medica</a></nav><a className="back-link" href="/django/revision-medica/">Vista actual</a></div></header>
    <form className="review-filter-next" onSubmit={submit}><label>Fecha<input type="date" value={date} onChange={(event) => { setDate(event.target.value); setPage(1); }} /></label><label>Buscar paciente<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nombre o DNI" /></label><button type="submit">Buscar</button></form>
    {error && <p className="notice error" role="alert">{error}</p>}{!data && !error && <p className="notice">Cargando cola medica...</p>}
    {data && <><section className="review-next-summary"><ReviewMetric label="Falta atender / PDF" value={data.counters.missing_pdf} tone="missing" /><ReviewMetric label="Para revisar" value={data.counters.pending} tone="pending" /><ReviewMetric label="Con resultado" value={data.counters.done} tone="done" /></section><section className="review-next-list"><div className="review-next-list-head"><div><p className="eyebrow">Cola activa</p><h2>{submittedQuery ? `Busqueda: ${submittedQuery}` : data.date_label}</h2></div><span>Pagina {data.page} de {data.pages || 1}</span></div>{data.rows.map((row) => <article key={row.encounter_id} className={`review-next-card ${row.review_state}`}><time><span>{row.date_short}</span><b>{row.time}</b></time><div className="review-next-patient"><div><strong>{row.patient_name}</strong>{row.medical_control_today && <em>Control medico hoy</em>}</div><span>{row.study_type} | {row.coverage_type} | DNI {row.dni}</span><p>{row.state_help}</p></div><div className="review-next-status"><b>{row.state_label}</b><span className={`file-status ${row.file_status_key}`}>{row.file_status}</span></div><a href={`/revision-medica/${row.encounter_id}/`}>{row.action_label}</a></article>)}{!data.rows.length && <p className="empty">No se encontraron pacientes para revisar.</p>}<nav className="patient-pagination-next" aria-label="Paginacion de revision"><button disabled={!data.has_previous} onClick={() => setPage(data.page - 1)}>Anterior</button><span>Pagina {data.page} de {data.pages || 1}</span><button disabled={!data.has_next} onClick={() => setPage(data.page + 1)}>Siguiente</button></nav></section></>}
  </main>;
}

function ReviewMetric({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className={`review-metric ${tone}`}><strong>{value}</strong><span>{label}</span></div>; }
