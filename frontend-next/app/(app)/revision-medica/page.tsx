import Link from "next/link";
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

export default async function MedicalReviewPage({ searchParams }: { searchParams: Promise<{ fecha?: string; q?: string }> }) {
  await requireProfile(["admin", "medico", "espirometrista"]);
  const params = await searchParams;
  const supabase = await createClient();
  const today = params.fecha && /^\d{4}-\d{2}-\d{2}$/.test(params.fecha) ? params.fecha : new Date().toISOString().slice(0, 10);
  const query = (params.q ?? "").trim().toLocaleLowerCase("es-AR");
  const { data, error } = await supabase.rpc("medical_review_queue", { target_date: today });
  const entries = ((data ?? []) as ReviewEntry[]).filter((entry) => {
    if (!query) return true;
    return `${entry.patient_name} ${entry.dni ?? ""}`.toLocaleLowerCase("es-AR").includes(query);
  });
  const withoutFile = entries.filter((entry) => entry.attendance_status !== "atendido" || !entry.has_source_file);
  const readyForReview = entries.filter((entry) => entry.attendance_status === "atendido" && entry.has_source_file && !entry.has_result);
  const resolved = entries.filter((entry) => entry.has_result);
  const dateLabel = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(`${today}T12:00:00`));

  return (
    <main className="shell">
      <section className="legacy-review-board">
        <header className="legacy-review-head">
          <div>
            <p>Revision medica</p>
            <h1>Atenciones de Hoy</h1>
            <span>Mostrando pacientes del dia seleccionado.</span>
          </div>
          <form className="legacy-review-filter" action="/revision-medica">
            <label>Filtrar por fecha<input name="fecha" type="date" defaultValue={today} /></label>
            <label>Buscar paciente<input name="q" defaultValue={params.q ?? ""} placeholder="Nombre o DNI..." /></label>
            <button type="submit">Ir</button>
          </form>
        </header>
        {error && <p className="notice error">No se pudo cargar la cola: {error.message}</p>}
        <section className="legacy-review-summary" aria-label="Resumen de revisiones">
          <div className="missing"><strong>{withoutFile.length}</strong><span>Falta atender / PDF</span></div>
          <div className="pending"><strong>{readyForReview.length}</strong><span>Para revisar</span></div>
          <div className="done"><strong>{resolved.length}</strong><span>Con resultado</span></div>
        </section>
        <section className="legacy-review-list">
          {entries.length === 0 && <p className="empty">No se encontraron pacientes para revisar.</p>}
          {entries.map((entry) => {
            const isReady = readyForReview.some((item) => item.encounter_id === entry.encounter_id);
            const cardState = entry.has_result ? "done" : isReady ? "pending" : "missing";
            return (
              <article className={`legacy-review-card ${cardState}`} key={entry.encounter_id}>
                <time><span>{dateLabel.slice(0, 5)}</span><b>{entry.encounter_time?.slice(0, 5) || "--:--"}</b></time>
                <div className="legacy-review-patient">
                  <strong>{entry.patient_name}</strong>
                  <div><span>{entry.study_type}</span>{entry.dni && <span>{entry.dni}</span>}{entry.medical_control_today && <em>Control medico hoy</em>}{entry.has_result && <em>Resultado listo</em>}</div>
                  <p>{entry.has_result ? "Resultado medico guardado." : isReady ? "Paciente atendido con PDF cargado. Falta marcar el resultado medico." : entry.has_source_file ? "Falta confirmar que el paciente fue atendido." : "Todavia no esta listo para revision medica."}</p>
                </div>
                {(isReady || entry.has_result) ? <Link className={`legacy-review-action ${cardState}`} href={`/revision-medica/${entry.encounter_id}`}>{entry.has_result ? "Ver revision" : "Revisar PDF"}</Link> : <span className={`legacy-review-action ${cardState} disabled`}>Abrir ficha</span>}
              </article>
            );
          })}
        </section>
      </section>
    </main>
  );
}
