import { NextResponse } from "next/server";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const { id } = await params;
    const payload = await request.json();
    const body = typeof payload?.body === "string" ? payload.body.trim() : "";
    if (!body) return NextResponse.json({ error: "Escribí una nota antes de guardar." }, { status: 400 });
    if (body.length > 2000) return NextResponse.json({ error: "La nota no puede superar 2000 caracteres." }, { status: 400 });
    const supabase = await createClient();
    const { error } = await supabase.rpc("save_clinical_note", { p_encounter_id: id, p_body: body });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo guardar la nota." }, { status: 500 });
  }
}
