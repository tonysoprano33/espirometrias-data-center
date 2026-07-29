"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

type Measurement = {
  best?: number | string | null;
  lln?: number | string | null;
  percent?: number | string | null;
  pct?: number | string | null;
};

type MedicalResultFormProps = {
  encounterId: string;
  initialCode: string;
  initialComment: string;
  suggestedCode?: string | null;
  suggestedSummary?: string | null;
  suggestedProbability?: number | null;
  measuredValues?: Record<string, Measurement | unknown> | null;
  bronchodilatorPositive?: boolean;
  suggestedBronchodilatorPositive?: boolean;
  suggestedBronchodilatorReason?: string | null;
};

function formatMeasure(value: unknown) {
  if (value == null || value === "") return "-";
  return String(value).replace(".", ",");
}

function readMeasurement(
  values: Record<string, Measurement | unknown> | null | undefined,
  keys: string[],
) {
  for (const key of keys) {
    const item = values?.[key];
    if (item && typeof item === "object" && !Array.isArray(item)) {
      return item as Measurement;
    }
  }
  return null;
}

export function MedicalResultForm({
  encounterId,
  initialCode,
  initialComment,
  suggestedCode,
  suggestedSummary,
  suggestedProbability,
  measuredValues,
  bronchodilatorPositive,
  suggestedBronchodilatorPositive,
  suggestedBronchodilatorReason,
}: MedicalResultFormProps) {
  const router = useRouter();
  const [code, setCode] = useState(initialCode);
  const [message, setMessage] = useState("");
  const [isSaving, startTransition] = useTransition();
  const fvc = readMeasurement(measuredValues, ["FVC", "fvc"]);
  const fev1 = readMeasurement(measuredValues, ["FEV1", "fev1"]);
  const ratio = readMeasurement(measuredValues, [
    "FEV1/FVC",
    "FEV1FVC",
    "fev1_fvc",
    "ratio",
  ]);
  const measurements = [
    ["FVC", fvc],
    ["FEV1", fev1],
    ["FEV1/FVC", ratio],
  ] as const;

  function save() {
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${encounterId}/medical-result`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ code, comment: initialComment }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage(body.error ?? "No se pudo guardar.");
        return;
      }
      setMessage("Resultado guardado");
      router.refresh();
    });
  }

  return (
    <section className="medical-decision-panel">
      {suggestedCode && (
        <div className="medical-suggestion-card">
          <div className="medical-suggestion-head">
            <div>
              <small>Sugerido por valores del PDF</small>
              <strong>{suggestedCode}</strong>
            </div>
            <button type="button" onClick={() => setCode(suggestedCode)}>
              Usar sugerido
            </button>
          </div>
          {suggestedProbability != null && (
            <b>{suggestedProbability}% probable {suggestedCode}</b>
          )}
          {suggestedSummary && <p>{suggestedSummary}</p>}
          {measurements.some(([, value]) => value) && (
            <div className="measurement-grid">
              {measurements.map(([label, value]) => (
                <div key={label}>
                  <strong>{label}</strong>
                  <span>
                    Best {formatMeasure(value?.best)} | LLN {formatMeasure(value?.lln)} | %{" "}
                    {formatMeasure(value?.percent ?? value?.pct)}
                  </span>
                </div>
              ))}
            </div>
          )}
          {suggestedBronchodilatorPositive && (
            <div className="bronchodilator-reading">
              <strong>Broncodilatador positivo</strong>
              {suggestedBronchodilatorReason && <span>{suggestedBronchodilatorReason}</span>}
            </div>
          )}
          <small className="decision-help">
            Es ayuda para carga rapida. La decision final queda en la revision medica.
          </small>
        </div>
      )}

      <div className={`final-result-card ${initialCode ? "saved" : "pending"}`}>
        <label htmlFor="medical-result-code">Resultado final del medico</label>
        <input
          id="medical-result-code"
          value={code}
          onChange={(event) => setCode(event.target.value.toUpperCase())}
          placeholder="N, OL, RL, RLOMS..."
        />
        <p>Aca va el resultado final elegido por el medico.</p>
        <span>{initialCode ? "Resultado guardado" : "Resultado listo para guardar"}</span>
      </div>

      {(bronchodilatorPositive || suggestedBronchodilatorPositive) && (
        <div className="bronchodilator-confirmed">
          Broncodilatador positivo
        </div>
      )}

      <button
        className="save-medical-result"
        type="button"
        onClick={save}
        disabled={isSaving || !code.trim()}
      >
        {isSaving ? "Guardando..." : "Guardar resultado"}
      </button>
      {message && <small className="save-result-message">{message}</small>}
    </section>
  );
}
