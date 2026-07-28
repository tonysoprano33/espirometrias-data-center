import { PDFDocument } from "pdf-lib";
import { NextResponse } from "next/server";
import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";

type AgendaEntry = { encounter_id: string };
type Attachment = { encounter_id: string; storage_bucket: string; object_path: string; file_kind: string; created_at: string };

export async function GET(request: Request) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const date = new URL(request.url).searchParams.get("date") ?? new Date().toISOString().slice(0, 10);
    const supabase = await createClient();
    const { data: entries, error: agendaError } = await supabase.rpc("secretary_agenda_entries", { target_date: date });
    if (agendaError) return NextResponse.json({ error: agendaError.message }, { status: 400 });

    const ids = ((entries ?? []) as AgendaEntry[]).map((entry) => entry.encounter_id);
    if (ids.length === 0) return NextResponse.json({ error: "No hay pacientes en esta fecha." }, { status: 404 });

    const { data: attachments, error: attachmentError } = await supabase
      .from("attachments")
      .select("encounter_id, storage_bucket, object_path, file_kind, created_at")
      .in("encounter_id", ids)
      .in("file_kind", ["informe_pdf", "pdf_resultado"])
      .order("created_at", { ascending: false });
    if (attachmentError) return NextResponse.json({ error: attachmentError.message }, { status: 400 });

    const latestByEncounter = new Map<string, Attachment>();
    for (const attachment of (attachments ?? []) as Attachment[]) {
      if (!latestByEncounter.has(attachment.encounter_id)) latestByEncounter.set(attachment.encounter_id, attachment);
    }

    const merged = await PDFDocument.create();
    let included = 0;
    for (const entry of (entries ?? []) as AgendaEntry[]) {
      const attachment = latestByEncounter.get(entry.encounter_id);
      if (!attachment) continue;
      const { data: file, error: downloadError } = await supabase.storage.from(attachment.storage_bucket).download(attachment.object_path);
      if (downloadError || !file) continue;
      try {
        const source = await PDFDocument.load(await file.arrayBuffer());
        const pages = await merged.copyPages(source, source.getPageIndices());
        pages.forEach((page) => merged.addPage(page));
        included += 1;
      } catch {
        // A damaged or non-PDF attachment must not block the other reports.
      }
    }

    if (!included) return NextResponse.json({ error: "No hay informes PDF listos para imprimir en esta fecha." }, { status: 404 });
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
