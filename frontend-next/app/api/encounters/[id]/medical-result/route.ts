import { NextResponse } from "next/server";
import { z } from "zod";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

const schema = z.object({ code: z.string().trim().min(1).max(8).regex(/^[A-Za-z]+$/), comment: z.string().max(4000).default("") });

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "medico"]);
    const parsed = schema.safeParse(await request.json());
    if (!parsed.success) return NextResponse.json({ error: "Escribi un codigo de resultado valido." }, { status: 400 });
    const { id } = await params;
    const supabase = await createClient();
    const { error } = await supabase.rpc("save_medical_result", { p_encounter_id: id, p_final_code: parsed.data.code, p_comment: parsed.data.comment });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo guardar el resultado." }, { status: 500 });
  }
}
