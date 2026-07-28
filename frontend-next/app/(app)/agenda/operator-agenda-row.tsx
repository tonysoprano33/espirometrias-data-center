"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { DeleteEncounterButton } from "../components/encounter-actions";

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
  const [isSaving, startTransition] = useTransition();
  const [attendance, setAttendanceState] = useState(entry.attendance_status);
  const [rest, setRest] = useState({ so2: entry.so2_rest?.toString() ?? "", fc: entry.fc_rest?.toString() ?? "" });
  const [post, setPost] = useState({ so2: entry.so2_post?.toString() ?? "", fc: entry.fc_post?.toString() ?? "" });
  const [savedStage, setSavedStage] = useState<"rest" | "post" | null>(null);
  const [message, setMessage] = useState("");

  async function save(stage: "rest" | "post") {
    const values = stage === "rest" ? rest : post;
    setMessage("");
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${entry.encounter_id}/vitals`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ stage, so2: values.so2, fc: values.fc }) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) { setMessage(body.error ?? "No se pudo guardar."); return; }
      setSavedStage(stage);
      setMessage(stage === "rest" ? "Reposo guardado" : "Post guardado");
    });
  }

  function setAttendance(status: "no_llego" | "esperando" | "atendido") {
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${entry.encounter_id}/attendance`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ status }) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) { setMessage(body.error ?? "No se pudo actualizar la asistencia."); return; }
      setAttendanceState(status);
    });
  }

  return <article className={`agenda-work-row ${attendance}`}>
    <time><b>{entry.encounter_time?.slice(0, 5) || "--:--"}</b><span>•</span></time>
    <label className="agenda-name"><input defaultValue={entry.patient_name} readOnly /><span className="sr-only">Paciente</span></label>
    <strong className="agenda-dni">{entry.dni || "Sin DNI"}</strong>
    <select aria-label="Estudio" defaultValue={entry.study_type} disabled><option>{entry.study_type}</option></select>
    <select aria-label="Cobertura" defaultValue={entry.coverage_type} disabled><option>{entry.coverage_type === "Mutual" ? entry.coverage_name || "Mutual" : "Particular"}</option></select>
    <label className="agenda-physician"><input defaultValue="Dr. Gustavo Piguillem" readOnly /><small>Doctor derivante</small></label>
    <div className="agenda-vitals">
      <input aria-label="SO2 reposo" inputMode="numeric" value={rest.so2} onChange={(event) => setRest({ ...rest, so2: event.target.value })} placeholder="SO2" /> <b>/</b>
      <input aria-label="FC reposo" inputMode="numeric" value={rest.fc} onChange={(event) => setRest({ ...rest, fc: event.target.value })} placeholder="FC" />
      <button type="button" onClick={() => save("rest")} disabled={isSaving || !rest.so2 || !rest.fc}>{savedStage === "rest" ? "Reposo guardado" : "Guardar reposo"}</button>
    </div>
    <div className="agenda-vitals">
      <input aria-label="SO2 post" inputMode="numeric" value={post.so2} onChange={(event) => setPost({ ...post, so2: event.target.value })} placeholder="SO2" /> <b>/</b>
      <input aria-label="FC post" inputMode="numeric" value={post.fc} onChange={(event) => setPost({ ...post, fc: event.target.value })} placeholder="FC" />
      <button type="button" onClick={() => save("post")} disabled={isSaving || !post.so2 || !post.fc}>{savedStage === "post" ? "Post guardado" : "Guardar post"}</button>
    </div>
    <label className="agenda-result"><input placeholder="N, OL, RL, RLOMS..." aria-label="Resultado medico" readOnly /></label>
    <div className="agenda-attendance">
      <button type="button" className={`attendance-control ${attendance}`} onClick={() => setAttendance(attendance === "no_llego" ? "esperando" : attendance === "esperando" ? "atendido" : "no_llego")} disabled={isSaving}>{labels[attendance]}</button>
      {entry.medical_control_today && <span>Control hoy</span>}
    </div>
    <span className={`agenda-status ${attendance}`}>{attendance === "atendido" ? "Atendido" : "Pendiente"}</span>
    <div className="agenda-actions"><Link className="print-action" href={`/api/encounters/${entry.encounter_id}/print`} target="_blank">Imprimir</Link><Link href={`/revision-medica/${entry.encounter_id}`}>Revision</Link><DeleteEncounterButton encounterId={entry.encounter_id} />{message && <small role="status">{message}</small>}</div>
  </article>;
}
