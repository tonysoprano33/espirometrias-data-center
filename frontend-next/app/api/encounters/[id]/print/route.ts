import { NextResponse } from "next/server";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const { id } = await params;
    const supabase = await createClient();
    const { data: files, error } = await supabase.from("attachments").select("storage_bucket, object_path, file_kind, created_at").eq("encounter_id", id).in("file_kind", ["informe_pdf", "pdf_resultado"]).order("created_at", { ascending: false });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    const file = (files ?? []).sort((a, b) => {
      if (a.file_kind !== b.file_kind) return a.file_kind === "informe_pdf" ? -1 : 1;
      return String(b.created_at ?? "").localeCompare(String(a.created_at ?? ""));
    })[0];
    if (!file) return NextResponse.json({ error: "Este paciente todavia no tiene un PDF para imprimir." }, { status: 404 });
    const { data, error: signedError } = await supabase.storage.from(file.storage_bucket).createSignedUrl(file.object_path, 600);
    if (signedError || !data?.signedUrl) return NextResponse.json({ error: "No se pudo abrir el PDF." }, { status: 404 });
    return NextResponse.redirect(data.signedUrl);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo imprimir." }, { status: 500 });
  }
}
