import type { SupabaseClient } from "@supabase/supabase-js";
import type { ReportData } from "./clinical-report";

export type ReportAttachment = {
  id: string;
  originalName: string;
  fileKind: "pdf_resultado" | "foto_resultado";
  mimeType: string;
};

type SpirometryResultRow = {
  final_code: string | null;
  respiratory_pattern: string | null;
  obstruction_grade: string | null;
  restriction_grade: string | null;
  bronchodilator_positive: boolean;
};

type EncounterRow = {
  encounter_date: string;
  encounter_time: string | null;
  attendance_status: string;
  study_type: "Ciclometria" | "Espirometria";
  coverage_type: "Mutual" | "Particular";
  coverage_name: string;
  patients: { full_name: string; dni: string | null } | Array<{ full_name: string; dni: string | null }>;
  referring_physicians: { full_name: string } | Array<{ full_name: string }> | null;
  vital_signs: { so2_rest: number | null; fc_rest: number | null; so2_post: number | null; fc_post: number | null } | Array<{ so2_rest: number | null; fc_rest: number | null; so2_post: number | null; fc_post: number | null }> | null;
  walk_tests: { distance_meters: number; completed: boolean; stopped: boolean; symptoms: boolean; borg_final: number; minute_readings: unknown } | Array<{ distance_meters: number; completed: boolean; stopped: boolean; symptoms: boolean; borg_final: number; minute_readings: unknown }> | null;
  spirometry_results: SpirometryResultRow | SpirometryResultRow[] | null;
  attachments: Array<{ id: string; original_name: string; file_kind: "pdf_resultado" | "foto_resultado"; mime_type: string; created_at: string }>;
};

function one<T>(value: T | T[] | null): T | null {
  return Array.isArray(value) ? value[0] ?? null : value;
}

function minuteReadings(value: unknown): ReportData["walkMinuteReadings"] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object")
    .map((entry) => ({
      minute: Number(entry.minute),
      so2: entry.so2 == null || entry.so2 === "" ? null : Number(entry.so2),
      fc: entry.fc == null || entry.fc === "" ? null : Number(entry.fc),
      borg: entry.borg == null || entry.borg === "" ? null : Number(entry.borg),
    }))
    .filter((entry) => Number.isInteger(entry.minute) && entry.minute >= 0 && entry.minute <= 6);
}

function resultCodeFromClinicalFields(result: SpirometryResultRow) {
  const storedCode = result.final_code?.trim().toUpperCase();
  if (storedCode) return storedCode;

  const obstructionCodes: Record<string, string> = {
    leve: "OL",
    moderada: "OM",
    moderado: "OM",
    "moderadamente severa": "OMS",
    severa: "OS",
    severo: "OS",
  };
  const restrictionCodes: Record<string, string> = {
    leve: "RL",
    moderada: "RM",
    moderado: "RM",
    "moderadamente severa": "RMS",
    severa: "RS",
    severo: "RS",
  };
  const pattern = result.respiratory_pattern?.trim().toLocaleLowerCase("es-AR");
  const obstruction = obstructionCodes[result.obstruction_grade?.trim().toLocaleLowerCase("es-AR") ?? ""];
  const restriction = restrictionCodes[result.restriction_grade?.trim().toLocaleLowerCase("es-AR") ?? ""];

  if (pattern === "normal") return "N";
  if (pattern === "obstructivo") return obstruction ?? "";
  if (pattern === "restrictivo") return restriction ?? "";
  if (pattern === "mixto") return restriction && obstruction ? `${restriction}${obstruction}` : "MIXTO";
  return "";
}

export async function loadReportData(
  supabase: SupabaseClient,
  encounterId: string,
): Promise<{ data?: ReportData; sourceAttachment?: ReportAttachment; missing?: string[]; error?: string }> {
  const { data: raw, error } = await supabase
    .from("encounters")
    .select("encounter_date, encounter_time, attendance_status, study_type, coverage_type, coverage_name, patients!inner(full_name, dni), referring_physicians(full_name), vital_signs(so2_rest, fc_rest, so2_post, fc_post), walk_tests(distance_meters, completed, stopped, symptoms, borg_final, minute_readings), spirometry_results(final_code, respiratory_pattern, obstruction_grade, restriction_grade, bronchodilator_positive), attachments(id, original_name, file_kind, mime_type, created_at)")
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
  if (!result?.final_code?.trim() && !result?.respiratory_pattern?.trim()) missing.push("resultado");
  if (missing.length) return { missing };
  const resultCode = resultCodeFromClinicalFields(result!);

  const source = [...(row.attachments ?? [])]
    .filter((attachment) => attachment.file_kind === "pdf_resultado" || attachment.file_kind === "foto_resultado")
    .sort((left, right) => right.created_at.localeCompare(left.created_at))[0];

  return {
    data: {
      date: row.encounter_date,
      time: row.encounter_time,
      attendanceStatus: row.attendance_status,
      patientName: patient!.full_name,
      dni: patient!.dni!,
      physicianName: physician?.full_name || "Dr. Gustavo Piguillem",
      studyType: row.study_type,
      coverageType: row.coverage_type,
      coverageName: row.coverage_name,
      so2Rest: vitals?.so2_rest ?? null,
      fcRest: vitals?.fc_rest ?? null,
      so2Post: vitals?.so2_post ?? null,
      fcPost: vitals?.fc_post ?? null,
      hasVitals: Boolean(vitals),
      hasWalk: Boolean(walk),
      resultCode,
      respiratoryPattern: result!.respiratory_pattern ?? "",
      obstructionGrade: result!.obstruction_grade ?? "",
      restrictionGrade: result!.restriction_grade ?? "",
      bronchodilatorPositive: result!.bronchodilator_positive,
      distanceMeters: walk?.distance_meters ?? 200,
      walkCompleted: walk?.completed ?? true,
      walkStopped: walk?.stopped ?? false,
      walkSymptoms: walk?.symptoms ?? false,
      borgFinal: walk?.borg_final ?? 1,
      walkMinuteReadings: minuteReadings(walk?.minute_readings),
    },
    sourceAttachment: source ? {
      id: source.id,
      originalName: source.original_name,
      fileKind: source.file_kind,
      mimeType: source.mime_type,
    } : undefined,
  };
}
