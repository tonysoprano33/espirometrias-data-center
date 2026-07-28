import { NextResponse } from "next/server";
import { z } from "zod";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

const payloadSchema = z.object({ status: z.enum(["no_llego", "esperando", "atendido"]) });

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "secretaria", "espirometrista"]);
    const parsed = payloadSchema.safeParse(await request.json());
    if (!parsed.success) return NextResponse.json({ error: "Estado invalido." }, { status: 400 });
    const { id } = await params;
    const supabase = await createClient();
    const { error } = await supabase.rpc("set_encounter_attendance", { p_encounter_id: id, p_status: parsed.data.status });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo guardar." }, { status: 500 });
  }
}
