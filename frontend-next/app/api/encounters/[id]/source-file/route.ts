import { NextResponse } from "next/server";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

const MAX_BYTES = 20 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["application/pdf", "image/jpeg", "image/png", "image/webp"]);

function safeFileName(name: string) {
  const normalized = name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  return normalized.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(-120) || "resultado";
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const { id } = await params;
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof File)) return NextResponse.json({ error: "Elegí un PDF o una imagen." }, { status: 400 });
    if (!ALLOWED_TYPES.has(file.type)) return NextResponse.json({ error: "Solo se aceptan PDF, JPG, PNG o WEBP." }, { status: 415 });
    if (file.size > MAX_BYTES) return NextResponse.json({ error: "El archivo no puede superar 20 MB." }, { status: 413 });

    const supabase = await createClient();
    const safeName = safeFileName(file.name);
    const objectPath = `${id}/${crypto.randomUUID()}-${safeName}`;
    const { error: uploadError } = await supabase.storage.from("attachments").upload(objectPath, file, { contentType: file.type, upsert: false });
    if (uploadError) return NextResponse.json({ error: `No se pudo subir el archivo: ${uploadError.message}` }, { status: 400 });

    const { error: recordError } = await supabase.from("attachments").insert({
      encounter_id: id,
      file_kind: file.type === "application/pdf" ? "pdf_resultado" : "foto_resultado",
      storage_bucket: "attachments",
      object_path: objectPath,
      original_name: file.name,
      safe_name: safeName,
      mime_type: file.type,
      byte_size: file.size,
      analysis_status: "uploaded",
    });
    if (recordError) {
      await supabase.storage.from("attachments").remove([objectPath]);
      return NextResponse.json({ error: `El archivo se subio pero no se pudo registrar: ${recordError.message}` }, { status: 400 });
    }
    return NextResponse.json({ ok: true, message: "Archivo cargado correctamente." });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo cargar el archivo." }, { status: 500 });
  }
}
