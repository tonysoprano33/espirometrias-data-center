"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

type Props = {
  entry: {
    encounter_id: string;
    encounter_time: string | null;
    patient_name: string;
    dni: string | null;
    study_type: string;
    coverage_type: string;
    coverage_name: string;
    attendance_status: "no_llego" | "esperando" | "atendido";
    medical_control_today: boolean;
    so2_rest?: number | null;
    fc_rest?: number | null;
    so2_post?: number | null;
    fc_post?: number | null;
  };
};

const labels = { no_llego: "No llego", esperando: "Esperando", atendido: "Atendido" };

export function OperatorAgendaRow({ entry }: Props) {
  const router = useRouter();
  const [isSaving, startTransition] = useTransition();
  const [rest, setRest] = useState({ so2: entry.so2_rest?.toString() ?? "", fc: entry.fc_rest?.toString() ?? "" });
  const [post, setPost] = useState({ so2: entry.so2_post?.toString() ?? "", fc: entry.fc_post?.toString() ?? "" });
  const [message, setMessage] = useState("");

  async function save(stage: "rest" | "post") {
    const values = stage === "rest" ? rest : post;
    setMessage("");
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${entry.encounter_id}/vitals`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ stage, so2: values.so2, fc: values.fc }) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) { setMessage(body.error ?? "No se pudo guardar."); return; }
      setMessage(stage === "rest" ? "Reposo guardado" : "Post guardado");
      router.refresh();
    });
  }

  function setAttendance(status: "no_llego" | "esperando" | "atendido") {
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${entry.encounter_id}/attendance`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ status }) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) { setMessage(body.error ?? "No se pudo actualizar la asistencia."); return; }
      router.refresh();
    });
  }

  return <article className={`agenda-work-row ${entry.attendance_status}`}>
    <time><b>{entry.encounter_time?.slice(0, 5) || "--:--"}</b><span>•</span></time>
    <label className="agenda-name"><input defaultValue={entry.patient_name} readOnly /><span className="sr-only">Paciente</span></label>
    <strong className="agenda-dni">{entry.dni || "Sin DNI"}</strong>
    <select aria-label="Estudio" defaultValue={entry.study_type} disabled><option>{entry.study_type}</option></select>
    <select aria-label="Cobertura" defaultValue={entry.coverage_type} disabled><option>{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</option></select>
    <label className="agenda-physician"><input defaultValue="Dr. Gustavo Piguillem" readOnly /><small>Doctor derivante</small></label>
    <div className="agenda-vitals">
      <input aria-label="SO2 reposo" inputMode="numeric" value={rest.so2} onChange={(event) => setRest({ ...rest, so2: event.target.value })} placeholder="SO2" /> <b>/</b>
      <input aria-label="FC reposo" inputMode="numeric" value={rest.fc} onChange={(event) => setRest({ ...rest, fc: event.target.value })} placeholder="FC" />
      <button type="button" onClick={() => save("rest")} disabled={isSaving || !rest.so2 || !rest.fc}>Guardar reposo</button>
    </div>
    <div className="agenda-vitals">
      <input aria-label="SO2 post" inputMode="numeric" value={post.so2} onChange={(event) => setPost({ ...post, so2: event.target.value })} placeholder="SO2" /> <b>/</b>
      <input aria-label="FC post" inputMode="numeric" value={post.fc} onChange={(event) => setPost({ ...post, fc: event.target.value })} placeholder="FC" />
      <button type="button" onClick={() => save("post")} disabled={isSaving || !post.so2 || !post.fc}>Guardar post</button>
    </div>
    <label className="agenda-result"><input placeholder="N, OL, RL, RLOMS..." aria-label="Resultado medico" readOnly /></label>
    <div className="agenda-attendance">
      <button type="button" className={`attendance-control ${entry.attendance_status}`} onClick={() => setAttendance(entry.attendance_status === "no_llego" ? "esperando" : entry.attendance_status === "esperando" ? "atendido" : "no_llego")} disabled={isSaving}>{labels[entry.attendance_status]}</button>
      {entry.medical_control_today && <span>Control hoy</span>}
    </div>
    <span className="agenda-status">{entry.attendance_status === "atendido" ? "Cargada" : "Pendiente"}</span>
    <div className="agenda-actions"><Link href={`/revision-medica/${entry.encounter_id}`}>Revision</Link><Link href={`/api/encounters/${entry.encounter_id}/print`} target="_blank">Imprimir</Link>{message && <small>{message}</small>}</div>
  </article>;
}
