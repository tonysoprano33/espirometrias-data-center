import { requireProfile } from "../../../lib/auth/require-profile";
import { loadReportData } from "../../../lib/reports/load-report-data";
import { createClient } from "../../../lib/supabase/server";
import { AutoPrint } from "../../auto-print";
import { ClinicalPrintPacket } from "../../clinical-print-packet";
import { PrintToolbar } from "../../print-toolbar";

export const dynamic = "force-dynamic";

type PrintPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ auto?: string }>;
};

export default async function EncounterPrintPage({ params, searchParams }: PrintPageProps) {
  await requireProfile(["admin", "espirometrista"]);
  const { id } = await params;
  const { auto } = await searchParams;
  const supabase = await createClient();
  const loaded = await loadReportData(supabase, id);
  const sourceUrl = loaded.sourceAttachment ? `/api/attachments/${loaded.sourceAttachment.id}/content` : undefined;

  if (loaded.error || loaded.missing || !loaded.data) {
    return <main className="print-root">
      <PrintToolbar />
      <section className="print-sheet print-blocked-sheet">
        <h1>Faltan datos antes de imprimir</h1>
        <p>{loaded.error || `Completar: ${loaded.missing?.join(", ")}.`}</p>
      </section>
    </main>;
  }

  return <main className="print-root">
    <AutoPrint enabled={auto === "1"} />
    <PrintToolbar sourceUrl={sourceUrl} />
    <ClinicalPrintPacket data={loaded.data} attachment={loaded.sourceAttachment} />
  </main>;
}
