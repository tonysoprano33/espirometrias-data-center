"use client";

import { useEffect, useState } from "react";

type Detail = {
  patient_name: string; dni: string; date_label: string; time: string; study_type: string; coverage_type: string;
  result_code: string; result_label: string; medical_control_today: boolean; technician_notes: string; bronchodilator_positive: boolean; can_edit_file: boolean;
  file: { present: boolean; url: string; name: string; is_image: boolean; status: { label: string; detail: string; key: string } };
  suggestion: { code?: string; reason?: string; values?: Record<string, string | number> };
  vitals: { rest: { so2: number | null; fc: number | null; so2_tone: string }; post: { so2: number | null; fc: number | null; so2_tone: string }; walk: { label: string; tone: string; borg_final: number | null } };
  legacy_review_url: string; print_url: string; can_print: boolean; print_block_reason: string; result_code_options: string[]; previous: { id: number; name: string } | null; next: { id: number; name: string } | null; pending_total: number;
};

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export default function ReviewDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [id, setId] = useState("");
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => { void params.then((value) => setId(value.id)); }, [params]);

  useEffect(() => {
    if (!id) return;
    let active = true;
    setError("");
    fetch(`/api/v1/revision-medica/${id}/`, { credentials: "same-origin" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.message || "No se pudo cargar la ficha.");
        return payload as Detail;
      })
      .then((payload) => { if (active) setData(payload); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "No se pudo cargar la ficha."); });
    return () => { active = false; };
  }, [id, refreshKey]);

  useEffect(() => { if (data) setResult(data.result_code); }, [data]);

  const saveResult = async () => {
    if (!result || !id) return;
    setSaving(true);
    try {
      const response = await fetch(`/api/v1/revision-medica/${id}/resultado/`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ respiratory_result: result }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "No se pudo guardar el resultado.");
      setData((current) => current ? { ...current, result_code: payload.result_code, result_label: payload.result_label, can_print: true } : current);
      setNotice(payload.message);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo guardar el resultado.");
    } finally {
      setSaving(false);
    }
  };

  const uploadFile = async () => {
    if (!id || !selectedFile) return;
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("pdf_file", selectedFile);
      const response = await fetch(`/api/v1/revision-medica/${id}/archivo/`, {
        method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrfToken() }, body: form,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "No se pudo subir el archivo.");
      setNotice(payload.message);
      setSelectedFile(null);
      setRefreshKey((current) => current + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo subir el archivo.");
    } finally {
      setUploading(false);
    }
  };

  return <main className="agenda-shell review-detail-next">
    {error && <p className="notice error">{error}</p>}
    {notice && <p className="notice success">{notice}</p>}
    {!data && !error && <p className="notice">Cargando ficha medica...</p>}
    {data && <>
      <header className="review-detail-head"><div><a className="back-link" href="/revision-medica/">Volver a Revision medica</a><h1>{data.patient_name}</h1><p>{data.date_label} | {data.time} | {data.study_type} | {data.coverage_type} | DNI {data.dni}</p></div><div className="detail-header-actions">{data.can_print && <a className="print-review-button" href={`/django${data.print_url}`} target="_blank">Imprimir informe</a>}<a className="legacy-review-button" href={`/django${data.legacy_review_url}`}>Opciones avanzadas</a></div></header>
      {data.medical_control_today && <p className="medical-control-banner">Control medico hoy</p>}
      <section className="review-detail-navigation"><span>{data.pending_total} pendiente{data.pending_total === 1 ? "" : "s"} para diagnostico</span><div>{data.previous && <a href={`/revision-medica/${data.previous.id}/`}>Anterior: {data.previous.name}</a>}{data.next && <a href={`/revision-medica/${data.next.id}/`}>Siguiente: {data.next.name}</a>}</div></section>
      <section className="review-detail-grid"><article className="review-document"><div className="document-status"><b>{data.file.status.label}</b><span>{data.file.status.detail}</span></div>{data.can_edit_file && <div className="next-file-upload"><label>Reemplazar PDF o foto<input type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(event) => setSelectedFile(event.target.files?.[0] || null)} /></label><button onClick={uploadFile} disabled={!selectedFile || uploading}>{uploading ? "Subiendo y leyendo..." : "Subir y analizar"}</button></div>}{data.file.present ? data.file.is_image ? <img src={`/django${data.file.url}`} alt={`Estudio de ${data.patient_name}`} /> : <iframe src={`/django${data.file.url}#view=FitH`} title={`Estudio de ${data.patient_name}`} /> : <p className="empty">No hay PDF o foto cargada para este paciente.</p>}</article>
        <aside className="review-clinical"><section><h2>Signos y caminata</h2><div className="vitals-next"><Vital label="SO2 reposo" value={data.vitals.rest.so2} tone={data.vitals.rest.so2_tone} /><Vital label="FC reposo" value={data.vitals.rest.fc} /><Vital label="SO2 post" value={data.vitals.post.so2} tone={data.vitals.post.so2_tone} /><Vital label="FC post" value={data.vitals.post.fc} /></div><p className={`walk-next ${data.vitals.walk.tone}`}>{data.vitals.walk.label}{data.vitals.walk.borg_final != null ? ` | Borg final ${data.vitals.walk.borg_final}` : ""}</p></section>
          {data.suggestion.code && <section className="suggestion-next"><h2>Sugerido por el PDF</h2><b>{data.suggestion.code}</b><p>{data.suggestion.reason || "Valores detectados para orientar la revision."}</p></section>}
          <section className={`result-next ${data.result_code ? "saved" : ""}`}><h2>Resultado final del medico</h2><select value={result} onChange={(event) => setResult(event.target.value)} disabled={saving}>{!result && <option value="">Elegir resultado</option>}{data.result_code && !data.result_code_options.includes(data.result_code) && <option value={data.result_code}>{data.result_code}</option>}{data.result_code_options.map((code) => <option key={code} value={code}>{code}</option>)}</select><button onClick={saveResult} disabled={!result || saving}>{saving ? "Guardando..." : "Guardar resultado"}</button><p>{data.result_label || "La decision final queda a cargo del medico."}</p>{data.bronchodilator_positive && <span>Broncodilatador positivo</span>}</section>
          {!data.can_print && <p className="print-block">Impresion pendiente: {data.print_block_reason}</p>}
          {data.technician_notes && <section className="notes-next"><h2>Nota para el medico</h2><p>{data.technician_notes}</p></section>}
        </aside></section>
    </>}
  </main>;
}

function Vital({ label, value, tone = "" }: { label: string; value: number | null; tone?: string }) {
  return <div className={`vital-next ${tone}`}><span>{label}</span><b>{value ?? "-"}</b></div>;
}
