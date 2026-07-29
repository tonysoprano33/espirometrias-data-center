"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireProfile } from "../../lib/auth/require-profile";
import { createClient } from "../../lib/supabase/server";

export type CreateAgendaState = { ok: boolean; message: string };

const createAgendaSchema = z.object({
  fullName: z.string().trim().min(2, "Ingresa el nombre del paciente.").max(180),
  dni: z.string().trim().max(20),
  encounterDate: z.string().date(),
  encounterTime: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Ingresa una hora valida.").or(z.literal("")),
  studyType: z.enum(["Ciclometria", "Espirometria"]),
  coverageType: z.enum(["Particular", "Mutual"]),
  coverageName: z.string().trim().max(120),
  medicalControlToday: z.boolean(),
  referringPhysicianId: z.string().uuid().or(z.literal("")),
});

export async function createAgendaEntry(
  _previousState: CreateAgendaState,
  formData: FormData,
): Promise<CreateAgendaState> {
  await requireProfile(["admin", "secretaria", "espirometrista"]);
  const parsed = createAgendaSchema.safeParse({
    fullName: formData.get("fullName"),
    dni: formData.get("dni"),
    encounterDate: formData.get("encounterDate"),
    encounterTime: formData.get("encounterTime"),
    studyType: formData.get("studyType"),
    coverageType: formData.get("coverageType"),
    coverageName: formData.get("coverageName"),
    medicalControlToday: formData.get("medicalControlToday") === "on",
    referringPhysicianId: formData.get("referringPhysicianId") ?? "",
  });

  if (!parsed.success) {
    return { ok: false, message: parsed.error.issues[0]?.message || "Revisa los datos ingresados." };
  }

  const values = parsed.data;
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("create_agenda_encounter_v2", {
    p_full_name: values.fullName,
    p_dni: values.dni || null,
    p_encounter_date: values.encounterDate,
    p_encounter_time: values.encounterTime || null,
    p_study_type: values.studyType,
    p_coverage_type: values.coverageType,
    p_coverage_name: values.coverageType === "Mutual" ? values.coverageName || "Mutual" : "",
    p_medical_control_today: values.medicalControlToday,
    p_referring_physician_id: values.referringPhysicianId || null,
  });

  if (error) return { ok: false, message: error.message };
  revalidatePath("/agenda");
  const reused = Array.isArray(data) && data[0]?.reused_patient;
  return {
    ok: true,
    message: reused
      ? "Nueva visita guardada en la historia existente por DNI."
      : "Paciente y atencion guardados.",
  };
}
