import Link from "next/link";
import { notFound } from "next/navigation";
import { requireProfile } from "../../../lib/auth/require-profile";
import { createClient } from "../../../lib/supabase/server";
import { MedicalResultForm } from "./medical-result-form";
import { SourceFileForm } from "./source-file-form";
import { TechnicianNoteForm } from "./technician-note-form";
import { PdfPreview } from "./pdf-preview";

type DetailPageProps = { params: Promise<{ id: string }> };
type QueueEntry = { encounter_id: string; encounter_time: string | null; patient_name: string; has_result: boolean; has_source_file: boolean; attendance_status: string };

function formatDni(value: string | null) {
  if (!value) return "Sin DNI";
  const digits = value.replace(/\D/g, "");
  return digits ? new Intl.NumberFormat("es-AR").format(Number(digits)) : value;
}

function formatDate(value: string | null) {
  if (!value) return "Sin fecha";
  return new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(`${value}T12:00:00`));
}

export default async function MedicalReviewDetailPage({ params }: DetailPageProps) {
  const { profile } = await requireProfile(["admin", "medico", "espirometrista"]);
  const { id } = await params;
  const supabase = await createClient();
  const { data: encounter } = await supabase
    .from("encounters")
    .select("id, encounter_date, encounter_time, study_type, coverage_type, coverage_name, attendance_status, medical_control_today, technician_notes, patient:patients(full_name, dni, birth_date, gender, bmi), vital_signs(so2_rest, fc_rest, so2_post, fc_post), walk_tests(distance_meters, completed, stopped, symptoms, borg_final, minute_readings), spirometry_results(respiratory_pattern, obstruction_grade, restriction_grade, bronchodilator_positive, physician_comment, suggested_summary, suggested_code, suggested_probability, final_code), attachments(original_name, file_kind, storage_bucket, object_path, analysis_status, created_at)")
    .eq("id", id)
    .is("deleted_at", null)
    .maybeSingle();

  if (!encounter) notFound();
  const { data: latestNote } = await supabase.from("clinical_notes").select("body, created_at").eq("encounter_id", id).order("created_at", { ascending: false }).limit(1).maybeSingle();

  const { data: queueData } = await supabase.rpc("medical_review_queue", { target_date: encounter.encounter_date });
  const reviewQueue = ((queueData ?? []) as QueueEntry[]).filter((entry) => entry.attendance_status === "atendido" && entry.has_source_file);
  const currentIndex = reviewQueue.findIndex((entry) => entry.encounter_id === id);
  const previousReview = currentIndex > 0 ? reviewQueue[currentIndex - 1] : null;
  const nextReview = currentIndex >= 0 && currentIndex < reviewQueue.length - 1 ? reviewQueue[currentIndex + 1] : null;
  const pendingCount = reviewQueue.filter((entry) => !entry.has_result).length;

  const patient = Array.isArray(encounter.patient) ? encounter.patient[0] : encounter.patient;
  const vitals = Array.isArray(encounter.vital_signs) ? encounter.vital_signs[0] : encounter.vital_signs;
  const walk = Array.isArray(encounter.walk_tests) ? encounter.walk_tests[0] : encounter.walk_tests;
  let result: any = Array.isArray(encounter.spirometry_results) ? encounter.spirometry_results[0] : encounter.spirometry_results;
  // Keep the suggestion visible even if a relationship cache is stale after import.
  if (!result) {
    const { data: importedResult } = await supabase.from("spirometry_results").select("respiratory_pattern, physician_comment, suggested_summary, suggested_code, suggested_probability, final_code").eq("encounter_id", id).maybeSingle();
    result = importedResult;
  }
  const attachments = (encounter.attachments ?? []) as Array<{ original_name: string; file_kind: string; storage_bucket: string; object_path: string; analysis_status: string; created_at?: string }>;
  const source = attachments.filter((file) => ["pdf_resultado", "foto_resultado"].includes(file.file_kind)).sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))[0];
  let sourceUrl: string | null = null;
  let sourceError = "";
  if (source) {
    const signed = await supabase.storage.from(source.storage_bucket).createSignedUrl(source.object_path, 60 * 30);
    sourceUrl = signed.data?.signedUrl ?? null;
    if (signed.error) sourceError = signed.error.message;
    // Legacy imports copied attachment metadata, not the binary object. Keep old
    // media reachable while those files are being re-uploaded to Supabase.
    if (!sourceUrl) {
      const legacyBase = (process.env.LEGACY_MEDIA_BASE_URL || "https://espirometrias-data-center.vercel.app/media").replace(/\/$/, "");
      sourceUrl = `${legacyBase}/${source.object_path.split("/").map(encodeURIComponent).join("/")}`;
    }
  }
  const hasResult = Boolean(result?.respiratory_pattern);
  const statusLabel = hasResult ? "Resultado guardado" : source ? "Pendiente de resultado medico" : "Falta cargar PDF";
  const suggestionCode = result?.suggested_code?.trim() || "";
  const suggestionSummary = result?.suggested_summary?.trim() || "";

  return <main className="shell">
    <header className="review-detail-head">
      <div>
        <p>Revision medica</p>
        <h1>{patient?.full_name ?? "Paciente sin nombre"}</h1>
        <span>{formatDate(encounter.encounter_date)} | {encounter.study_type} | {encounter.coverage_type}{encounter.coverage_name ? ` · ${encounter.coverage_name}` : ""}</span>
      </div>
      <div className="detail-header-actions"><Link className="legacy-review-button" href="/revision-medica">Volver a Revision medica</Link></div>
    </header>

    {encounter.medical_control_today && <div className="medical-control-banner">Control medico hoy</div>}

    <nav className="review-detail-navigation" aria-label="Navegacion de revision">
      <strong>{pendingCount ? `Quedan ${pendingCount} paciente(s) para revisar` : "No quedan pacientes pendientes"}</strong>
      <div>{previousReview ? <Link href={`/revision-medica/${previousReview.encounter_id}`}>Anterior</Link> : <span className="navigation-disabled">Anterior</span>}<Link href="/revision-medica">Lista de pacientes</Link>{nextReview ? <Link href={`/revision-medica/${nextReview.encounter_id}`}>Siguiente</Link> : <span className="navigation-disabled">Siguiente</span>}<span>{statusLabel} · {encounter.encounter_time?.slice(0, 5) ?? "--:--"}</span></div>
    </nav>

    <div className="review-detail-grid">
      <section className="review-document">
        <div className="document-status"><b>{source ? source.original_name : "Sin archivo original"}</b><span>{source ? `Archivo ${source.analysis_status}` : "La revision queda pendiente de PDF o foto"}</span>{sourceError && <small className="document-warning">El archivo figura en la base, pero no está disponible en Storage. Podés volver a subirlo desde esta ficha.</small>}{sourceUrl && <div className="document-actions"><a href={sourceUrl} target="_blank" rel="noreferrer">Abrir archivo grande</a><a href={sourceUrl} download={source?.original_name} target="_blank" rel="noreferrer">Descargar archivo</a></div>}</div>
        {sourceUrl && source?.file_kind.includes("pdf") ? <PdfPreview url={sourceUrl} name={source.original_name} /> : sourceUrl ? <img src={sourceUrl} alt="Resultado de espirometria" /> : <div className="document-empty">Todavia no hay un documento para visualizar.</div>}
      </section>

      <aside className="review-clinical">
        {(profile.role === "admin" || profile.role === "espirometrista") && <SourceFileForm encounterId={id} currentName={source?.original_name} />}
        <section><h2>Datos del paciente</h2><div className="patient-facts"><span><small>DNI</small><b>{formatDni(patient?.dni ?? null)}</b></span><span><small>Nacimiento</small><b>{patient?.birth_date ?? "-"}</b></span><span><small>Genero</small><b>{patient?.gender ?? "-"}</b></span><span><small>BMI</small><b>{patient?.bmi ?? "-"}</b></span></div></section>
        <section><h2>SO2 y frecuencia cardiaca</h2><div className="vitals-next"><div className="vital-next"><span>Reposo</span><b>{vitals?.so2_rest ?? "-"}% / {vitals?.fc_rest ?? "-"}</b></div><div className={`vital-next ${(vitals?.so2_post ?? 100) < 90 ? "alert" : ""}`}><span>Post caminata</span><b>{vitals?.so2_post ?? "-"}% / {vitals?.fc_post ?? "-"}</b></div></div></section>
        {walk && <section><h2>Prueba de caminata</h2><div className={`walk-next ${walk.stopped || walk.symptoms || (vitals?.so2_post ?? 100) < 90 ? "alert" : ""}`}>{walk.completed ? "Prueba completada" : "Prueba incompleta"} · {walk.distance_meters} m · Borg final {walk.borg_final}</div></section>}
        {result && <section className={`result-next ${hasResult ? "saved" : ""}`}><h2>Resultado medico</h2><b>{result.respiratory_pattern ?? result.final_code ?? "Pendiente"}</b><p>{result.physician_comment || "La decisión final queda a cargo del médico."}</p></section>}
        {suggestionCode && <section className="suggestion-preview"><div><small>Sugerencia por valores del PDF</small><strong>{suggestionCode}</strong>{result?.suggested_probability && <b>{result.suggested_probability}% de coincidencia de lectura</b>}{suggestionSummary && <p>{suggestionSummary}</p>}</div><span>La decisión final queda a cargo del médico.</span></section>}
        {(profile.role === "admin" || profile.role === "medico") && <MedicalResultForm encounterId={id} initialCode={result?.final_code ?? ""} initialComment={result?.physician_comment ?? ""} suggestedCode={suggestionCode} suggestedSummary={suggestionSummary} />}
        {(encounter.technician_notes || latestNote?.body) && <section className="notes-next"><h2>Nota breve para el medico</h2><p>{latestNote?.body || encounter.technician_notes}</p></section>}
        {(profile.role === "admin" || profile.role === "espirometrista") && <TechnicianNoteForm encounterId={id} />}
      </aside>
    </div>
  </main>;
}
