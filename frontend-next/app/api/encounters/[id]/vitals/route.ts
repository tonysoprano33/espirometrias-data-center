import { NextResponse } from "next/server";
import { z } from "zod";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

const payloadSchema = z.object({
  stage: z.enum(["rest", "post"]),
  so2: z.coerce.number().int().min(0).max(100),
  fc: z.coerce.number().int().min(0).max(300),
});

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const parsed = payloadSchema.safeParse(await request.json());
    if (!parsed.success) {
      return NextResponse.json({ error: "Completa valores validos para SO2 y FC." }, { status: 400 });
    }
    const { id } = await params;
    const supabase = await createClient();
    const { error } = await supabase.rpc("save_encounter_vitals", {
      p_encounter_id: id,
      p_stage: parsed.data.stage,
      p_so2: parsed.data.so2,
      p_fc: parsed.data.fc,
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo guardar." }, { status: 500 });
  }
}
