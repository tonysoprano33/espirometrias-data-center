import { PDFDocument } from "pdf-lib";
import { NextResponse } from "next/server";
import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";
import { createClinicalReport } from "../../lib/reports/clinical-report";
import { loadReportData } from "../../lib/reports/load-report-data";

type AgendaEntry = { encounter_id: string; patient_name: string; can_print: boolean };

export async function GET(request: Request) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const date = new URL(request.url).searchParams.get("date") ?? new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).format(new Date());
    const supabase = await createClient();
    const { data: rawEntries, error } = await supabase.rpc("agenda_entries_v2", { target_date: date });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    const entries = (rawEntries ?? []) as AgendaEntry[];
    if (!entries.length) return NextResponse.json({ error: "No hay pacientes en esta fecha." }, { status: 404 });

    const incomplete = entries.filter((entry) => !entry.can_print);
    if (incomplete.length) {
      return NextResponse.json({
        error: "No se imprimio el dia porque hay pacientes incompletos.",
        patients: incomplete.map((entry) => entry.patient_name),
      }, { status: 422 });
    }

    const merged = await PDFDocument.create();
    for (const entry of entries) {
      const loaded = await loadReportData(supabase, entry.encounter_id);
      if (!loaded.data) {
        return NextResponse.json({ error: `No se pudo preparar el informe de ${entry.patient_name}.` }, { status: 422 });
      }
      const source = await PDFDocument.load(await createClinicalReport(loaded.data));
      const pages = await merged.copyPages(source, source.getPageIndices());
      pages.forEach((page) => merged.addPage(page));
    }

    const bytes = await merged.save();
    return new NextResponse(Buffer.from(bytes), {
      headers: {
        "content-type": "application/pdf",
        "content-disposition": `inline; filename="informes-${date}.pdf"`,
        "cache-control": "private, no-store",
      },
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo preparar la impresion." }, { status: 500 });
  }
}
