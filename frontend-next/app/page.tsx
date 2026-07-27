"use client";

import { FormEvent, useEffect, useState } from "react";

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
  patient_url: string;
  print_url: string;
  can_print_result: boolean;
};

type AgendaPayload = {
  date: string;
  work_mode: string;
  checked_at: string;
  summary: { total: number; attended: number; no_show: number; waiting: number };
  rows: AgendaRow[];
};

type DuplicateCandidate = {
  patient_id: number;
  patient_name: string;
  dni_display: string;
  match_summary: string;
  coverage_hint: string;
  can_use: boolean;
};

type QuickPatient = {
  patient_name: string;
  patient_dni: string;
  encounter_time: string;
  study_type: string;
  coverage_type: string;
  medical_control_today: boolean;
};

const initialQuickPatient: QuickPatient = {
  patient_name: "",
  patient_dni: "",
  encounter_time: "",
  study_type: "Ciclometria",
  coverage_type: "Particular",
  medical_control_today: false,
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

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function postAgenda(path: string, body: object) {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({ ok: false, message: "La respuesta del servidor no es valida." }));
  return { response, payload };
}

export default function AgendaPreview() {
  const [data, setData] = useState<AgendaPayload | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [quickPatient, setQuickPatient] = useState<QuickPatient>(initialQuickPatient);
  const [duplicateCandidates, setDuplicateCandidates] = useState<DuplicateCandidate[]>([]);
  const [savingQuickPatient, setSavingQuickPatient] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/v1/agenda/hoy/", { cache: "no-store", credentials: "same-origin" });
        if (response.status === 401) throw new Error("Inicia sesion para abrir la agenda nueva.");
        if (!response.ok) throw new Error("No se pudo actualizar la agenda.");
        const payload = await response.json() as AgendaPayload;
        if (active) {
          setData(payload);
          setError("");
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Error de conexion.");
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
  }, [refreshVersion]);

  const updateRow = (row: AgendaRow) => {
    setData((current) => current ? {
      ...current,
      rows: current.rows.map((item) => item.encounter_id === row.encounter_id ? row : item),
    } : current);
    setRefreshVersion((version) => version + 1);
  };

  const submitQuickPatient = async (duplicateAction = "", patientId?: number) => {
    if (!quickPatient.patient_name.trim()) {
      setError("Escribi el nombre para agendar al paciente.");
      return;
    }
    setSavingQuickPatient(true);
    setError("");
    try {
      const { response, payload } = await postAgenda("/api/v1/agenda/hoy/nueva/", {
        ...quickPatient,
        duplicate_action: duplicateAction,
        patient_id: patientId,
      });
      if (response.status === 409 && payload.needs_duplicate_choice) {
        setDuplicateCandidates(payload.candidates as DuplicateCandidate[]);
        return;
      }
      if (!response.ok) throw new Error(payload.message || "No se pudo agendar el paciente.");
      setQuickPatient(initialQuickPatient);
      setDuplicateCandidates([]);
      setNotice(payload.message || "Paciente agendado.");
      setRefreshVersion((version) => version + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo agendar el paciente.");
    } finally {
      setSavingQuickPatient(false);
    }
  };

  const saveVitals = async (event: FormEvent<HTMLFormElement>, row: AgendaRow, group: "rest" | "post") => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setError("");
    try {
      const { response, payload } = await postAgenda(`/api/v1/agenda/${row.encounter_id}/signos/`, {
        group,
        so2: values.get("so2"),
        fc: values.get("fc"),
      });
      if (!response.ok) throw new Error(payload.message || "No se pudieron guardar los signos.");
      updateRow(payload as AgendaRow);
      setNotice(payload.message || "Signos vitales guardados.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudieron guardar los signos.");
    }
  };

  const cycleAttendance = async (row: AgendaRow) => {
    setError("");
    try {
      const { response, payload } = await postAgenda(`/api/v1/agenda/${row.encounter_id}/asistencia/`, {});
      if (!response.ok) throw new Error(payload.message || "No se pudo actualizar la asistencia.");
      updateRow(payload as AgendaRow);
      setNotice(payload.message || "Asistencia actualizada.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo actualizar la asistencia.");
    }
  };

  const toggleMedicalControl = async (row: AgendaRow) => {
    setError("");
    try {
      const { response, payload } = await postAgenda(`/api/v1/agenda/${row.encounter_id}/control-medico/`, {});
      if (!response.ok) throw new Error(payload.message || "No se pudo actualizar el control medico.");
      updateRow(payload as AgendaRow);
      setNotice(payload.message || "Control medico actualizado.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo actualizar el control medico.");
    }
  };

  return (
    <main className="agenda-shell">
      <header className="agenda-header">
        <div>
          <p className="eyebrow">Clinica Espiro · Agenda nueva</p>
          <h1>Pacientes de hoy</h1>
          <p className="subtitle">Actualiza datos sin recargar la pagina ni mover tu lugar de trabajo.</p>
        </div>
        <div className="header-actions">
          <span className="mode">Sesion {data?.work_mode ?? "..."}</span>
          <a className="back-link" href="/django/">Agenda actual</a>
        </div>
      </header>

      <section className="quick-panel" aria-labelledby="quick-title">
        <div>
          <p className="eyebrow">Recepcion</p>
          <h2 id="quick-title">Agregar paciente</h2>
        </div>
        <form className="quick-form" onSubmit={(event) => { event.preventDefault(); void submitQuickPatient(); }}>
          <label>Nombre
            <input value={quickPatient.patient_name} onChange={(event) => setQuickPatient({ ...quickPatient, patient_name: event.target.value })} autoComplete="off" />
          </label>
          <label>DNI opcional
            <input value={quickPatient.patient_dni} onChange={(event) => setQuickPatient({ ...quickPatient, patient_dni: event.target.value })} inputMode="numeric" autoComplete="off" />
          </label>
          <label>Hora
            <input type="time" value={quickPatient.encounter_time} onChange={(event) => setQuickPatient({ ...quickPatient, encounter_time: event.target.value })} />
          </label>
          <label>Estudio
            <select value={quickPatient.study_type} onChange={(event) => setQuickPatient({ ...quickPatient, study_type: event.target.value })}>
              <option>Ciclometria</option><option>Espirometria</option>
            </select>
          </label>
          <label>Cobertura
            <select value={quickPatient.coverage_type} onChange={(event) => setQuickPatient({ ...quickPatient, coverage_type: event.target.value })}>
              <option>Particular</option><option>Mutual</option>
            </select>
          </label>
          <label className="check-label"><input type="checkbox" checked={quickPatient.medical_control_today} onChange={(event) => setQuickPatient({ ...quickPatient, medical_control_today: event.target.checked })} /> Control hoy</label>
          <button className="primary-action" disabled={savingQuickPatient}>{savingQuickPatient ? "Agregando..." : "Agregar paciente"}</button>
        </form>
      </section>

      {duplicateCandidates.length > 0 && (
        <section className="duplicate-panel" aria-live="assertive">
          <div><p className="eyebrow">Posible historia existente</p><h2>Confirma antes de agendar</h2></div>
          <p>El DNI es el dato principal. Elegi la historia correcta o crea una nueva solamente si el DNI es distinto.</p>
          <div className="duplicate-actions">
            {duplicateCandidates.map((candidate) => (
              <button key={candidate.patient_id} disabled={!candidate.can_use || savingQuickPatient} onClick={() => void submitQuickPatient("use_existing", candidate.patient_id)}>
                Usar {candidate.patient_name} · {candidate.dni_display}
                <small>{candidate.match_summary}</small>
              </button>
            ))}
            <button className="secondary-action" disabled={savingQuickPatient} onClick={() => void submitQuickPatient("create_new")}>Crear historia nueva</button>
            <button className="text-action" disabled={savingQuickPatient} onClick={() => setDuplicateCandidates([])}>Cancelar</button>
          </div>
        </section>
      )}

      {error && <p className="notice error" role="alert">{error}</p>}
      {notice && <p className="notice success" role="status">{notice}</p>}
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
                  <div className="patient-main"><strong>{row.patient_name}</strong><span>DNI {row.patient_dni_display}</span></div>
                  <div className="tags"><span>{row.study_type}</span><span>{row.coverage_type}</span>{row.medical_control_today && <span className="control">Control hoy</span>}</div>
                  <VitalForm row={row} group="rest" onSave={saveVitals} />
                  <VitalForm row={row} group="post" onSave={saveVitals} />
                  <span className="result">{row.result_code || "Sin resultado"}</span>
                  <div className="attendance-actions"><button onClick={() => void cycleAttendance(row)}>{row.attendance_label}</button><button className="control-toggle" onClick={() => void toggleMedicalControl(row)}>{row.medical_control_today ? "Quitar control" : "Control hoy"}</button></div>
                  <div className="row-actions"><a href={`/django${row.patient_url}`}>Abrir ficha</a>{row.can_print_result && <a className="print-link" href={`/django${row.print_url}`}>Imprimir</a>}</div>
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

function VitalForm({ row, group, onSave }: { row: AgendaRow; group: "rest" | "post"; onSave: (event: FormEvent<HTMLFormElement>, row: AgendaRow, group: "rest" | "post") => Promise<void> }) {
  const isRest = group === "rest";
  return <form className="vitals-form" onSubmit={(event) => void onSave(event, row, group)}>
    <span>{isRest ? "Reposo" : "Post"}</span>
    <div><input name="so2" defaultValue={isRest ? row.so2_rest : row.so2_post} inputMode="numeric" placeholder="SO2" aria-label={`SO2 ${isRest ? "reposo" : "post"}`} /><b>/</b><input name="fc" defaultValue={isRest ? row.fc_rest : row.fc_post} inputMode="numeric" placeholder="FC" aria-label={`FC ${isRest ? "reposo" : "post"}`} /></div>
    <button>Guardar</button>
  </form>;
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={`metric ${tone}`}><strong>{value}</strong><span>{label}</span></div>;
}
