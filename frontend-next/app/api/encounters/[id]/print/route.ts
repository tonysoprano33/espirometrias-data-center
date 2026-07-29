import { NextResponse } from "next/server";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";
import { createClinicalReport } from "../../../../lib/reports/clinical-report";
import { loadReportData } from "../../../../lib/reports/load-report-data";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const { id } = await params;
    const supabase = await createClient();
    const loaded = await loadReportData(supabase, id);
    if (loaded.error) return NextResponse.json({ error: loaded.error }, { status: 404 });
    if (loaded.missing) {
      return NextResponse.json({ error: `No se puede imprimir. Completar: ${loaded.missing.join(", ")}.` }, { status: 422 });
    }
    const bytes = await createClinicalReport(loaded.data!);
    return new NextResponse(Buffer.from(bytes), {
      headers: {
        "content-type": "application/pdf",
        "content-disposition": `inline; filename="Informe_${loaded.data!.patientName.replace(/[^a-zA-Z0-9]+/g, "_")}.pdf"`,
        "cache-control": "private, no-store",
      },
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo imprimir." }, { status: 500 });
  }
}
