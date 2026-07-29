import { NextResponse } from "next/server";
import { z } from "zod";
import { requireProfile } from "../../../lib/auth/require-profile";
import { createClient } from "../../../lib/supabase/server";

const rowSchema = z.object({
  agendaDate: z.string().date(),
  time: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/),
  name: z.string().trim().min(2).max(180),
  dni: z.string().trim().max(20),
  studyType: z.enum(["Ciclometria", "Espirometria"]),
  coverageType: z.enum(["Particular", "Mutual"]),
  coverageName: z.string().trim().max(120),
});

const schema = z.object({
  rows: z.array(rowSchema).min(1).max(50),
  referringPhysicianId: z.string().uuid().nullable(),
});

function normalized(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9]/g, "").toLowerCase();
}

export async function POST(request: Request) {
  try {
    await requireProfile(["admin", "espirometrista"]);
    const parsed = schema.safeParse(await request.json());
    if (!parsed.success) return NextResponse.json({ error: "Revisa las filas detectadas antes de importar." }, { status: 400 });

    const supabase = await createClient();
    const dates = [...new Set(parsed.data.rows.map((row) => row.agendaDate))].sort();
    const existingByDate = new Map<string, Array<{ dni: string | null; patient_name: string }>>();
    for (const agendaDate of dates) {
      const { data: current, error: currentError } = await supabase.rpc("agenda_entries_v2", { target_date: agendaDate });
      if (currentError) return NextResponse.json({ error: currentError.message }, { status: 400 });
      existingByDate.set(agendaDate, (current ?? []) as Array<{ dni: string | null; patient_name: string }>);
    }

    let created = 0;
    let skipped = 0;
    const errors: string[] = [];

    for (const row of parsed.data.rows) {
      const dni = row.dni.replace(/\D/g, "");
      const existing = existingByDate.get(row.agendaDate) ?? [];
      const duplicate = existing.some((candidate) => {
        const existingDni = (candidate.dni ?? "").replace(/\D/g, "");
        if (dni && existingDni) return dni === existingDni;
        return normalized(row.name) === normalized(candidate.patient_name);
      });
      if (duplicate) {
        skipped += 1;
        continue;
      }

      const { error } = await supabase.rpc("create_agenda_encounter_v2", {
        p_full_name: row.name,
        p_dni: dni || null,
        p_encounter_date: row.agendaDate,
        p_encounter_time: row.time,
        p_study_type: row.studyType,
        p_coverage_type: row.coverageType,
        p_coverage_name: row.coverageType === "Mutual" ? row.coverageName || "Mutual" : "",
        p_medical_control_today: false,
        p_referring_physician_id: parsed.data.referringPhysicianId,
      });
      if (error) errors.push(`${row.time} ${row.name}: ${error.message}`);
      else {
        created += 1;
        existing.push({ dni, patient_name: row.name });
      }
    }

    return NextResponse.json({ ok: errors.length === 0, created, skipped, errors, dates });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "No se pudo importar Drapp." }, { status: 500 });
  }
}
