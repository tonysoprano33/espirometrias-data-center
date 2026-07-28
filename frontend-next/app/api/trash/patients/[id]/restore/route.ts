import { NextResponse } from "next/server";
import { requireProfile } from "../../../../../lib/auth/require-profile";
import { createClient } from "../../../../../lib/supabase/server";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const { id } = await params;
    const supabase = await createClient();
    const { error } = await supabase.rpc("restore_patient", { p_patient_id: id });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo restaurar el paciente." }, { status: 500 });
  }
}
