"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function DeleteEncounterButton({ encounterId, label = "Eliminar" }: { encounterId: string; label?: string }) {
  const router = useRouter(); const [busy, setBusy] = useState(false);
  async function remove() {
    if (!window.confirm("La atención se moverá a la papelera durante 30 días. ¿Continuar?")) return;
    setBusy(true);
    const response = await fetch(`/api/encounters/${encounterId}/manage`, { method: "DELETE" });
    if (!response.ok) { const body = await response.json().catch(() => ({})); window.alert(body.error ?? "No se pudo eliminar."); setBusy(false); return; }
    router.refresh();
  }
  return <button type="button" className="danger compact-action" onClick={remove} disabled={busy}>{busy ? "Eliminando..." : label}</button>;
}

export function EditEncounterButton({ encounterId, date, time, studyType, coverageType, coverageName, controlToday }: { encounterId: string; date: string; time: string; studyType: string; coverageType: string; coverageName: string; controlToday: boolean }) {
  const router = useRouter(); const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    const data = new FormData(event.currentTarget);
    const response = await fetch(`/api/encounters/${encounterId}/manage`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "update", encounterDate: data.get("date"), encounterTime: data.get("time"), studyType: data.get("studyType"), coverageType: data.get("coverageType"), coverageName: data.get("coverageName"), medicalControlToday: data.get("controlToday") === "on" }) });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) { setMessage(body.error ?? "No se pudo editar."); setBusy(false); return; }
    setMessage("Guardado"); router.refresh();
  }
  return <details className="edit-encounter"><summary>Editar</summary><form onSubmit={save}><label>Fecha<input name="date" type="date" defaultValue={date} required /></label><label>Hora<input name="time" type="time" defaultValue={time} /></label><label>Estudio<select name="studyType" defaultValue={studyType}><option>Ciclometria</option><option>Espirometria</option></select></label><label>Cobertura<select name="coverageType" defaultValue={coverageType}><option>Particular</option><option>Mutual</option></select></label><label>Mutual<input name="coverageName" defaultValue={coverageName} /></label><label className="edit-check"><input name="controlToday" type="checkbox" defaultChecked={controlToday} /> Control hoy</label><button type="submit" disabled={busy}>{busy ? "Guardando..." : "Guardar cambios"}</button>{message && <small>{message}</small>}</form></details>;
}
