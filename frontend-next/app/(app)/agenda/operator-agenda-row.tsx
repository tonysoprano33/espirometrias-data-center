"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { DeleteEncounterButton } from "../components/encounter-actions";
import type { AgendaEntry, AttendanceStatus, CoverageType, PhysicianOption, StudyType } from "./agenda-types";
import { resultCodes } from "./agenda-types";

type Props = {
  entry: AgendaEntry;
  physicians: PhysicianOption[];
};

const labels: Record<AttendanceStatus, string> = {
  no_llego: "No llego",
  esperando: "Esperando",
  atendido: "Atendido",
};

function digits(value: string) {
  return value.replace(/\D/g, "");
}

function normalizeName(value: string) {
  return value.trim().replace(/\s+/g, " ").toLocaleLowerCase("es");
}

export function OperatorAgendaRow({ entry, physicians: initialPhysicians }: Props) {
  const [isSaving, startTransition] = useTransition();
  const [attendance, setAttendanceState] = useState(entry.attendance_status);
  const [physicians, setPhysicians] = useState(initialPhysicians);
  const [details, setDetails] = useState({
    time: entry.encounter_time?.slice(0, 5) ?? "",
    name: entry.patient_name,
    dni: entry.dni ?? "",
    studyType: entry.study_type as StudyType,
    coverageType: entry.coverage_type as CoverageType,
    coverageName: entry.coverage_name,
    physicianId: entry.referring_physician_id ?? "",
    physicianName: entry.referring_physician_name || "",
    medicalControlToday: entry.medical_control_today,
  });
  const [rest, setRest] = useState({ so2: entry.so2_rest?.toString() ?? "", fc: entry.fc_rest?.toString() ?? "" });
  const [post, setPost] = useState({ so2: entry.so2_post?.toString() ?? "", fc: entry.fc_post?.toString() ?? "" });
  const [result, setResult] = useState(entry.result_code ?? "");
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"ok" | "error">("ok");

  const canPrint = Boolean(
    details.name.trim()
    && digits(details.dni)
    && result.trim(),
  );

  function reportMessage(text: string, tone: "ok" | "error" = "ok") {
    setMessage(text);
    setMessageTone(tone);
  }

  async function saveVitals(stage: "rest" | "post") {
    const values = stage === "rest" ? rest : post;
    reportMessage("");
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${entry.encounter_id}/vitals`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ stage, so2: values.so2, fc: values.fc }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        reportMessage(body.error ?? "No se pudo guardar.", "error");
        return;
      }
      if (stage === "rest") setAttendanceState("atendido");
      reportMessage(stage === "rest" ? "Reposo guardado" : "Post guardado");
    });
  }

  function setAttendance(status: AttendanceStatus) {
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${entry.encounter_id}/attendance`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ status }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        reportMessage(body.error ?? "No se pudo actualizar la asistencia.", "error");
        return;
      }
      setAttendanceState(status);
      reportMessage(`Asistencia: ${labels[status]}`);
    });
  }

  async function resolvePhysician() {
    const typedName = details.physicianName.trim();
    if (!typedName) return "";
    const existing = physicians.find((item) => normalizeName(item.full_name) === normalizeName(typedName));
    if (existing) return existing.physician_id;

    const response = await fetch("/api/physicians", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ fullName: typedName }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error ?? "No se pudo agregar el medico.");
    const created = body.physician as PhysicianOption;
    setPhysicians((current) => [...current, created].sort((a, b) => a.full_name.localeCompare(b.full_name)));
    setDetails((current) => ({ ...current, physicianId: created.physician_id, physicianName: created.full_name }));
    return created.physician_id;
  }

  function saveDetails() {
    reportMessage("");
    startTransition(async () => {
      try {
        const physicianId = await resolvePhysician();
        const response = await fetch(`/api/encounters/${entry.encounter_id}/manage`, {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            action: "update",
            fullName: details.name,
            dni: details.dni,
            encounterTime: details.time,
            studyType: details.studyType,
            coverageType: details.coverageType,
            coverageName: details.coverageType === "Mutual" ? details.coverageName || "Mutual" : "",
            referringPhysicianId: physicianId || null,
            medicalControlToday: details.medicalControlToday,
          }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error ?? "No se pudieron guardar los datos.");
        reportMessage("Datos del paciente guardados");
      } catch (error) {
        reportMessage(error instanceof Error ? error.message : "No se pudieron guardar los datos.", "error");
      }
    });
  }

  function saveResult() {
    reportMessage("");
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${entry.encounter_id}/medical-result`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ code: result, comment: "" }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        reportMessage(body.error ?? "No se pudo guardar el resultado.", "error");
        return;
      }
      reportMessage("Resultado guardado");
    });
  }

  return <article className={`agenda-work-row ${attendance} ${canPrint ? "is-printable" : "is-incomplete"}`}>
    <label className="agenda-time-editor">
      <span className="sr-only">Hora</span>
      <input type="time" value={details.time} onChange={(event) => setDetails({ ...details, time: event.target.value })} />
    </label>

    <label className="agenda-name">
      <span className="sr-only">Paciente</span>
      <input value={details.name} onChange={(event) => setDetails({ ...details, name: event.target.value })} />
    </label>

    <label className="agenda-dni-editor">
      <span className="sr-only">DNI</span>
      <input inputMode="numeric" value={details.dni} onChange={(event) => setDetails({ ...details, dni: digits(event.target.value) })} placeholder="Completar DNI" />
    </label>

    <select aria-label="Estudio" value={details.studyType} onChange={(event) => setDetails({ ...details, studyType: event.target.value as StudyType })}>
      <option value="Ciclometria">Ciclometria</option>
      <option value="Espirometria">Espirometria</option>
    </select>

    <div className="agenda-coverage-editor">
      <select aria-label="Cobertura" value={details.coverageType} onChange={(event) => setDetails({ ...details, coverageType: event.target.value as CoverageType })}>
        <option value="Particular">Particular</option>
        <option value="Mutual">Mutual</option>
      </select>
      {details.coverageType === "Mutual" && <input value={details.coverageName} onChange={(event) => setDetails({ ...details, coverageName: event.target.value })} placeholder="Nombre de mutual" />}
    </div>

    <label className="agenda-physician">
      <input
        list={`physicians-${entry.encounter_id}`}
        value={details.physicianName}
        onChange={(event) => setDetails({ ...details, physicianName: event.target.value, physicianId: "" })}
        placeholder="Buscar o escribir medico"
      />
      <datalist id={`physicians-${entry.encounter_id}`}>{physicians.map((item) => <option key={item.physician_id} value={item.full_name} />)}</datalist>
      <small>Elegilo de la lista o escribi uno nuevo</small>
    </label>

    <div className="agenda-vitals">
      <input aria-label="SO2 reposo" inputMode="numeric" value={rest.so2} onChange={(event) => setRest({ ...rest, so2: digits(event.target.value).slice(0, 3) })} placeholder="SO2" />
      <b>/</b>
      <input aria-label="FC reposo" inputMode="numeric" value={rest.fc} onChange={(event) => setRest({ ...rest, fc: digits(event.target.value).slice(0, 3) })} placeholder="FC" />
      <button type="button" onClick={() => saveVitals("rest")} disabled={isSaving || !rest.so2 || !rest.fc}>Guardar reposo</button>
    </div>

    <div className="agenda-vitals">
      <input aria-label="SO2 post" inputMode="numeric" value={post.so2} onChange={(event) => setPost({ ...post, so2: digits(event.target.value).slice(0, 3) })} placeholder="SO2" />
      <b>/</b>
      <input aria-label="FC post" inputMode="numeric" value={post.fc} onChange={(event) => setPost({ ...post, fc: digits(event.target.value).slice(0, 3) })} placeholder="FC" />
      <button type="button" onClick={() => saveVitals("post")} disabled={isSaving || !post.so2 || !post.fc}>Guardar post</button>
    </div>

    <div className="agenda-result">
      <input list={`results-${entry.encounter_id}`} value={result} onChange={(event) => setResult(event.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 8))} placeholder="N, OL, RL..." aria-label="Resultado medico" />
      <datalist id={`results-${entry.encounter_id}`}>{resultCodes.map((code) => <option value={code} key={code} />)}</datalist>
      <button type="button" onClick={saveResult} disabled={isSaving || !result}>Guardar resultado</button>
    </div>

    <div className="agenda-attendance">
      <button
        type="button"
        className={`attendance-control ${attendance}`}
        onClick={() => setAttendance(attendance === "no_llego" ? "esperando" : attendance === "esperando" ? "atendido" : "no_llego")}
        disabled={isSaving}
      >
        {labels[attendance]}
      </button>
      {details.medicalControlToday && <span>Control hoy</span>}
    </div>

    <div className="agenda-actions">
      {canPrint
        ? <Link className="print-action" href={`/imprimir/${entry.encounter_id}`} target="_blank">Imprimir</Link>
        : <span className="print-action is-disabled" title={`Completar: ${entry.missing_for_print || "datos clinicos"}`}>Imprimir no disponible</span>}
      <button type="button" className="save-row-action" onClick={saveDetails} disabled={isSaving}>Guardar datos</button>
      <Link href={`/revision-medica/${entry.encounter_id}`}>Revision</Link>
      <DeleteEncounterButton encounterId={entry.encounter_id} />
      {message && <small className={messageTone} role="status">{message}</small>}
    </div>
  </article>;
}
