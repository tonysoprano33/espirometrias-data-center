export type AttendanceStatus = "no_llego" | "esperando" | "atendido";
export type StudyType = "Ciclometria" | "Espirometria";
export type CoverageType = "Mutual" | "Particular";

export type PhysicianOption = {
  physician_id: string;
  full_name: string;
  is_default: boolean;
};

export type AgendaEntry = {
  encounter_id: string;
  patient_id: string;
  encounter_date: string;
  encounter_time: string | null;
  patient_name: string;
  dni: string | null;
  study_type: StudyType;
  coverage_type: CoverageType;
  coverage_name: string;
  referring_physician_id: string | null;
  referring_physician_name: string;
  attendance_status: AttendanceStatus;
  workflow_status: string;
  medical_control_today: boolean;
  so2_rest: number | null;
  fc_rest: number | null;
  so2_post: number | null;
  fc_post: number | null;
  result_code: string;
  walk_distance_meters: number;
  walk_completed: boolean;
  walk_stopped: boolean;
  walk_symptoms: boolean;
  borg_final: number;
  bronchodilator_positive: boolean;
  can_print: boolean;
  missing_for_print: string;
};

export const resultCodes = [
  "N",
  "OL",
  "OM",
  "OMS",
  "OS",
  "RL",
  "RM",
  "RMS",
  "RS",
  "RLOL",
  "RLOM",
  "RLOMS",
  "RLOS",
  "RMOL",
  "RMOM",
  "RMOMS",
  "RMOS",
  "RMSOL",
  "RMSOM",
  "RMSOMS",
  "RMSOS",
  "RSOL",
  "RSOM",
  "RSOMS",
  "RSOS",
] as const;
