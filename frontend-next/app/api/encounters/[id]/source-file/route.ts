import { NextResponse } from "next/server";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

const MAX_BYTES = 20 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(["pdf", "jpg", "jpeg", "png", "webp"]);

function extensionOf(name: string) {
  return name.toLowerCase().split(".").pop() ?? "";
}

function contentTypeFor(extension: string, browserType: string) {
  if (extension === "pdf") return "application/pdf";
  if (extension === "jpg" || extension === "jpeg") return "image/jpeg";
  if (extension === "png") return "image/png";
  if (extension === "webp") return "image/webp";
  return browserType;
}

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
    const extension = extensionOf(file.name);
    if (!ALLOWED_EXTENSIONS.has(extension)) return NextResponse.json({ error: "Solo se aceptan archivos PDF, JPG, PNG o WEBP." }, { status: 415 });
    if (file.size > MAX_BYTES) return NextResponse.json({ error: "El archivo no puede superar 20 MB." }, { status: 413 });
    const contentType = contentTypeFor(extension, file.type);
    // Windows browsers sometimes report a PDF as octet-stream or with no MIME.
    // Validate the extension and the PDF signature instead of rejecting a valid file.
    if (extension === "pdf") {
      const header = new TextDecoder().decode(await file.slice(0, 5).arrayBuffer());
      if (header !== "%PDF-") return NextResponse.json({ error: "El archivo tiene extensión PDF, pero no parece ser un PDF válido." }, { status: 415 });
    }

    const supabase = await createClient();
    const safeName = safeFileName(file.name);
    const objectPath = `${id}/${crypto.randomUUID()}-${safeName}`;
    const { error: uploadError } = await supabase.storage.from("attachments").upload(objectPath, file, { contentType, upsert: false });
    if (uploadError) {
      const detail = /row-level security|not authorized|permission/i.test(uploadError.message)
        ? "Storage todavía no está habilitado para este proyecto. Aplicá la migración 20260728_0010_storage_attachments.sql en Supabase."
        : uploadError.message;
      return NextResponse.json({ error: `No se pudo subir el archivo: ${detail}` }, { status: 400 });
    }

    const { error: recordError } = await supabase.from("attachments").insert({
      encounter_id: id,
      file_kind: extension === "pdf" ? "pdf_resultado" : "foto_resultado",
      storage_bucket: "attachments",
      object_path: objectPath,
      original_name: file.name,
      safe_name: safeName,
      mime_type: contentType,
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
