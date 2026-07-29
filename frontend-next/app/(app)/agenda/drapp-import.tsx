"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  parseDrappOcrLines,
  parseDrappText,
  type DrappOcrItem,
  type DrappOcrLine,
  type DrappRow,
} from "../../lib/drapp";
import type { PhysicianOption } from "./agenda-types";

type OcrBoundingBox = { x0: number; y0: number; x1: number; y1: number };
type OcrEntry = { text?: string; bbox?: OcrBoundingBox };
type OcrResult = {
  data: {
    text: string;
    words?: OcrEntry[];
    lines?: OcrEntry[];
  };
};

declare global {
  interface Window {
    Tesseract?: {
      recognize: (source: File | HTMLCanvasElement, languages: string) => Promise<OcrResult>;
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

function normalizeOcrText(value: string | undefined) {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function buildOcrLines(result: OcrResult) {
  const words = (result.data.words ?? [])
    .filter((word): word is Required<OcrEntry> => Boolean(normalizeOcrText(word.text) && word.bbox))
    .map((word) => ({
      text: normalizeOcrText(word.text),
      x: Number(word.bbox.x0),
      y: Number(word.bbox.y0),
      height: Math.max(1, Number(word.bbox.y1) - Number(word.bbox.y0)),
    }));

  if (!words.length) {
    return (result.data.lines ?? []).map((line, index) => ({
      text: normalizeOcrText(line.text),
      y: line.bbox?.y0 ?? index * 30,
      items: [] as DrappOcrItem[],
    })).filter((line) => line.text);
  }

  const heights = words.map((word) => word.height).sort((left, right) => left - right);
  const tolerance = Math.max(12, Math.min(28, (heights[Math.floor(heights.length / 2)] || 16) * .85));
  const sortedWords = [...words].sort((left, right) =>
    Math.abs(left.y - right.y) <= tolerance / 3 ? left.x - right.x : left.y - right.y);
  const lines: Array<{ y: number; items: DrappOcrItem[] }> = [];

  for (const word of sortedWords) {
    const currentLine = lines.at(-1);
    if (!currentLine || Math.abs(currentLine.y - word.y) > tolerance) {
      lines.push({ y: word.y, items: [word] });
      continue;
    }
    currentLine.items.push(word);
    currentLine.y = ((currentLine.y * (currentLine.items.length - 1)) + word.y) / currentLine.items.length;
  }

  return lines.map((line): DrappOcrLine => {
    const items = [...line.items].sort((left, right) => left.x - right.x);
    return {
      text: normalizeOcrText(items.map((item) => item.text).join(" ")),
      y: line.y,
      items,
    };
  }).filter((line) => line.text);
}

async function prepareOcrSource(file: File) {
  if (!file.type.toLowerCase().startsWith("image/")) {
    return { source: file, width: 0 };
  }

  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error("No se pudo procesar la captura."));
      element.src = objectUrl;
    });
    const scale = image.width < 1100 ? 2.4 : image.width < 1500 ? 1.65 : 1;
    const width = Math.max(image.width, Math.round(image.width * scale));
    const height = Math.max(image.height, Math.round(image.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) return { source: file, width: image.width };
    context.fillStyle = "#fff";
    context.fillRect(0, 0, width, height);
    context.imageSmoothingEnabled = true;
    context.filter = "grayscale(1) contrast(1.3) brightness(1.05)";
    context.drawImage(image, 0, 0, width, height);
    context.filter = "none";
    return { source: canvas, width };
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export function DrappImport({ physicians }: { physicians: PhysicianOption[] }) {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [isPending, startTransition] = useTransition();
  const [rows, setRows] = useState<DrappRow[]>([]);
  const [message, setMessage] = useState("");
  const [captureStatus, setCaptureStatus] = useState("Sin captura");
  const defaultPhysicianId = physicians.find((item) => item.is_default)?.physician_id ?? null;

  function readImage(file: File) {
    if (!file.type.startsWith("image/")) {
      setMessage("Elegí una captura PNG, JPG o WEBP.");
      return;
    }
    setCaptureStatus(`Captura lista: ${Math.max(1, Math.round(file.size / 1024))} KB`);
    setMessage("Leyendo la captura. Esto puede tardar unos segundos...");
    startTransition(async () => {
      try {
        await loadTesseract();
        setCaptureStatus("Preparando OCR...");
        const prepared = await prepareOcrSource(file);
        setCaptureStatus("Leyendo captura...");
        const result = await window.Tesseract?.recognize(prepared.source, "spa+eng");
        if (!result) throw new Error("No se pudo iniciar el lector OCR.");
        const ocrLines = buildOcrLines(result);
        const extracted = ocrLines.length
          ? ocrLines.map((line) => line.text).join("\n")
          : result.data.text ?? "";
        const parsed = ocrLines.some((line) => line.items.length)
          ? parseDrappOcrLines(ocrLines, prepared.width)
          : parseDrappText(extracted);
        const missingDate = parsed.some((row) => !row.agendaDate);
        setRows(parsed);
        setCaptureStatus(parsed.length ? (missingDate ? "Revisar fecha" : "Captura leída") : "Sin pacientes válidos");
        setMessage(parsed.length
          ? missingDate
            ? `Se detectaron ${parsed.length} pacientes, pero no pude leer la fecha del encabezado. Completala antes de confirmar.`
            : `Se detectaron ${parsed.length} pacientes. Revisá fecha, hora, nombre, DNI y cobertura antes de confirmar.`
          : "La captura se leyó, pero no se detectaron pacientes válidos. Elegí otra captura.");
      } catch (error) {
        setCaptureStatus("No se pudo leer");
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
        body: JSON.stringify({ rows, referringPhysicianId: defaultPhysicianId }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage(body.error ?? "No se pudo importar.");
        return;
      }
      const dates = Array.isArray(body.dates) ? ` Agenda: ${body.dates.join(", ")}.` : "";
      setMessage(`Importados: ${body.created}. Duplicados omitidos: ${body.skipped}.${dates}`);
      if (body.created) {
        setRows([]);
        setCaptureStatus("Sin captura");
        router.refresh();
      }
    });
  }

  return <details className="drapp-import">
    <summary>Importar agenda desde Drapp</summary>
    <div className="drapp-import-body">
      <p>Pegá la captura de Drapp con Ctrl+V o elegí el archivo. Primero vas a revisar todos los datos.</p>
      <div
        className="drapp-paste-zone"
        tabIndex={0}
        role="button"
        aria-label="Pegar captura de Drapp"
        onClick={(event) => event.currentTarget.focus()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") fileRef.current?.click();
        }}
        onPaste={(event) => {
          const imageItem = [...event.clipboardData.items].find((item) => item.type.startsWith("image/"));
          const file = imageItem?.getAsFile();
          if (!file) {
            setMessage("El portapapeles no contiene una imagen.");
            return;
          }
          event.preventDefault();
          readImage(file);
        }}
      >
        <div><strong>Pegá una captura con Ctrl+V</strong><span>Hacé click acá y pegá. También podés elegir el archivo manualmente.</span></div>
        <span className="drapp-paste-indicator">{captureStatus}</span>
      </div>
      <div className="drapp-toolbar">
        <button type="button" className="secondary" onClick={() => fileRef.current?.click()} disabled={isPending}>Elegir captura</button>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) readImage(file);
          event.currentTarget.value = "";
        }} />
      </div>
      {message && <p className="drapp-message" role="status">{message}</p>}
      {rows.length > 0 && <div className="drapp-preview">
        <div className="drapp-preview-head"><span>Fecha</span><span>Hora</span><span>Paciente</span><span>DNI</span><span>Estudio</span><span>Cobertura</span><span /></div>
        {rows.map((row, index) => <div className="drapp-preview-row" key={`${row.time}-${index}`}>
          <input type="date" value={row.agendaDate} onChange={(event) => updateRow(index, { agendaDate: event.target.value })} aria-label={`Fecha de ${row.name}`} />
          <input type="time" value={row.time} onChange={(event) => updateRow(index, { time: event.target.value })} />
          <input value={row.name} onChange={(event) => updateRow(index, { name: event.target.value.toUpperCase() })} />
          <input inputMode="numeric" value={row.dni} onChange={(event) => updateRow(index, { dni: event.target.value.replace(/\D/g, "") })} placeholder="Sin DNI" />
          <select value={row.studyType} onChange={(event) => updateRow(index, { studyType: event.target.value as DrappRow["studyType"] })}><option>Ciclometria</option><option>Espirometria</option></select>
          <div className="drapp-coverage"><select value={row.coverageType} onChange={(event) => updateRow(index, { coverageType: event.target.value as DrappRow["coverageType"] })}><option>Particular</option><option>Mutual</option></select>{row.coverageType === "Mutual" && <input value={row.coverageName} onChange={(event) => updateRow(index, { coverageName: event.target.value })} placeholder="Mutual" />}</div>
          <button type="button" className="danger" onClick={() => removeRow(index)}>Quitar</button>
        </div>)}
        <button type="button" className="confirm-import" disabled={isPending || rows.some((row) => !row.agendaDate || !row.name || !row.time)} onClick={importRows}>{isPending ? "Importando..." : `Confirmar ${rows.length} pacientes`}</button>
      </div>}
    </div>
  </details>;
}
