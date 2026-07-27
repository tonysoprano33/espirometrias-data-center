"use client";

import { useEffect, useState } from "react";

type DeletedPatient = { patient_id: number; name: string; dni: string; deleted_at: string; days_remaining: number; encounter_count: number };
type DeletedEncounter = { encounter_id: number; patient_name: string; patient_id: number; date: string; study_type: string; deleted_at: string; days_remaining: number; patient_deleted: boolean };
type TrashPayload = { retention_days: number; can_purge: boolean; patients: DeletedPatient[]; encounters: DeletedEncounter[]; message?: string };

function csrfToken() {
  return document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] || "";
}

export default function RecycleBinPage() {
  const [data, setData] = useState<TrashPayload | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = async () => {
    const response = await fetch("/api/v1/papelera/", { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error("No se pudo abrir la papelera.");
    setData(await response.json() as TrashPayload);
  };

  useEffect(() => { void load().catch((cause) => setError(cause instanceof Error ? cause.message : "Error de conexion.")); }, []);

  const runAction = async (action: string, id: number, label: string) => {
    const irreversible = action.startsWith("purge");
    if (irreversible && !window.confirm(`Eliminar definitivamente ${label}? Esta accion no se puede deshacer.`)) return;
    setBusy(`${action}-${id}`); setError("");
    try {
      const response = await fetch("/api/v1/papelera/accion/", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": decodeURIComponent(csrfToken()) },
        body: JSON.stringify({ action, id }),
      });
      const payload = await response.json() as TrashPayload & { message?: string };
      if (!response.ok) throw new Error(payload.message || "No se pudo actualizar la papelera.");
      setData(payload);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "No se pudo actualizar la papelera."); }
    finally { setBusy(""); }
  };

  return <main className="agenda-shell trash-next">
    <header className="agenda-header"><div><p className="eyebrow">Seguridad de datos</p><h1>Papelera clinica</h1><p className="subtitle">Los registros se conservan {data?.retention_days ?? 30} dias antes de poder purgarse definitivamente.</p></div><div className="header-actions"><nav className="next-nav"><a href="/">Agenda</a><a href="/calendario/">Calendario</a><a href="/estadistica/">Estadisticas</a><a href="/pacientes/">Pacientes</a><a className="is-current" href="/papelera/">Papelera</a><a href="/revision-medica/">Revision medica</a></nav><a className="back-link" href="/django/papelera/">Vista actual</a></div></header>
    {error && <p className="notice error" role="alert">{error}</p>}
    {!data && !error && <p className="notice">Cargando papelera...</p>}
    {data && <><section className="summary trash-summary"><Metric label="Pacientes recuperables" value={data.patients.length} tone="blue" /><Metric label="Atenciones recuperables" value={data.encounters.length} tone="amber" /><Metric label="Borrado definitivo" value={data.can_purge ? "Habilitado" : "Restringido"} tone={data.can_purge ? "rose" : "green"} /></section>
      <TrashSection title="Historias eliminadas" empty="No hay pacientes eliminados." rows={data.patients.map((item) => <article className="trash-row" key={`patient-${item.patient_id}`}><div><strong>{item.name}</strong><span>DNI {item.dni} · {item.encounter_count} atencion{item.encounter_count === 1 ? "" : "es"}</span></div><span>Eliminado {item.deleted_at}<small>Quedan {item.days_remaining} dias</small></span><div className="trash-actions"><button disabled={busy === `restore_patient-${item.patient_id}`} onClick={() => void runAction("restore_patient", item.patient_id, item.name)}>Restaurar historia</button>{data.can_purge && <button className="danger" disabled={busy === `purge_patient-${item.patient_id}`} onClick={() => void runAction("purge_patient", item.patient_id, item.name)}>Eliminar definitivo</button>}</div></article>)} />
      <TrashSection title="Atenciones eliminadas" empty="No hay atenciones eliminadas." rows={data.encounters.map((item) => <article className="trash-row" key={`encounter-${item.encounter_id}`}><div><strong>{item.patient_name}</strong><span>{item.date} · {item.study_type}{item.patient_deleted ? " · La historia tambien esta en papelera" : ""}</span></div><span>Eliminado {item.deleted_at}<small>Quedan {item.days_remaining} dias</small></span><div className="trash-actions"><button disabled={busy === `restore_encounter-${item.encounter_id}`} onClick={() => void runAction("restore_encounter", item.encounter_id, `la atencion de ${item.patient_name}`)}>Restaurar atencion</button>{data.can_purge && <button className="danger" disabled={busy === `purge_encounter-${item.encounter_id}`} onClick={() => void runAction("purge_encounter", item.encounter_id, item.patient_name)}>Eliminar definitivo</button>}</div></article>)} />
    </>}
  </main>;
}

function TrashSection({ title, empty, rows }: { title: string; empty: string; rows: React.ReactNode[] }) {
  return <section className="trash-panel"><h2>{title}</h2>{rows.length ? <div>{rows}</div> : <p className="empty">{empty}</p>}</section>;
}

function Metric({ label, value, tone }: { label: string; value: number | string; tone: string }) {
  return <div className={`metric ${tone}`}><strong>{value}</strong><span>{label}</span></div>;
}
