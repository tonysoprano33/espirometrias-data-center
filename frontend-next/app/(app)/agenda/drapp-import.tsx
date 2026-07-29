"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { parseDrappText, type DrappRow } from "../../lib/drapp";
import type { PhysicianOption } from "./agenda-types";

declare global {
  interface Window {
    Tesseract?: {
      recognize: (source: File, languages: string) => Promise<{ data: { text: string } }>;
    };
  }
}

function loadTesseract() {
  if (window.Tesseract) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-tesseract="true"]');
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("No se pudo cargar el lector OCR.")), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js";
    script.async = true;
    script.dataset.tesseract = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("No se pudo cargar el lector OCR."));
    document.head.appendChild(script);
  });
}

export function DrappImport({ today, physicians }: { today: string; physicians: PhysicianOption[] }) {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [isPending, startTransition] = useTransition();
  const [text, setText] = useState("");
  const [rows, setRows] = useState<DrappRow[]>([]);
  const [message, setMessage] = useState("");
  const defaultPhysicianId = physicians.find((item) => item.is_default)?.physician_id ?? null;

  function preview(rawText: string) {
    const parsed = parseDrappText(rawText);
    setRows(parsed);
    setMessage(parsed.length ? `Se detectaron ${parsed.length} pacientes. Revisa los datos antes de confirmar.` : "No se detectaron filas validas. Podes corregir el texto o elegir otra captura.");
  }

  function readImage(file: File) {
    setMessage("Leyendo la captura. Esto puede tardar unos segundos...");
    startTransition(async () => {
      try {
        await loadTesseract();
        const result = await window.Tesseract?.recognize(file, "spa+eng");
        const extracted = result?.data.text ?? "";
        setText(extracted);
        preview(extracted);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "No se pudo leer la captura.");
      }
    });
  }

  function updateRow(index: number, patch: Partial<DrappRow>) {
    setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));
  }

  function removeRow(index: number) {
    setRows((current) => current.filter((_, rowIndex) => rowIndex !== index));
  }

  function importRows() {
    setMessage("");
    startTransition(async () => {
      const response = await fetch("/api/drapp/import", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ date: today, rows, referringPhysicianId: defaultPhysicianId }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage(body.error ?? "No se pudo importar.");
        return;
      }
      setMessage(`Importados: ${body.created}. Duplicados omitidos: ${body.skipped}.`);
      if (body.created) {
        setRows([]);
        setText("");
        router.refresh();
      }
    });
  }

  return <details className="drapp-import">
    <summary>Importar agenda desde Drapp</summary>
    <div className="drapp-import-body">
      <p>Pega el texto o una captura. Primero vas a ver una confirmacion editable; nada se agrega automaticamente.</p>
      <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Pega aca el texto copiado de Drapp..." rows={5} />
      <div className="drapp-toolbar">
        <button type="button" onClick={() => preview(text)} disabled={isPending || !text.trim()}>Analizar texto</button>
        <button type="button" className="secondary" onClick={() => fileRef.current?.click()} disabled={isPending}>Elegir captura</button>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) readImage(file); }} />
      </div>
      {message && <p className="drapp-message" role="status">{message}</p>}
      {rows.length > 0 && <div className="drapp-preview">
        <div className="drapp-preview-head"><span>Hora</span><span>Paciente</span><span>DNI</span><span>Estudio</span><span>Cobertura</span><span /></div>
        {rows.map((row, index) => <div className="drapp-preview-row" key={`${row.time}-${index}`}>
          <input type="time" value={row.time} onChange={(event) => updateRow(index, { time: event.target.value })} />
          <input value={row.name} onChange={(event) => updateRow(index, { name: event.target.value.toUpperCase() })} />
          <input inputMode="numeric" value={row.dni} onChange={(event) => updateRow(index, { dni: event.target.value.replace(/\D/g, "") })} placeholder="Sin DNI" />
          <select value={row.studyType} onChange={(event) => updateRow(index, { studyType: event.target.value as DrappRow["studyType"] })}><option>Ciclometria</option><option>Espirometria</option></select>
          <div className="drapp-coverage"><select value={row.coverageType} onChange={(event) => updateRow(index, { coverageType: event.target.value as DrappRow["coverageType"] })}><option>Particular</option><option>Mutual</option></select>{row.coverageType === "Mutual" && <input value={row.coverageName} onChange={(event) => updateRow(index, { coverageName: event.target.value })} placeholder="Mutual" />}</div>
          <button type="button" className="danger" onClick={() => removeRow(index)}>Quitar</button>
        </div>)}
        <button type="button" className="confirm-import" disabled={isPending || rows.some((row) => !row.name || !row.time)} onClick={importRows}>{isPending ? "Importando..." : `Confirmar ${rows.length} pacientes`}</button>
      </div>}
    </div>
  </details>;
}
