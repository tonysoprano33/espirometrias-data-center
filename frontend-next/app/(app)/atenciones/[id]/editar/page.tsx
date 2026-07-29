import { notFound } from "next/navigation";

import { requireProfile } from "../../../../lib/auth/require-profile";
import { createClient } from "../../../../lib/supabase/server";

import { EncounterEditForm, type EncounterEditValues } from "./encounter-edit-form";

type Relation<T> = T | T[] | null;
function first<T>(relation: Relation<T>) {
  return Array.isArray(relation) ? (relation[0] ?? null) : relation;
}

export default async function EncounterEditPage({ params }: { params: Promise<{ id: string }> }) {
  await requireProfile(["admin", "espirometrista"]);
  const { id } = await params;
  const supabase = await createClient();

  const [{ data: encounter }, { data: physicianRows }] = await Promise.all([
    supabase
      .from("encounters")
      .select(`
        id, encounter_time, study_type, coverage_type, coverage_name,
        medical_control_today, attendance_status,
        patients!inner(full_name, dni),
        referring_physicians(id, full_name),
        vital_signs(so2_rest, fc_rest, so2_post, fc_post),
        walk_tests(distance_meters, completed, stopped, symptoms, borg_final),
        spirometry_results(final_code, bronchodilator_positive)
      `)
      .eq("id", id)
      .is("deleted_at", null)
      .maybeSingle(),
    supabase.from("agenda_physicians_v1").select("physician_id, full_name").order("full_name"),
  ]);

  if (!encounter) notFound();
  const patient = first(encounter.patients);
  if (!patient) notFound();
  const physician = first(encounter.referring_physicians);
  const vitals = first(encounter.vital_signs);
  const walk = first(encounter.walk_tests);
  const spirometry = first(encounter.spirometry_results);

  const initialValues: EncounterEditValues = {
    fullName: patient.full_name,
    dni: patient.dni ?? "",
    encounterTime: encounter.encounter_time?.slice(0, 5) ?? "",
    studyType: encounter.study_type,
    coverageType: encounter.coverage_type,
    coverageName: encounter.coverage_name ?? "",
    referringPhysicianName: physician?.full_name ?? "",
    medicalControlToday: encounter.medical_control_today,
    attendanceStatus: encounter.attendance_status,
    so2Rest: vitals?.so2_rest ?? null,
    fcRest: vitals?.fc_rest ?? null,
    so2Post: vitals?.so2_post ?? null,
    fcPost: vitals?.fc_post ?? null,
    distanceMeters: walk?.distance_meters ?? 200,
    completed: walk?.completed ?? true,
    stopped: walk?.stopped ?? false,
    symptoms: walk?.symptoms ?? false,
    borgFinal: walk?.borg_final ?? 1,
    resultCode: spirometry?.final_code ?? "",
    bronchodilatorPositive: spirometry?.bronchodilator_positive ?? false,
  };

  return (
    <EncounterEditForm
      encounterId={encounter.id}
      initialValues={initialValues}
      physicians={(physicianRows ?? []).map((item) => ({
        id: item.physician_id,
        fullName: item.full_name,
      }))}
    />
  );
}
