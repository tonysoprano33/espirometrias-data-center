import { NextResponse } from "next/server";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

type AttachmentRow = {
  storage_bucket: string;
  object_path: string;
  original_name: string;
  mime_type: string;
};

function contentType(file: AttachmentRow) {
  if (file.mime_type) return file.mime_type;
  const lower = file.original_name.toLocaleLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".webp")) return "image/webp";
  return "image/jpeg";
}

function legacyUrl(objectPath: string) {
  const base = (process.env.LEGACY_MEDIA_BASE_URL || "https://espirometrias-data-center.vercel.app/media").replace(/\/$/, "");
  return `${base}/${objectPath.split("/").map(encodeURIComponent).join("/")}`;
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "espirometrista", "medico"]);
    const { id } = await params;
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("attachments")
      .select("storage_bucket, object_path, original_name, mime_type")
      .eq("id", id)
      .maybeSingle();
    if (error || !data) return NextResponse.json({ error: "El archivo no existe." }, { status: 404 });

    const file = data as AttachmentRow;
    const downloaded = await supabase.storage.from(file.storage_bucket || "attachments").download(file.object_path);
    let body: ArrayBuffer | null = null;
    let type = contentType(file);

    if (downloaded.data) {
      body = await downloaded.data.arrayBuffer();
      type = downloaded.data.type || type;
    } else {
      const legacy = await fetch(legacyUrl(file.object_path), { cache: "no-store" });
      if (legacy.ok) {
        body = await legacy.arrayBuffer();
        type = legacy.headers.get("content-type") || type;
      }
    }

    if (!body) {
      return NextResponse.json({
        error: downloaded.error?.message || "El archivo figura en la ficha, pero no está disponible en Storage.",
      }, { status: 404 });
    }

    return new NextResponse(body, {
      headers: {
        "content-type": type,
        "content-disposition": `inline; filename*=UTF-8''${encodeURIComponent(file.original_name)}`,
        "cache-control": "private, no-store, max-age=0",
        "x-content-type-options": "nosniff",
      },
    });
  } catch (error) {
    return NextResponse.json({
      error: error instanceof Error ? error.message : "No se pudo abrir el archivo.",
    }, { status: 500 });
  }
}
