"use client";

import { ChangeEvent, useState } from "react";

export function SourceFileForm({ encounterId, currentName }: { encounterId: string; currentName?: string }) {
  const [message, setMessage] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setMessage("");
    setIsUploading(true);
    try {
      const form = new FormData();
      form.set("file", file);
      const response = await fetch(`/api/encounters/${encounterId}/source-file`, { method: "POST", body: form });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error ?? "No se pudo cargar el archivo.");
      setMessage("Archivo cargado. Actualizando la vista...");
      window.location.reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo cargar el archivo.");
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  }

  return <section className="source-file-panel"><div><h2>{currentName ? "Reemplazar PDF o foto" : "Cargar PDF o foto"}</h2><p>{currentName ? `Archivo actual: ${currentName}` : "Subi el resultado original para visualizarlo en la ficha."}</p></div><label className="source-file-picker"><span>{isUploading ? "Subiendo..." : "Elegir archivo"}</span><input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={upload} disabled={isUploading} /></label>{message && <small role="status">{message}</small>}</section>;
}
