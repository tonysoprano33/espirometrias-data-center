"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { resultCodes } from "../../../agenda/agenda-types";

type Physician = { id: string; fullName: string };
type StudyType = "Ciclometria" | "Espirometria";
type CoverageType = "Particular" | "Mutual";
type AttendanceStatus = "no_llego" | "esperando" | "atendido";

export type EncounterEditValues = {
  fullName: string;
  dni: string;
  encounterTime: string;
  studyType: StudyType;
  coverageType: CoverageType;
  coverageName: string;
  referringPhysicianName: string;
  medicalControlToday: boolean;
  attendanceStatus: AttendanceStatus;
  so2Rest: number | null;
  fcRest: number | null;
  so2Post: number | null;
  fcPost: number | null;
  distanceMeters: number;
  completed: boolean;
  stopped: boolean;
  symptoms: boolean;
  borgFinal: number;
  resultCode: string;
  bronchodilatorPositive: boolean;
};

function nullableNumber(value: string) {
  return value === "" ? null : Number(value);
}

export function EncounterEditForm({
  encounterId,
  initialValues,
  physicians: initialPhysicians,
}: {
  encounterId: string;
  initialValues: EncounterEditValues;
  physicians: Physician[];
}) {
  const router = useRouter();
  const [values, setValues] = useState(initialValues);
  const [physicians, setPhysicians] = useState(initialPhysicians);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  function update<K extends keyof EncounterEditValues>(key: K, value: EncounterEditValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function resolvePhysicianId() {
    const typed = values.referringPhysicianName.trim();
    if (!typed) return null;
    const existing = physicians.find(
      (physician) => physician.fullName.toLocaleLowerCase("es") === typed.toLocaleLowerCase("es"),
    );
    if (existing) return existing.id;

    const response = await fetch("/api/physicians", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fullName: typed }),
    });
    const payload = (await response.json()) as {
      physician?: { physician_id: string; full_name: string };
      error?: string;
    };
    if (!response.ok || !payload.physician) {
      throw new Error(payload.error ?? "No se pudo agregar el medico derivante.");
    }
    const created = {
      id: payload.physician.physician_id,
      fullName: payload.physician.full_name,
    };
    setPhysicians((current) => [...current, created]);
    update("referringPhysicianName", created.fullName);
    return created.id;
  }

  function save(nextPath?: string) {
    setError("");
    setMessage("");
    startTransition(async () => {
      try {
        const referringPhysicianId = await resolvePhysicianId();
        const response = await fetch(`/api/encounters/${encounterId}/clinical-details`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...values,
            referringPhysicianId,
            resultCode: values.resultCode.trim().toUpperCase(),
          }),
        });
        const payload = (await response.json()) as { error?: string };
        if (!response.ok) throw new Error(payload.error ?? "No se pudo guardar la atencion.");

        setMessage("Cambios guardados correctamente.");
        router.refresh();
        if (nextPath) router.push(nextPath);
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : "No se pudo guardar.");
      }
    });
  }

  return (
    <main className="clinical-edit-shell">
      <header className="clinical-edit-heading">
        <div>
          <span className="eyebrow">Paciente</span>
          <h1>Editar atención</h1>
          <p>Estos son los datos que usa la revisión médica y el informe final.</p>
        </div>
        <Link className="button button-secondary" href="/agenda">Volver a Inicio</Link>
      </header>

      {message ? <p className="form-alert form-alert-success">{message}</p> : null}
      {error ? <p className="form-alert form-alert-error">{error}</p> : null}

      <section className="clinical-edit-card clinical-edit-card-wide">
        <div className="clinical-edit-card-title">
          <span className="eyebrow">Identificación</span>
          <h2>Paciente y turno</h2>
        </div>
        <div className="clinical-edit-grid clinical-edit-grid-identification">
          <label>Nombre
            <input value={values.fullName} onChange={(event) => update("fullName", event.target.value)} />
          </label>
          <label>DNI
            <input inputMode="numeric" value={values.dni} onChange={(event) => update("dni", event.target.value.replace(/\D/g, ""))} />
          </label>
          <label>Hora
            <input type="time" value={values.encounterTime} onChange={(event) => update("encounterTime", event.target.value)} />
          </label>
          <label>Dr. deriva
            <input
              list="clinical-edit-physicians"
              value={values.referringPhysicianName}
              onChange={(event) => update("referringPhysicianName", event.target.value)}
              placeholder="Escribí y elegí un doctor"
            />
            <datalist id="clinical-edit-physicians">
              {physicians.map((physician) => <option key={physician.id} value={physician.fullName} />)}
            </datalist>
            <small>Si no existe, se agrega al guardar.</small>
          </label>
        </div>
      </section>

      <div className="clinical-edit-columns">
        <section className="clinical-edit-card">
          <div className="clinical-edit-card-title">
            <span className="eyebrow">Estudio</span>
            <h2>Tipo de atención</h2>
          </div>
          <div className="clinical-edit-grid clinical-edit-grid-three">
            <label>Tipo de estudio
              <select value={values.studyType} onChange={(event) => update("studyType", event.target.value as StudyType)}>
                <option value="Ciclometria">Ciclometría</option>
                <option value="Espirometria">Espirometría</option>
              </select>
            </label>
            <label>Cobertura
              <select value={values.coverageType} onChange={(event) => update("coverageType", event.target.value as CoverageType)}>
                <option value="Particular">Particular</option>
                <option value="Mutual">Mutual</option>
              </select>
            </label>
            {values.coverageType === "Mutual" ? (
              <label>Mutual
                <input value={values.coverageName} onChange={(event) => update("coverageName", event.target.value)} placeholder="DOSEP, PAMI, Grassi..." />
              </label>
            ) : null}
            <label>Resultado
              <select value={values.resultCode} onChange={(event) => update("resultCode", event.target.value)}>
                <option value="">Sin resultado</option>
                {resultCodes.map((code) => <option key={code} value={code}>{code}</option>)}
              </select>
            </label>
          </div>
        </section>

        <section className="clinical-edit-card">
          <div className="clinical-edit-card-title">
            <span className="eyebrow">Informe</span>
            <h2>Estado clínico</h2>
          </div>
          <div className="clinical-choice-stack">
            <label className="clinical-choice clinical-choice-broncho">
              <input type="checkbox" checked={values.bronchodilatorPositive} onChange={(event) => update("bronchodilatorPositive", event.target.checked)} />
              <span><strong>Broncodilatador positivo</strong><small>Aparece en la primera página del informe.</small></span>
            </label>
            <label className="clinical-choice">
              <input type="checkbox" checked={values.medicalControlToday} onChange={(event) => update("medicalControlToday", event.target.checked)} />
              <span><strong>Control médico hoy</strong><small>El médico lo verá destacado en la revisión.</small></span>
            </label>
            <fieldset className="clinical-status-picker">
              <legend>Asistencia</legend>
              {([
                ["no_llego", "No llegó"],
                ["esperando", "Esperando"],
                ["atendido", "Atendido"],
              ] as const).map(([value, label]) => (
                <label key={value}>
                  <input type="radio" name="attendance" checked={values.attendanceStatus === value} onChange={() => update("attendanceStatus", value)} />
                  {label}
                </label>
              ))}
            </fieldset>
          </div>
        </section>

        <section className="clinical-edit-card">
          <div className="clinical-edit-card-title">
            <span className="eyebrow">Oxigenación</span>
            <h2>Valores y caminata</h2>
          </div>
          <div className="clinical-vitals-grid">
            <label>SO2 en reposo
              <input type="number" min="50" max="100" value={values.so2Rest ?? ""} onChange={(event) => update("so2Rest", nullableNumber(event.target.value))} />
            </label>
            <label>FC en reposo
              <input type="number" min="20" max="250" value={values.fcRest ?? ""} onChange={(event) => update("fcRest", nullableNumber(event.target.value))} />
            </label>
            <label>SO2 después de caminata
              <input type="number" min="50" max="100" value={values.so2Post ?? ""} onChange={(event) => update("so2Post", nullableNumber(event.target.value))} />
            </label>
            <label>FC después de caminata
              <input type="number" min="20" max="250" value={values.fcPost ?? ""} onChange={(event) => update("fcPost", nullableNumber(event.target.value))} />
            </label>
            <label>Distancia caminata
              <div className="input-with-suffix">
                <input type="number" min="0" step="50" value={values.distanceMeters} onChange={(event) => update("distanceMeters", Number(event.target.value))} />
                <span>metros</span>
              </div>
            </label>
            <label>Borg final
              <select value={values.borgFinal} onChange={(event) => update("borgFinal", Number(event.target.value))}>
                {Array.from({ length: 11 }, (_, index) => <option key={index} value={index}>{index}</option>)}
              </select>
            </label>
          </div>
        </section>

        <section className="clinical-edit-card">
          <div className="clinical-edit-card-title">
            <span className="eyebrow">Criterios</span>
            <h2>Cómo terminó la caminata</h2>
          </div>
          <div className="clinical-choice-stack">
            <label className="clinical-choice clinical-choice-success">
              <input type="checkbox" checked={values.completed} onChange={(event) => update("completed", event.target.checked)} />
              <span><strong>Completada con éxito</strong><small>Activa por defecto para cada nueva atención.</small></span>
            </label>
            <label className="clinical-choice">
              <input type="checkbox" checked={values.stopped} onChange={(event) => update("stopped", event.target.checked)} />
              <span><strong>Se detuvo durante la marcha</strong><small>Marcala si frenó antes de tiempo.</small></span>
            </label>
            <label className="clinical-choice clinical-choice-warning">
              <input type="checkbox" checked={values.symptoms} onChange={(event) => update("symptoms", event.target.checked)} />
              <span><strong>Presentó síntomas al final</strong><small>Se conserva en su ficha y estadísticas.</small></span>
            </label>
          </div>
        </section>
      </div>

      <footer className="clinical-edit-actions">
        <button className="button button-primary" type="button" disabled={isPending} onClick={() => save()}>
          {isPending ? "Guardando..." : "Guardar cambios"}
        </button>
        <button className="button button-secondary" type="button" disabled={isPending} onClick={() => save(`/revision-medica/${encounterId}`)}>
          Guardar e ir a revisión
        </button>
      </footer>
    </main>
  );
}
