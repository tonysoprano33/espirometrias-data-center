import { NextResponse } from "next/server";
import { z } from "zod";
import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

const updateSchema = z.object({
  action: z.literal("update"),
  fullName: z.string().trim().min(2).max(180),
  dni: z.string().trim().max(20),
  encounterTime: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/).or(z.literal("")),
  studyType: z.enum(["Ciclometria", "Espirometria"]),
  coverageType: z.enum(["Mutual", "Particular"]),
  coverageName: z.string().trim().max(120).default(""),
  referringPhysicianId: z.string().uuid().nullable(),
  medicalControlToday: z.boolean().default(false),
});

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "secretaria", "espirometrista"]);
    const parsed = updateSchema.safeParse(await request.json());
    if (!parsed.success) {
      return NextResponse.json({ error: "Revisa los datos del paciente y la atencion." }, { status: 400 });
    }
    const { id } = await params;
    const supabase = await createClient();
    const { error } = await supabase.rpc("update_agenda_encounter_full", {
      p_encounter_id: id,
      p_full_name: parsed.data.fullName,
      p_dni: parsed.data.dni || null,
      p_encounter_time: parsed.data.encounterTime || null,
      p_study_type: parsed.data.studyType,
      p_coverage_type: parsed.data.coverageType,
      p_coverage_name: parsed.data.coverageName,
      p_referring_physician_id: parsed.data.referringPhysicianId,
      p_medical_control_today: parsed.data.medicalControlToday,
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo editar." }, { status: 500 });
  }
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const { id } = await params;
    const supabase = await createClient();
    const { error } = await supabase.rpc("soft_delete_encounter", { p_encounter_id: id });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo eliminar." }, { status: 500 });
  }
}
