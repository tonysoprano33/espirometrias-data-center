import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";

type ReviewEntry = {
  encounter_id: string;
  encounter_time: string | null;
  patient_name: string;
  dni: string | null;
  study_type: "Ciclometria" | "Espirometria";
  coverage_type: "Mutual" | "Particular";
  attendance_status: "no_llego" | "esperando" | "atendido";
  workflow_status: "pendiente" | "cargada" | "revisada" | "informe_generado" | "entregada";
  has_result: boolean;
  has_source_file: boolean;
  medical_control_today: boolean;
};

export default async function MedicalReviewPage() {
  await requireProfile(["admin", "medico", "espirometrista"]);
  const supabase = await createClient();
  const today = new Date().toISOString().slice(0, 10);
  const { data, error } = await supabase.rpc("medical_review_queue", { target_date: today });
  const entries = (data ?? []) as ReviewEntry[];
  const readyForReview = entries.filter((entry) => entry.attendance_status === "atendido" && entry.has_source_file && !entry.has_result);

  return (
    <main className="next-screen">
      <section className="next-page-heading">
        <p className="eyebrow">Revision medica</p>
        <h1>Cola de diagnostico</h1>
        <p>Solo se muestran como pendientes las atenciones con archivo cargado y sin resultado final.</p>
      </section>
      {error && <p className="notice error">No se pudo cargar la cola: {error.message}</p>}
      <section className="review-summary">
        <strong>{readyForReview.length}</strong>
        <span>pacientes pendientes de diagnostico</span>
      </section>
      <section className="review-list">
        {entries.length === 0 && <p className="empty">No hay pacientes para revisar hoy.</p>}
        {entries.map((entry) => {
          const isReady = readyForReview.some((item) => item.encounter_id === entry.encounter_id);
          return (
            <article className={`review-row ${isReady ? "ready" : entry.has_result ? "resolved" : "waiting"}`} key={entry.encounter_id}>
              <time>{entry.encounter_time?.slice(0, 5) || "--:--"}</time>
              <div><strong>{entry.patient_name}</strong><span>{entry.study_type} · {entry.coverage_type}{entry.dni ? ` · DNI ${entry.dni}` : ""}</span></div>
              <p>{entry.has_result ? "Resultado guardado" : isReady ? "Listo para revisar" : entry.has_source_file ? "Falta confirmar asistencia" : "Sin archivo cargado"}</p>
              {entry.medical_control_today && <b>Control hoy</b>}
              {isReady ? <span className="review-action">Revision detallada: proxima fase</span> : <span className="review-status">{entry.workflow_status}</span>}
            </article>
          );
        })}
      </section>
    </main>
  );
}
