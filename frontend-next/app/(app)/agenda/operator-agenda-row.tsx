"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
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

async function readResponse(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error ?? fallback);
}

export function OperatorAgendaRow({ entry, physicians: initialPhysicians }: Props) {
  const [isSaving, setIsSaving] = useState(false);
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
  const restReady = Boolean(rest.so2 && rest.fc);
  const postReady = Boolean(post.so2 && post.fc);
  const resultReady = resultCodes.includes(result as (typeof resultCodes)[number]);
  const restMounted = useRef(false);
  const postMounted = useRef(false);
  const resultMounted = useRef(false);

  const canPrint = Boolean(
    details.name.trim()
    && digits(details.dni)
    && resultReady,
  );

  function reportMessage(text: string, tone: "ok" | "error" = "ok") {
    setMessage(text);
    setMessageTone(tone);
  }

  async function persistVitals(stage: "rest" | "post", values: { so2: string; fc: string }, notify = true) {
    const response = await fetch(`/api/encounters/${entry.encounter_id}/vitals`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ stage, so2: values.so2, fc: values.fc }),
    });
    await readResponse(response, "No se pudieron guardar los signos vitales.");
    if (stage === "rest") setAttendanceState("atendido");
    if (notify) reportMessage(stage === "rest" ? "Reposo guardado automaticamente" : "Post guardado automaticamente");
  }

  function setAttendance(status: AttendanceStatus) {
    setIsSaving(true);
    void (async () => {
      const response = await fetch(`/api/encounters/${entry.encounter_id}/attendance`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ status }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        reportMessage(body.error ?? "No se pudo actualizar la asistencia.", "error");
        setIsSaving(false);
        return;
      }
      setAttendanceState(status);
      reportMessage(`Asistencia: ${labels[status]}`);
      setIsSaving(false);
    })();
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

  async function persistDetails(current = details, notify = true) {
    const physicianId = await resolvePhysician();
    const response = await fetch(`/api/encounters/${entry.encounter_id}/manage`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        action: "update",
        fullName: current.name,
        dni: current.dni,
        encounterTime: current.time,
        studyType: current.studyType,
        coverageType: current.coverageType,
        coverageName: current.coverageType === "Mutual" ? current.coverageName || "Mutual" : "",
        referringPhysicianId: physicianId || null,
        medicalControlToday: current.medicalControlToday,
      }),
    });
    await readResponse(response, "No se pudieron guardar los datos.");
    if (notify) reportMessage("Datos guardados automaticamente");
  }

  async function persistResult(code = result, notify = true) {
    const response = await fetch(`/api/encounters/${entry.encounter_id}/medical-result`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code, comment: "" }),
    });
    await readResponse(response, "No se pudo guardar el resultado.");
    if (notify) reportMessage("Resultado guardado automaticamente");
  }

  async function saveDetailsFromField() {
    if (!details.name.trim()) return;
    try {
      await persistDetails();
    } catch (error) {
      reportMessage(error instanceof Error ? error.message : "No se pudieron guardar los datos.", "error");
    }
  }

  async function printEncounter() {
    if (!canPrint || isSaving) return;
    const printWindow = window.open("", "_blank");
    setIsSaving(true);
    reportMessage("Preparando impresion...");
    try {
      const tasks: Promise<void>[] = [
        persistDetails(details, false),
        persistResult(result, false),
      ];
      if (restReady) tasks.push(persistVitals("rest", rest, false));
      if (postReady) tasks.push(persistVitals("post", post, false));
      await Promise.all(tasks);
      reportMessage("Datos guardados. Abriendo impresion.");
      if (printWindow) printWindow.location.href = `/imprimir/${entry.encounter_id}`;
      else window.location.href = `/imprimir/${entry.encounter_id}`;
    } catch (error) {
      printWindow?.close();
      reportMessage(error instanceof Error ? error.message : "No se pudo preparar la impresion.", "error");
    } finally {
      setIsSaving(false);
    }
  }

  useEffect(() => {
    if (!restMounted.current) {
      restMounted.current = true;
      return;
    }
    if (!restReady) return;
    const timer = window.setTimeout(() => {
      void persistVitals("rest", rest).catch((error) => {
        reportMessage(error instanceof Error ? error.message : "No se pudo guardar reposo.", "error");
      });
    }, 650);
    return () => window.clearTimeout(timer);
  }, [rest.fc, rest.so2, restReady]);

  useEffect(() => {
    if (!postMounted.current) {
      postMounted.current = true;
      return;
    }
    if (!postReady) return;
    const timer = window.setTimeout(() => {
      void persistVitals("post", post).catch((error) => {
        reportMessage(error instanceof Error ? error.message : "No se pudo guardar post.", "error");
      });
    }, 650);
    return () => window.clearTimeout(timer);
  }, [post.fc, post.so2, postReady]);

  useEffect(() => {
    if (!resultMounted.current) {
      resultMounted.current = true;
      return;
    }
    if (!resultReady) return;
    const timer = window.setTimeout(() => {
      void persistResult(result).catch((error) => {
        reportMessage(error instanceof Error ? error.message : "No se pudo guardar el resultado.", "error");
      });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [result, resultReady]);

  return <article className={`agenda-work-row ${attendance} ${canPrint ? "is-printable" : "is-incomplete"}`}>
    <label className="agenda-time-editor">
      <span className="sr-only">Hora</span>
      <input type="time" value={details.time} onChange={(event) => setDetails({ ...details, time: event.target.value })} onBlur={() => void saveDetailsFromField()} />
    </label>

    <label className="agenda-name">
      <span className="sr-only">Paciente</span>
      <input value={details.name} onChange={(event) => setDetails({ ...details, name: event.target.value })} onBlur={() => void saveDetailsFromField()} />
    </label>

    <label className="agenda-dni-editor">
      <span className="sr-only">DNI</span>
      <input inputMode="numeric" value={details.dni} onChange={(event) => setDetails({ ...details, dni: digits(event.target.value) })} onBlur={() => void saveDetailsFromField()} placeholder="Completar DNI" />
    </label>

    <select aria-label="Estudio" value={details.studyType} onChange={(event) => {
      const next = { ...details, studyType: event.target.value as StudyType };
      setDetails(next);
      void persistDetails(next).catch((error) => reportMessage(error instanceof Error ? error.message : "No se pudo guardar el estudio.", "error"));
    }}>
      <option value="Ciclometria">Ciclometria</option>
      <option value="Espirometria">Espirometria</option>
    </select>

    <div className="agenda-coverage-editor">
      <select aria-label="Cobertura" value={details.coverageType} onChange={(event) => {
        const coverageType = event.target.value as CoverageType;
        const next = { ...details, coverageType, coverageName: coverageType === "Mutual" ? details.coverageName || "Mutual" : "" };
        setDetails(next);
        void persistDetails(next).catch((error) => reportMessage(error instanceof Error ? error.message : "No se pudo guardar la cobertura.", "error"));
      }}>
        <option value="Particular">Particular</option>
        <option value="Mutual">Mutual</option>
      </select>
    </div>

    <label className="agenda-physician">
      <input
        list={`physicians-${entry.encounter_id}`}
        value={details.physicianName}
        onChange={(event) => setDetails({ ...details, physicianName: event.target.value, physicianId: "" })}
        onBlur={() => void saveDetailsFromField()}
        placeholder="Buscar o escribir medico"
      />
      <datalist id={`physicians-${entry.encounter_id}`}>{physicians.map((item) => <option key={item.physician_id} value={item.full_name} />)}</datalist>
      <small>Elegilo de la lista o escribi uno nuevo</small>
    </label>

    <div className="agenda-vitals">
      <input aria-label="SO2 reposo" inputMode="numeric" value={rest.so2} onChange={(event) => setRest({ ...rest, so2: digits(event.target.value).slice(0, 3) })} placeholder="SO2" />
      <b>/</b>
      <input aria-label="FC reposo" inputMode="numeric" value={rest.fc} onChange={(event) => setRest({ ...rest, fc: digits(event.target.value).slice(0, 3) })} placeholder="FC" />
    </div>

    <div className="agenda-vitals">
      <input aria-label="SO2 post" inputMode="numeric" value={post.so2} onChange={(event) => setPost({ ...post, so2: digits(event.target.value).slice(0, 3) })} placeholder="SO2" />
      <b>/</b>
      <input aria-label="FC post" inputMode="numeric" value={post.fc} onChange={(event) => setPost({ ...post, fc: digits(event.target.value).slice(0, 3) })} placeholder="FC" />
    </div>

    <div className="agenda-result">
      <input list={`results-${entry.encounter_id}`} value={result} onChange={(event) => setResult(event.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 8))} placeholder="N, OL, RL..." aria-label="Resultado medico" />
      <datalist id={`results-${entry.encounter_id}`}>{resultCodes.map((code) => <option value={code} key={code} />)}</datalist>
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
      <Link className="edit-action" href={`/atenciones/${entry.encounter_id}/editar`}>Editar</Link>
      {canPrint
        ? <button type="button" className="print-action" onClick={() => void printEncounter()} disabled={isSaving}>{isSaving ? "Guardando..." : "Imprimir"}</button>
        : <span className="print-action is-disabled" title="Completar DNI y resultado">Imprimir no disponible</span>}
      <Link href={`/revision-medica/${entry.encounter_id}`}>Revision</Link>
      <DeleteEncounterButton encounterId={entry.encounter_id} />
      {message && <small className={messageTone} role="status">{message}</small>}
    </div>
  </article>;
}
