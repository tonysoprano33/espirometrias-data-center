import { NextResponse } from "next/server";
import { z } from "zod";
import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";

const schema = z.object({ fullName: z.string().trim().min(4).max(180) });

export async function POST(request: Request) {
  try {
    await requireProfile(["admin", "secretaria", "espirometrista"]);
    const parsed = schema.safeParse(await request.json());
    if (!parsed.success) {
      return NextResponse.json({ error: "Escribi el nombre completo del medico." }, { status: 400 });
    }
    const supabase = await createClient();
    const { data, error } = await supabase.rpc("upsert_agenda_physician", { p_full_name: parsed.data.fullName });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    const row = Array.isArray(data) ? data[0] : null;
    if (!row) return NextResponse.json({ error: "No se pudo recuperar el medico." }, { status: 500 });
    return NextResponse.json({
      physician: {
        physician_id: row.physician_id,
        full_name: row.full_name,
        is_default: false,
      },
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo agregar el medico." }, { status: 500 });
  }
}
