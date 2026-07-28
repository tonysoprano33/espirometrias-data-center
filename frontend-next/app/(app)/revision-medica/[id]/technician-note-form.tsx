"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function TechnicianNoteForm({ encounterId }: { encounterId: string }) {
  const router = useRouter();
  const [body, setBody] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!body.trim()) return;
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch(`/api/encounters/${encounterId}/note`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ body }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "No se pudo guardar la nota.");
      setBody("");
      setMessage("Nota guardada para el médico.");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo guardar la nota.");
    } finally {
      setSaving(false);
    }
  }

  return <section className="note-editor-next"><h2>Nota para el médico</h2><textarea value={body} onChange={(event) => setBody(event.target.value)} maxLength={2000} rows={3} placeholder="Ej.: repetir control, paciente con dificultad para completar la maniobra..." /><button className="button" type="button" onClick={save} disabled={saving || !body.trim()}>{saving ? "Guardando..." : "Guardar nota"}</button>{message && <small role="status">{message}</small>}</section>;
}
