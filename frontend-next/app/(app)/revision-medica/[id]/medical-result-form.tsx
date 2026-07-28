"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

export function MedicalResultForm({ encounterId, initialCode, initialComment, suggestedCode, suggestedSummary }: { encounterId: string; initialCode: string; initialComment: string; suggestedCode?: string | null; suggestedSummary?: string | null }) {
  const router = useRouter();
  const [code, setCode] = useState(initialCode);
  const [comment, setComment] = useState(initialComment);
  const [message, setMessage] = useState("");
  const [isSaving, startTransition] = useTransition();
  function save() {
    startTransition(async () => {
      const response = await fetch(`/api/encounters/${encounterId}/medical-result`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ code, comment }) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) { setMessage(body.error ?? "No se pudo guardar."); return; }
      setMessage("Resultado guardado");
      router.refresh();
    });
  }
  return <section className="result-editor-next"><h2>Resultado final del medico</h2>{suggestedCode && <div className="medical-suggestion"><div><small>Sugerencia automatica</small><strong>{suggestedCode}</strong>{suggestedSummary && <span>{suggestedSummary}</span>}</div><button type="button" onClick={() => setCode(suggestedCode)}>Usar sugerido</button></div>}<label>Codigo elegido<input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} placeholder="N, OL, RL, RLOMS..." /></label><label>Comentario opcional<textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} placeholder="Observacion del medico" /></label><button className="button" type="button" onClick={save} disabled={isSaving || !code.trim()}>Guardar resultado</button>{message && <small>{message}</small>}</section>;
}
