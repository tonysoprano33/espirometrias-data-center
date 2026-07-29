import Link from "next/link";
import { notFound } from "next/navigation";
import { requireProfile } from "../../../lib/auth/require-profile";
import { createClient } from "../../../lib/supabase/server";
import { MedicalResultForm } from "./medical-result-form";
import { PdfPreview } from "./pdf-preview";
import { SourceFileForm } from "./source-file-form";
import { TechnicianNoteForm } from "./technician-note-form";

type DetailPageProps = { params: Promise<{ id: string }> };
type QueueEntry = {
  encounter_id: string;
  encounter_time: string | null;
  patient_name: string;
  has_result: boolean;
  has_source_file: boolean;
  attendance_status: string;
};
type Attachment = {
  id: string;
  original_name: string;
  file_kind: string;
  storage_bucket: string;
  object_path: string;
  mime_type: string;
  analysis_status: string;
  created_at?: string;
};

function formatDate(value: string | null) {
  if (!value) return "Sin fecha";
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function oxygenTone(value: number | null | undefined) {
  if (value == null) return "neutral";
  if (value < 90) return "alert";
  if (value < 95) return "watch";
  return "ok";
}

function fileStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    uploaded: "PDF subido",
    detected: "Datos detectados",
    read: "Datos detectados",
    analyzed: "Datos detectados",
    failed: "Fallo la lectura",
  };
  return labels[status ?? ""] ?? "PDF cargado";
}

export default async function MedicalReviewDetailPage({ params }: DetailPageProps) {
  const { profile } = await requireProfile(["admin", "medico", "espirometrista"]);
  const { id } = await params;
  const supabase = await createClient();
  const { data: encounter } = await supabase
    .from("encounters")
    .select("id, encounter_date, encounter_time, study_type, coverage_type, coverage_name, attendance_status, medical_control_today, technician_notes, patient:patients(full_name, dni, birth_date, gender, bmi), vital_signs(so2_rest, fc_rest, so2_post, fc_post), walk_tests(distance_meters, completed, stopped, symptoms, borg_final, minute_readings), spirometry_results(respiratory_pattern, obstruction_grade, restriction_grade, bronchodilator_positive, suggested_bronchodilator_positive, suggested_bronchodilator_reason, physician_comment, measured_values, suggested_summary, suggested_code, suggested_probability, final_code), attachments(id, original_name, file_kind, storage_bucket, object_path, mime_type, analysis_status, created_at)")
    .eq("id", id)
    .is("deleted_at", null)
    .maybeSingle();

  if (!encounter) notFound();

  const { data: latestNote } = await supabase
    .from("clinical_notes")
    .select("body, created_at")
    .eq("encounter_id", id)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const { data: queueData } = await supabase.rpc("medical_review_queue", {
    target_date: encounter.encounter_date,
  });
  const reviewQueue = ((queueData ?? []) as QueueEntry[]).filter(
    (entry) => entry.attendance_status === "atendido" && entry.has_source_file,
  );
  const currentIndex = reviewQueue.findIndex((entry) => entry.encounter_id === id);
  const previousReview = currentIndex > 0 ? reviewQueue[currentIndex - 1] : null;
  const nextReview =
    currentIndex >= 0 && currentIndex < reviewQueue.length - 1
      ? reviewQueue[currentIndex + 1]
      : null;
  const pendingCount = reviewQueue.filter((entry) => !entry.has_result).length;

  const patient = Array.isArray(encounter.patient) ? encounter.patient[0] : encounter.patient;
  const vitals = Array.isArray(encounter.vital_signs)
    ? encounter.vital_signs[0]
    : encounter.vital_signs;
  const walk = Array.isArray(encounter.walk_tests) ? encounter.walk_tests[0] : encounter.walk_tests;
  let result: any = Array.isArray(encounter.spirometry_results)
    ? encounter.spirometry_results[0]
    : encounter.spirometry_results;

  if (!result) {
    const { data: importedResult } = await supabase
      .from("spirometry_results")
      .select("respiratory_pattern, bronchodilator_positive, suggested_bronchodilator_positive, suggested_bronchodilator_reason, physician_comment, measured_values, suggested_summary, suggested_code, suggested_probability, final_code")
      .eq("encounter_id", id)
      .maybeSingle();
    result = importedResult;
  }

  const attachments = (encounter.attachments ?? []) as Attachment[];
  const source = attachments
    .filter((file) => ["pdf_resultado", "foto_resultado"].includes(file.file_kind))
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))[0];
  const sourceUrl = source ? `/api/attachments/${source.id}/content` : null;
  const hasResult = Boolean(result?.final_code || result?.respiratory_pattern);
  const suggestionCode = result?.suggested_code?.trim() || "";
  const suggestionSummary = result?.suggested_summary?.trim() || "";
  const canEditSource = profile.role === "admin" || profile.role === "espirometrista";
  const canEditResult = profile.role === "admin" || profile.role === "medico";
  const note = latestNote?.body || encounter.technician_notes;
  const walkHasAlert =
    Boolean(walk?.stopped || walk?.symptoms || walk?.completed === false) ||
    (vitals?.so2_post != null && vitals.so2_post < 90) ||
    (vitals?.so2_rest != null &&
      vitals?.so2_post != null &&
      vitals.so2_rest - vitals.so2_post >= 4);

  return (
    <main className="shell doctor-review-page">
      <header className="doctor-review-header">
        <div>
          <h1>{patient?.full_name ?? "Paciente sin nombre"}</h1>
          <p>
            {formatDate(encounter.encounter_date)} | {encounter.study_type} |{" "}
            {encounter.coverage_type}
            {encounter.coverage_name ? ` · ${encounter.coverage_name}` : ""}
          </p>
        </div>
        {sourceUrl && (
          <details className="review-file-options">
            <summary>PDF · Opciones del archivo +</summary>
            <div>
              <a href={sourceUrl} target="_blank" rel="noreferrer">
                Abrir archivo grande
              </a>
              <a href={sourceUrl} download={source.original_name}>
                Descargar archivo
              </a>
            </div>
          </details>
        )}
      </header>

      <section className="review-queue-banner" aria-label="Navegacion del medico">
        <div>
          <small>Navegacion del doctor</small>
          <strong>
            {pendingCount
              ? `Quedan ${pendingCount} paciente(s) pendientes de diagnostico.`
              : "No quedan pacientes pendientes para diagnosticar hoy."}
          </strong>
          <span>
            Los pendientes se descuentan solamente cuando el medico guarda un resultado.
          </span>
        </div>
        <div className="review-queue-controls">
          <div>
            {previousReview ? (
              <Link href={`/revision-medica/${previousReview.encounter_id}`}>
                Anterior paciente
              </Link>
            ) : (
              <span className="navigation-disabled">Sin anterior</span>
            )}
            {previousReview && (
              <small>
                <b>{previousReview.encounter_time?.slice(0, 5) ?? "--:--"}</b>{" "}
                {previousReview.patient_name}
              </small>
            )}
          </div>
          <div>
            {nextReview ? (
              <Link className="next" href={`/revision-medica/${nextReview.encounter_id}`}>
                Siguiente paciente
              </Link>
            ) : (
              <span className="navigation-disabled">No hay siguiente pendiente</span>
            )}
            {nextReview && (
              <small>
                <b>{nextReview.encounter_time?.slice(0, 5) ?? "--:--"}</b>{" "}
                {nextReview.patient_name}
              </small>
            )}
          </div>
        </div>
      </section>

      {encounter.medical_control_today && (
        <div className="medical-control-banner">Control medico hoy</div>
      )}

      <div className="review-workspace">
        <section className="pdf-review-card">
          {sourceUrl && source?.file_kind.includes("pdf") ? (
            <PdfPreview url={sourceUrl} name={source.original_name} />
          ) : sourceUrl ? (
            <div className="pdf-page-frame">
              <span className="pdf-page-label">Pagina 1</span>
              <div className="pdf-page-viewport">
                {/* The attachment endpoint validates access before serving the image. */}
                <img className="pdf-page-image" src={sourceUrl} alt="Resultado de espirometria" />
              </div>
            </div>
          ) : (
            <div className="document-empty">
              Todavia no hay un documento para visualizar.
            </div>
          )}
        </section>

        <aside className="review-panel-compact">
          <section className="clinical-signs-card">
            <h2>Signos vitales de la atencion</h2>
            <div className="clinical-signs-grid">
              <div className={`clinical-sign ${oxygenTone(vitals?.so2_rest)}`}>
                <small>SO2 reposo</small>
                <strong>{vitals?.so2_rest ?? "-"}%</strong>
              </div>
              <div className="clinical-sign heart">
                <small>FC reposo</small>
                <strong>{vitals?.fc_rest ?? "-"} lpm</strong>
              </div>
              <div className={`clinical-sign ${oxygenTone(vitals?.so2_post)}`}>
                <small>SO2 post</small>
                <strong>{vitals?.so2_post ?? "-"}%</strong>
              </div>
              <div className="clinical-sign heart">
                <small>FC post</small>
                <strong>{vitals?.fc_post ?? "-"} lpm</strong>
              </div>
            </div>
            {walk && (
              <div className={`walk-clinical-summary ${walkHasAlert ? "alert" : "ok"}`}>
                <strong>
                  {walkHasAlert
                    ? "Prueba de caminata no normal"
                    : "Prueba realizada con normalidad"}
                </strong>
                <span>
                  {walk.completed ? "Completada" : "Incompleta"} ·{" "}
                  {walk.stopped ? "Se detuvo" : "No se detuvo"} ·{" "}
                  {walk.symptoms ? "Con sintomas" : "Sin sintomas"} · Borg{" "}
                  {walk.borg_final ?? "-"} / 10
                </span>
              </div>
            )}
          </section>

          <section className={`source-status-card ${source ? "ready" : "missing"}`}>
            <div>
              <small>Estado del archivo</small>
              <strong>{source ? fileStatusLabel(source.analysis_status) : "Falta cargar PDF"}</strong>
            </div>
            <span>{hasResult ? "Resultado medico guardado" : "Pendiente del medico"}</span>
          </section>

          {canEditSource && (
            <details className="source-file-details">
              <summary>{source ? "Cambiar PDF o foto" : "Cargar PDF o foto"}</summary>
              <SourceFileForm encounterId={id} currentName={source?.original_name} />
            </details>
          )}

          {canEditResult && (
            <MedicalResultForm
              encounterId={id}
              initialCode={result?.final_code ?? result?.respiratory_pattern ?? ""}
              initialComment={result?.physician_comment ?? ""}
              suggestedCode={suggestionCode}
              suggestedSummary={suggestionSummary}
              suggestedProbability={result?.suggested_probability}
              measuredValues={result?.measured_values}
              bronchodilatorPositive={Boolean(result?.bronchodilator_positive)}
              suggestedBronchodilatorPositive={Boolean(
                result?.suggested_bronchodilator_positive,
              )}
              suggestedBronchodilatorReason={result?.suggested_bronchodilator_reason}
            />
          )}

          {note && (
            <section className="notes-next">
              <h2>Nota breve para el medico</h2>
              <p>{note}</p>
            </section>
          )}

          {canEditSource && <TechnicianNoteForm encounterId={id} />}
        </aside>
      </div>
    </main>
  );
}
