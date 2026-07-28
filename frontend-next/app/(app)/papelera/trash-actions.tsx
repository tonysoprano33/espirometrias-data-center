"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function RestoreEncounterButton({ encounterId }: { encounterId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function restore() {
    setBusy(true);
    const response = await fetch(`/api/trash/encounters/${encounterId}/restore`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) window.alert(body.error ?? "No se pudo restaurar la atencion.");
    else router.refresh();
    setBusy(false);
  }

  return <button type="button" onClick={restore} disabled={busy}>{busy ? "Restaurando..." : "Restaurar"}</button>;
}

export function RestorePatientButton({ patientId }: { patientId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function restore() {
    setBusy(true);
    const response = await fetch(`/api/trash/patients/${patientId}/restore`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) window.alert(body.error ?? "No se pudo restaurar el paciente.");
    else router.refresh();
    setBusy(false);
  }

  return <button type="button" onClick={restore} disabled={busy}>{busy ? "Restaurando..." : "Restaurar"}</button>;
}
