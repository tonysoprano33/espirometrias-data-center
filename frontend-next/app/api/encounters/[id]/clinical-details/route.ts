import { NextResponse } from "next/server";
import { z } from "zod";

import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

const optionalInteger = (minimum: number, maximum: number) =>
  z.preprocess(
    (value) => (value === "" || value === null || value === undefined ? null : Number(value)),
    z.number().int().min(minimum).max(maximum).nullable(),
  );

const resultCodeSchema = z.enum([
  "",
  "N", "OL", "OM", "OMS", "OS", "RL", "RM", "RMS", "RS",
  "RLOL", "RLOM", "RLOMS", "RLOS", "RMOL", "RMOM", "RMOMS", "RMOS",
  "RMSOL", "RMSOM", "RMSOMS", "RMSOS", "RSOL", "RSOM", "RSOMS", "RSOS",
]);

const bodySchema = z.object({
  fullName: z.string().trim().min(2).max(160),
  dni: z.string().trim().max(20).default(""),
  encounterTime: z.string().trim().regex(/^$|^\d{2}:\d{2}$/),
  studyType: z.enum(["Ciclometria", "Espirometria"]),
  coverageType: z.enum(["Particular", "Mutual"]),
  coverageName: z.string().trim().max(120).default(""),
  referringPhysicianId: z.string().uuid().nullable(),
  medicalControlToday: z.boolean(),
  attendanceStatus: z.enum(["no_llego", "esperando", "atendido"]),
  so2Rest: optionalInteger(50, 100),
  fcRest: optionalInteger(20, 250),
  so2Post: optionalInteger(50, 100),
  fcPost: optionalInteger(20, 250),
  distanceMeters: z.coerce.number().int().min(0).max(10000),
  completed: z.boolean(),
  stopped: z.boolean(),
  symptoms: z.boolean(),
  borgFinal: z.coerce.number().int().min(0).max(10),
  resultCode: resultCodeSchema,
  bronchodilatorPositive: z.boolean(),
});

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const { id } = await context.params;
    const encounterId = z.string().uuid().parse(id);
    const body = bodySchema.parse(await request.json());
    const supabase = await createClient();

    const { error } = await supabase.rpc("save_encounter_clinical_details", {
      p_encounter_id: encounterId,
      p_full_name: body.fullName,
      p_dni: body.dni,
      p_encounter_time: body.encounterTime || null,
      p_study_type: body.studyType,
      p_coverage_type: body.coverageType,
      p_coverage_name: body.coverageName,
      p_referring_physician_id: body.referringPhysicianId,
      p_medical_control_today: body.medicalControlToday,
      p_attendance_status: body.attendanceStatus,
      p_so2_rest: body.so2Rest,
      p_fc_rest: body.fcRest,
      p_so2_post: body.so2Post,
      p_fc_post: body.fcPost,
      p_distance_meters: body.distanceMeters,
      p_completed: body.completed,
      p_stopped: body.stopped,
      p_symptoms: body.symptoms,
      p_borg_final: body.borgFinal,
      p_result_code: body.resultCode,
      p_bronchodilator_positive: body.bronchodilatorPositive,
    });

    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "No se pudo guardar la atencion." },
      { status: 400 },
    );
  }
}
