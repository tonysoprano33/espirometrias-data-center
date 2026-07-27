"use client";

import { useEffect, useState } from "react";

type AgendaRow = {
  encounter_id: number;
  patient_name: string;
  patient_dni_display: string;
  encounter_time: string;
  study_type: string;
  coverage_type: string;
  attendance_label: string;
  attended: boolean;
  no_show: boolean;
  result_code: string;
  medical_control_today: boolean;
  so2_rest: string;
  fc_rest: string;
  so2_post: string;
  fc_post: string;
};

type AgendaPayload = {
  date: string;
  work_mode: string;
  checked_at: string;
  summary: { total: number; attended: number; no_show: number; waiting: number };
  rows: AgendaRow[];
};

const statusClass = (row: AgendaRow) => {
  if (row.attended) return "attended";
  if (row.no_show) return "no-show";
  return "waiting";
};

const formatDate = (date: string) => new Intl.DateTimeFormat("es-AR", {
  weekday: "long",
  day: "2-digit",
  month: "long",
  year: "numeric",
}).format(new Date(`${date}T12:00:00`));

export default function AgendaPreview() {
  const [data, setData] = useState<AgendaPayload | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/v1/agenda/hoy/", { cache: "no-store" });
        if (!response.ok) throw new Error("No se pudo actualizar la agenda.");
        const payload = await response.json() as AgendaPayload;
        if (active) {
          setData(payload);
          setError("");
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Error de conexión.");
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    const interval = window.setInterval(load, 10_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <main className="agenda-shell">
      <header className="agenda-header">
        <div>
          <p className="eyebrow">Clinica Espiro · Vista nueva</p>
          <h1>Pacientes de hoy</h1>
          <p className="subtitle">Actualiza datos sin recargar la página ni mover tu lugar de trabajo.</p>
        </div>
        <span className="mode">Sesión {data?.work_mode ?? "..."}</span>
      </header>

      {error && <p className="notice error">{error}</p>}
      {loading && <p className="notice">Cargando agenda...</p>}

      {data && (
        <>
          <section className="summary" aria-label="Resumen de agenda">
            <Metric label="Pacientes" value={data.summary.total} tone="blue" />
            <Metric label="Atendidos" value={data.summary.attended} tone="green" />
            <Metric label="Esperando" value={data.summary.waiting} tone="amber" />
            <Metric label="No llegaron" value={data.summary.no_show} tone="rose" />
          </section>

          <section className="agenda-card">
            <div className="agenda-card-head">
              <h2>{formatDate(data.date)}</h2>
              <small>Sincronizado {new Date(data.checked_at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}</small>
            </div>
            <div className="agenda-list">
              {data.rows.map((row) => (
                <article className={`patient-row ${statusClass(row)}`} key={row.encounter_id}>
                  <time>{row.encounter_time || "Sin hora"}</time>
                  <div className="patient-main">
                    <strong>{row.patient_name}</strong>
                    <span>DNI {row.patient_dni_display}</span>
                  </div>
                  <div className="tags">
                    <span>{row.study_type}</span>
                    <span>{row.coverage_type}</span>
                    {row.medical_control_today && <span className="control">Control hoy</span>}
                  </div>
                  <div className="vitals">
                    <span>R {row.so2_rest || "-"}/{row.fc_rest || "-"}</span>
                    <span>P {row.so2_post || "-"}/{row.fc_post || "-"}</span>
                  </div>
                  <span className="result">{row.result_code || "Sin resultado"}</span>
                  <span className="attendance">{row.attendance_label}</span>
                </article>
              ))}
              {!data.rows.length && <p className="empty">No hay pacientes cargados para hoy.</p>}
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={`metric ${tone}`}><strong>{value}</strong><span>{label}</span></div>;
}
