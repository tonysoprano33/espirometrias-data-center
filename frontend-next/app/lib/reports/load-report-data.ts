import type { SupabaseClient } from "@supabase/supabase-js";
import type { ReportData } from "./clinical-report";

type EncounterRow = {
  encounter_date: string;
  study_type: "Ciclometria" | "Espirometria";
  coverage_type: "Mutual" | "Particular";
  coverage_name: string;
  patients: { full_name: string; dni: string | null } | Array<{ full_name: string; dni: string | null }>;
  referring_physicians: { full_name: string } | Array<{ full_name: string }> | null;
  vital_signs: { so2_rest: number | null; fc_rest: number | null; so2_post: number | null; fc_post: number | null } | Array<{ so2_rest: number | null; fc_rest: number | null; so2_post: number | null; fc_post: number | null }> | null;
  walk_tests: { distance_meters: number; completed: boolean; stopped: boolean; symptoms: boolean; borg_final: number } | Array<{ distance_meters: number; completed: boolean; stopped: boolean; symptoms: boolean; borg_final: number }> | null;
  spirometry_results: { final_code: string; bronchodilator_positive: boolean } | Array<{ final_code: string; bronchodilator_positive: boolean }> | null;
};

function one<T>(value: T | T[] | null): T | null {
  return Array.isArray(value) ? value[0] ?? null : value;
}

export async function loadReportData(supabase: SupabaseClient, encounterId: string): Promise<{ data?: ReportData; missing?: string[]; error?: string }> {
  const { data: raw, error } = await supabase
    .from("encounters")
    .select("encounter_date, study_type, coverage_type, coverage_name, patients!inner(full_name, dni), referring_physicians(full_name), vital_signs(so2_rest, fc_rest, so2_post, fc_post), walk_tests(distance_meters, completed, stopped, symptoms, borg_final), spirometry_results(final_code, bronchodilator_positive)")
    .eq("id", encounterId)
    .is("deleted_at", null)
    .maybeSingle();
  if (error) return { error: error.message };
  if (!raw) return { error: "La atencion no existe." };

  const row = raw as unknown as EncounterRow;
  const patient = one(row.patients);
  const physician = one(row.referring_physicians);
  const vitals = one(row.vital_signs);
  const walk = one(row.walk_tests);
  const result = one(row.spirometry_results);
  const missing: string[] = [];
  if (!patient?.full_name?.trim()) missing.push("nombre");
  if (!patient?.dni?.replace(/\D/g, "")) missing.push("DNI");
  if (vitals?.so2_rest == null) missing.push("SO2 reposo");
  if (vitals?.fc_rest == null) missing.push("FC reposo");
  if (vitals?.so2_post == null) missing.push("SO2 post");
  if (vitals?.fc_post == null) missing.push("FC post");
  if (!result?.final_code?.trim()) missing.push("resultado");
  if (missing.length) return { missing };

  return {
    data: {
      date: row.encounter_date,
      patientName: patient!.full_name,
      dni: patient!.dni!,
      physicianName: physician?.full_name || "Dr. Gustavo Piguillem",
      studyType: row.study_type,
      coverageType: row.coverage_type,
      coverageName: row.coverage_name,
      so2Rest: vitals!.so2_rest!,
      fcRest: vitals!.fc_rest!,
      so2Post: vitals!.so2_post!,
      fcPost: vitals!.fc_post!,
      resultCode: result!.final_code,
      bronchodilatorPositive: result!.bronchodilator_positive,
      distanceMeters: walk?.distance_meters ?? 200,
      walkCompleted: walk?.completed ?? true,
      walkStopped: walk?.stopped ?? false,
      walkSymptoms: walk?.symptoms ?? false,
      borgFinal: walk?.borg_final ?? 1,
    },
  };
}
