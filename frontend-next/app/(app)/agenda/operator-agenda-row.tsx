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
  return value
    .replace(/^\s*(dr|dra)\.?\s*/i, "")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase("es");
}

function physicianDisplayName(value: string) {
  return value.replace(/^\s*(dr|dra)\.?\s*/i, "").trim();
}

async function readResponse(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error ?? fallback);
}

export function OperatorAgendaRow({ entry, physicians: initialPhysicians }: Props) {
  const [isSaving, setIsSaving] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isEditingWalk, setIsEditingWalk] = useState(false);
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
    physicianName: physicianDisplayName(entry.referring_physician_name || ""),
    medicalControlToday: entry.medical_control_today,
  });
  const [rest, setRest] = useState({ so2: entry.so2_rest?.toString() ?? "", fc: entry.fc_rest?.toString() ?? "" });
  const [post, setPost] = useState({ so2: entry.so2_post?.toString() ?? "", fc: entry.fc_post?.toString() ?? "" });
  const [result, setResult] = useState(entry.result_code ?? "");
  const [walk, setWalk] = useState({
    distanceMeters: entry.walk_distance_meters?.toString() ?? "200",
    completed: entry.walk_completed && !entry.walk_stopped,
    stopped: entry.walk_stopped,
    symptoms: entry.walk_symptoms,
    borgFinal: entry.borg_final,
    bronchodilatorPositive: entry.bronchodilator_positive,
  });
  const [isSavingWalk, setIsSavingWalk] = useState(false);
  const [walkSaveState, setWalkSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"ok" | "error">("ok");
  const restReady = Boolean(rest.so2 && rest.fc);
  const postReady = Boolean(post.so2 && post.fc);
  const resultReady = resultCodes.includes(result as (typeof resultCodes)[number]);
  const restMounted = useRef(false);
  const postMounted = useRef(false);
  const resultMounted = useRef(false);
  const walkSnapshot = useRef(JSON.stringify({
    distanceMeters: entry.walk_distance_meters.toString(),
    borgFinal: entry.borg_final,
    completed: entry.walk_completed && !entry.walk_stopped,
    stopped: entry.walk_stopped,
    symptoms: entry.walk_symptoms,
    bronchodilatorPositive: entry.bronchodilator_positive,
  }));
  const walkAbort = useRef<AbortController | null>(null);

  const canPrint = Boolean(
    details.name.trim()
    && digits(details.dni)
    && restReady
    && resultReady
    && (details.studyType === "Espirometria" || postReady),
  );
  const clinicalDataReady = Boolean(restReady && (details.studyType === "Espirometria" || postReady));
  const wasPrinted = entry.workflow_status === "informe_generado" || entry.workflow_status === "entregada";
  const primaryAction = canPrint ? (wasPrinted ? "Reimprimir" : "Imprimir") : clinicalDataReady ? "Revisar" : "Completar";
  const saveLabel = isSaving || isSavingWalk
    ? "Guardando..."
    : messageTone === "error"
      ? "Error al guardar"
      : message
        ? "Guardado"
        : "";

  function formatDni(value: string) {
    const clean = digits(value);
    return clean ? new Intl.NumberFormat("es-AR").format(Number(clean)) : "Sin DNI";
  }

  function oxygenTone(value: string) {
    const numeric = Number(value);
    if (!value) return "empty";
    if (numeric >= 95) return "normal";
    if (numeric >= 90) return "caution";
    return "alert";
  }

  function heartRateTone(value: string) {
    const numeric = Number(value);
    if (!value) return "empty";
    return numeric >= 60 && numeric <= 100 ? "normal" : "caution";
  }

  function walkSummary() {
    if (details.studyType === "Espirometria") return "Sin prueba de caminata";
    const status = walk.stopped ? "Interrumpida" : walk.completed ? "Completa" : "Pendiente";
    return [
      `${walk.distanceMeters || 0} m`,
      `Borg ${walk.borgFinal}`,
      status,
      walk.symptoms ? "Con síntomas" : null,
      walk.bronchodilatorPositive ? "BD+" : null,
    ].filter(Boolean).join(" · ");
  }

  async function retrySave() {
    setIsSaving(true);
    reportMessage("Reintentando guardado...");
    try {
      const tasks: Promise<void>[] = [persistDetails(details, false)];
      if (restReady) tasks.push(persistVitals("rest", rest, false));
      if (details.studyType === "Ciclometria" && postReady) tasks.push(persistVitals("post", post, false));
      if (resultReady) tasks.push(persistResult(result, false));
      await Promise.all(tasks);
      await persistWalk(false);
      reportMessage("Cambios guardados");
    } catch (error) {
      reportMessage(error instanceof Error ? error.message : "No se pudieron guardar los cambios.", "error");
    } finally {
      setIsSaving(false);
    }
  }

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
    setDetails((current) => ({ ...current, physicianId: created.physician_id, physicianName: physicianDisplayName(created.full_name) }));
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

  async function persistWalk(notify = true) {
    walkAbort.current?.abort();
    const controller = new AbortController();
    walkAbort.current = controller;
    setIsSavingWalk(true);
    setWalkSaveState("saving");
    try {
      const physicianId = await resolvePhysician();
      const response = await fetch(`/api/encounters/${entry.encounter_id}/clinical-details`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          fullName: details.name,
          dni: details.dni,
          encounterTime: details.time,
          studyType: details.studyType,
          coverageType: details.coverageType,
          coverageName: details.coverageType === "Mutual" ? details.coverageName || "Mutual" : "",
          referringPhysicianId: physicianId || null,
          medicalControlToday: details.medicalControlToday,
          attendanceStatus: attendance,
          so2Rest: rest.so2 ? Number(rest.so2) : null,
          fcRest: rest.fc ? Number(rest.fc) : null,
          so2Post: details.studyType === "Ciclometria" && post.so2 ? Number(post.so2) : null,
          fcPost: details.studyType === "Ciclometria" && post.fc ? Number(post.fc) : null,
          distanceMeters: details.studyType === "Ciclometria" ? Number(walk.distanceMeters || 0) : 0,
          completed: details.studyType === "Ciclometria" ? walk.completed : true,
          stopped: details.studyType === "Ciclometria" ? walk.stopped : false,
          symptoms: details.studyType === "Ciclometria" ? walk.symptoms : false,
          borgFinal: details.studyType === "Ciclometria" ? walk.borgFinal : 1,
          resultCode: resultReady ? result : "",
          bronchodilatorPositive: walk.bronchodilatorPositive,
        }),
      });
      await readResponse(response, "No se pudo guardar la prueba.");
      setWalkSaveState("saved");
      if (notify) reportMessage("Prueba guardada automaticamente");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setWalkSaveState("error");
      reportMessage(error instanceof Error ? error.message : "No se pudo guardar la prueba.", "error");
    } finally {
      if (walkAbort.current === controller) {
        walkAbort.current = null;
        setIsSavingWalk(false);
      }
    }
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

  useEffect(() => {
    const snapshot = JSON.stringify(walk);
    if (walkSnapshot.current === snapshot) return;
    walkSnapshot.current = snapshot;
    const timer = window.setTimeout(() => {
      void persistWalk(false);
    }, 700);
    return () => window.clearTimeout(timer);
  }, [
    walk.distanceMeters,
    walk.borgFinal,
    walk.completed,
    walk.stopped,
    walk.symptoms,
    walk.bronchodilatorPositive,
  ]);

  useEffect(() => () => walkAbort.current?.abort(), []);

  /* Legacy spreadsheet row retained here only while the clinical card is validated.
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
      <datalist id={`physicians-${entry.encounter_id}`}>{physicians.map((item) => <option key={item.physician_id} value={physicianDisplayName(item.full_name)} />)}</datalist>
    </label>

    <div className="agenda-vitals-comparison">
      <div className="agenda-vital-stage">
        <span>Reposo</span>
        <div className="agenda-vitals">
          <input aria-label="SO2 reposo" inputMode="numeric" value={rest.so2} onChange={(event) => setRest({ ...rest, so2: digits(event.target.value).slice(0, 3) })} placeholder="SO2" />
          <b>/</b>
          <input aria-label="FC reposo" inputMode="numeric" value={rest.fc} onChange={(event) => setRest({ ...rest, fc: digits(event.target.value).slice(0, 3) })} placeholder="FC" />
        </div>
      </div>
      {details.studyType === "Ciclometria"
        ? <div className="agenda-vital-stage">
            <span>Post</span>
            <div className="agenda-vitals">
              <input aria-label="SO2 post" inputMode="numeric" value={post.so2} onChange={(event) => setPost({ ...post, so2: digits(event.target.value).slice(0, 3) })} placeholder="SO2" />
              <b>/</b>
              <input aria-label="FC post" inputMode="numeric" value={post.fc} onChange={(event) => setPost({ ...post, fc: digits(event.target.value).slice(0, 3) })} placeholder="FC" />
            </div>
          </div>
        : <div className="agenda-not-applicable" title="La espirometria sola no usa valores post caminata">Sin post</div>}
    </div>

    <div className={`agenda-test-editor ${walk.completed && !walk.stopped && !walk.symptoms ? "is-complete" : "needs-review"}`}>
      {details.studyType === "Ciclometria" ? (
        <>
          <div className="agenda-test-numbers">
            <label>
              <span>Metros</span>
              <input
                type="number"
                min="0"
                step="50"
                value={walk.distanceMeters}
                onChange={(event) => setWalk({ ...walk, distanceMeters: digits(event.target.value).slice(0, 4) })}
              />
            </label>
            <label>
              <span>Borg</span>
              <select value={walk.borgFinal} onChange={(event) => setWalk({ ...walk, borgFinal: Number(event.target.value) })}>
                {Array.from({ length: 11 }, (_, index) => <option key={index} value={index}>{index}</option>)}
              </select>
            </label>
          </div>
          <div className="agenda-test-checks">
            <label className={walk.completed ? "active" : ""}>
              <input
                type="checkbox"
                checked={walk.completed}
                onChange={(event) => setWalk({ ...walk, completed: event.target.checked, stopped: event.target.checked ? false : walk.stopped })}
              />
              Completa
            </label>
            <label className={walk.stopped ? "active warning" : ""}>
              <input
                type="checkbox"
                checked={walk.stopped}
                onChange={(event) => setWalk({ ...walk, stopped: event.target.checked, completed: event.target.checked ? false : walk.completed })}
              />
              Se detuvo
            </label>
            <label className={walk.symptoms ? "active warning" : ""}>
              <input type="checkbox" checked={walk.symptoms} onChange={(event) => setWalk({ ...walk, symptoms: event.target.checked })} />
              Síntomas
            </label>
          </div>
        </>
      ) : <span className="agenda-test-no-walk">Espirometría sola · sin caminata</span>}
      <div className="agenda-test-footer">
        <label className={`agenda-test-broncho ${walk.bronchodilatorPositive ? "active" : ""}`}>
          <input
            type="checkbox"
            checked={walk.bronchodilatorPositive}
            onChange={(event) => setWalk({ ...walk, bronchodilatorPositive: event.target.checked })}
          />
          BD+
        </label>
        <span className={`agenda-auto-save ${walkSaveState}`} role="status">
          {isSavingWalk ? "Guardando..." : walkSaveState === "error" ? "Error al guardar" : "Guardado automatico"}
        </span>
      </div>
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
      {canPrint
        ? <button type="button" className="print-action" onClick={() => void printEncounter()} disabled={isSaving}>{isSaving ? "Guardando..." : "Imprimir"}</button>
        : <span className="print-action is-disabled" title="Completar DNI y resultado">Imprimir no disponible</span>}
      <div className="agenda-secondary-actions">
        <Link className="edit-action" href={`/atenciones/${entry.encounter_id}/editar`}>Editar</Link>
        <Link href={`/revision-medica/${entry.encounter_id}`}>Revision</Link>
      </div>
      <div className="agenda-delete-action"><DeleteEncounterButton encounterId={entry.encounter_id} /></div>
      {message && <small className={messageTone} role="status">{message}</small>}
    </div>
  </article>;
  */

  return <article className={`agenda-patient-card ${attendance} ${isExpanded ? "is-expanded" : ""}`}>
    <div className="agenda-patient-main">
      <div className="agenda-patient-time">{details.time || "Sin hora"}</div>

      <div className="agenda-patient-identity">
        <strong>{details.name || "Paciente sin nombre"}</strong>
        <span>DNI {formatDni(details.dni)}</span>
      </div>

      <div className="agenda-patient-study">
        <strong>{details.studyType}</strong>
        <span>{details.coverageType === "Mutual" ? details.coverageName || "Mutual" : "Particular"}</span>
      </div>

      <span className={`agenda-result-badge ${resultReady ? "has-result" : "missing"}`}>
        {resultReady ? result : "Sin resultado"}
      </span>

      <span className={`agenda-state-badge ${attendance}`}>
        <i aria-hidden="true" />
        {labels[attendance]}
      </span>

      <div className="agenda-primary-action">
        {primaryAction === "Completar"
          ? <button type="button" onClick={() => setIsExpanded(true)}>Completar</button>
          : primaryAction === "Revisar"
            ? <Link href={`/revision-medica/${entry.encounter_id}`}>Revisar</Link>
            : <button type="button" onClick={() => void printEncounter()} disabled={isSaving}>{primaryAction}</button>}
      </div>

      <button
        type="button"
        className="agenda-expand-button"
        aria-expanded={isExpanded}
        aria-controls={`agenda-details-${entry.encounter_id}`}
        onClick={() => setIsExpanded((current) => !current)}
      >
        {isExpanded ? "Ocultar" : "Detalles"}
        <span aria-hidden="true">{isExpanded ? "▲" : "▼"}</span>
      </button>
    </div>

    <div className="agenda-patient-summary">
      <span><b>Médico</b>{details.physicianName || "Sin asignar"}</span>
      <span className="agenda-summary-vitals">
        <b>Reposo</b>
        <em className={oxygenTone(rest.so2)}>SpO₂ {rest.so2 || "--"}%</em>
        <em className={heartRateTone(rest.fc)}>FC {rest.fc || "--"} lpm</em>
      </span>
      {details.studyType === "Ciclometria" && <span className="agenda-summary-vitals">
        <b>Post</b>
        <em className={oxygenTone(post.so2)}>SpO₂ {post.so2 || "--"}%</em>
        <em className={heartRateTone(post.fc)}>FC {post.fc || "--"} lpm</em>
      </span>}
      <span className="agenda-walk-summary"><b>Prueba</b>{walkSummary()}</span>
      {saveLabel && <span className={`agenda-card-save ${messageTone === "error" || walkSaveState === "error" ? "error" : "ok"}`} role="status">
        {saveLabel === "Guardado" ? "✓ Guardado" : saveLabel}
        {(messageTone === "error" || walkSaveState === "error") && <button type="button" onClick={() => void retrySave()}>Reintentar</button>}
      </span>}
    </div>

    {isExpanded && <div className="agenda-patient-details" id={`agenda-details-${entry.encounter_id}`}>
      <section className="agenda-detail-section agenda-detail-identification">
        <div className="agenda-detail-heading"><h3>Datos del turno</h3><span>Se guardan al salir del campo</span></div>
        <div className="agenda-detail-grid">
          <label><span>Hora</span><input type="time" value={details.time} onChange={(event) => setDetails({ ...details, time: event.target.value })} onBlur={() => void saveDetailsFromField()} /></label>
          <label><span>Paciente</span><input value={details.name} onChange={(event) => setDetails({ ...details, name: event.target.value })} onBlur={() => void saveDetailsFromField()} /></label>
          <label><span>DNI</span><input inputMode="numeric" value={details.dni} onChange={(event) => setDetails({ ...details, dni: digits(event.target.value) })} onBlur={() => void saveDetailsFromField()} placeholder="Completar DNI" /></label>
          <label><span>Estudio</span><select value={details.studyType} onChange={(event) => {
            const next = { ...details, studyType: event.target.value as StudyType };
            setDetails(next);
            void persistDetails(next).catch((error) => reportMessage(error instanceof Error ? error.message : "No se pudo guardar el estudio.", "error"));
          }}><option value="Ciclometria">Ciclometria</option><option value="Espirometria">Espirometria</option></select></label>
          <label><span>Cobertura</span><select value={details.coverageType} onChange={(event) => {
            const coverageType = event.target.value as CoverageType;
            const next = { ...details, coverageType, coverageName: coverageType === "Mutual" ? details.coverageName || "Mutual" : "" };
            setDetails(next);
            void persistDetails(next).catch((error) => reportMessage(error instanceof Error ? error.message : "No se pudo guardar la cobertura.", "error"));
          }}><option value="Particular">Particular</option><option value="Mutual">Mutual</option></select></label>
          <label><span>Médico derivante</span><input list={`physicians-${entry.encounter_id}`} value={details.physicianName} onChange={(event) => setDetails({ ...details, physicianName: event.target.value, physicianId: "" })} onBlur={() => void saveDetailsFromField()} placeholder="Buscar o escribir médico" /><datalist id={`physicians-${entry.encounter_id}`}>{physicians.map((item) => <option key={item.physician_id} value={physicianDisplayName(item.full_name)} />)}</datalist></label>
        </div>
      </section>

      <section className="agenda-detail-section agenda-detail-vitals">
        <div className="agenda-detail-heading"><h3>Signos vitales</h3><span>SpO₂ en % y FC en lpm</span></div>
        <div className="agenda-vitals-editor">
          <fieldset><legend>Reposo</legend><label><span>SpO₂</span><input inputMode="numeric" value={rest.so2} onChange={(event) => setRest({ ...rest, so2: digits(event.target.value).slice(0, 3) })} /></label><label><span>FC</span><input inputMode="numeric" value={rest.fc} onChange={(event) => setRest({ ...rest, fc: digits(event.target.value).slice(0, 3) })} /></label></fieldset>
          {details.studyType === "Ciclometria" && <fieldset><legend>Post caminata</legend><label><span>SpO₂</span><input inputMode="numeric" value={post.so2} onChange={(event) => setPost({ ...post, so2: digits(event.target.value).slice(0, 3) })} /></label><label><span>FC</span><input inputMode="numeric" value={post.fc} onChange={(event) => setPost({ ...post, fc: digits(event.target.value).slice(0, 3) })} /></label></fieldset>}
        </div>
      </section>

      <section className="agenda-detail-section agenda-detail-walk">
        <div className="agenda-detail-heading"><h3>Prueba de caminata</h3>{details.studyType === "Ciclometria" && <button type="button" onClick={() => setIsEditingWalk((current) => !current)}>{isEditingWalk ? "Cerrar edición" : "Editar prueba"}</button>}</div>
        <p className="agenda-walk-readout">{walkSummary()}</p>
        {details.studyType === "Ciclometria" && isEditingWalk && <div className="agenda-walk-controls">
          <label><span>Metros</span><input type="number" min="0" step="50" value={walk.distanceMeters} onChange={(event) => setWalk({ ...walk, distanceMeters: digits(event.target.value).slice(0, 4) })} /></label>
          <label><span>Borg final</span><select value={walk.borgFinal} onChange={(event) => setWalk({ ...walk, borgFinal: Number(event.target.value) })}>{Array.from({ length: 11 }, (_, index) => <option key={index} value={index}>{index}</option>)}</select></label>
          <label className={walk.completed ? "active" : ""}><input type="checkbox" checked={walk.completed} onChange={(event) => setWalk({ ...walk, completed: event.target.checked, stopped: event.target.checked ? false : walk.stopped })} />Completa</label>
          <label className={walk.stopped ? "active warning" : ""}><input type="checkbox" checked={walk.stopped} onChange={(event) => setWalk({ ...walk, stopped: event.target.checked, completed: event.target.checked ? false : walk.completed })} />Se detuvo</label>
          <label className={walk.symptoms ? "active warning" : ""}><input type="checkbox" checked={walk.symptoms} onChange={(event) => setWalk({ ...walk, symptoms: event.target.checked })} />Con síntomas</label>
          <label className={walk.bronchodilatorPositive ? "active" : ""}><input type="checkbox" checked={walk.bronchodilatorPositive} onChange={(event) => setWalk({ ...walk, bronchodilatorPositive: event.target.checked })} />BD+</label>
        </div>}
      </section>

      <section className="agenda-detail-section agenda-detail-result">
        <div className="agenda-detail-heading"><h3>Resultado y asistencia</h3><span>Selección clínica final</span></div>
        <label><span>Resultado</span><input list={`results-${entry.encounter_id}`} value={result} onChange={(event) => setResult(event.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 8))} placeholder="N, OL, RL..." /><datalist id={`results-${entry.encounter_id}`}>{resultCodes.map((code) => <option value={code} key={code} />)}</datalist></label>
        <div className="agenda-attendance-picker" aria-label="Asistencia">
          {(Object.keys(labels) as AttendanceStatus[]).map((status) => <button key={status} type="button" className={attendance === status ? `active ${status}` : ""} onClick={() => setAttendance(status)} disabled={isSaving}>{labels[status]}</button>)}
        </div>
      </section>

      <footer className="agenda-detail-footer">
        {details.medicalControlToday && <span className="agenda-control-today">Control medico hoy</span>}
        <details className="agenda-more-actions">
          <summary>Más acciones</summary>
          <div>
            <Link href={`/atenciones/${entry.encounter_id}/editar`}>Editar ficha completa</Link>
            <Link href={`/revision-medica/${entry.encounter_id}`}>Abrir revisión</Link>
            {canPrint && <button type="button" onClick={() => void printEncounter()}>Imprimir</button>}
            <span className="agenda-delete-action"><DeleteEncounterButton encounterId={entry.encounter_id} /></span>
          </div>
        </details>
      </footer>
    </div>}
  </article>;
}
