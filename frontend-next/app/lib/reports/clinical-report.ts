export type WalkMinuteReading = {
  minute: number;
  so2: number | null;
  fc: number | null;
  borg: number | null;
};

export type ReportData = {
  date: string;
  time: string | null;
  attendanceStatus: string;
  patientName: string;
  dni: string;
  physicianName: string;
  studyType: "Ciclometria" | "Espirometria";
  coverageType: "Mutual" | "Particular";
  coverageName: string;
  so2Rest: number | null;
  fcRest: number | null;
  so2Post: number | null;
  fcPost: number | null;
  hasVitals: boolean;
  hasWalk: boolean;
  resultCode: string;
  respiratoryPattern: string;
  obstructionGrade: string;
  restrictionGrade: string;
  bronchodilatorPositive: boolean;
  distanceMeters: number;
  walkCompleted: boolean;
  walkStopped: boolean;
  walkSymptoms: boolean;
  borgFinal: number;
  walkMinuteReadings: WalkMinuteReading[];
};

export type WalkReportRow = {
  minute: number;
  so2: number | "";
  fc: number | "";
  borg: number | "";
};

const obstructionLabels: Record<string, string> = {
  OL: "leve",
  OM: "moderada",
  OMS: "moderadamente severa",
  OS: "severa",
};

const restrictionLabels: Record<string, string> = {
  RL: "leve",
  RM: "moderada",
  RMS: "moderadamente severa",
  RS: "severa",
};

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizedPattern(value: unknown) {
  const clean = cleanText(value).toLocaleLowerCase("es-AR");
  if (clean === "normal") return "Normal";
  if (clean === "obstructivo") return "Obstructivo";
  if (clean === "restrictivo") return "Restrictivo";
  if (clean === "mixto") return "Mixto";
  return "";
}

function parseCode(codeValue: unknown) {
  const code = cleanText(codeValue).toUpperCase().replace(/\s+/g, "");
  if (code === "N") return { pattern: "Normal", obstruction: "", restriction: "" };
  if (obstructionLabels[code]) return { pattern: "Obstructivo", obstruction: obstructionLabels[code], restriction: "" };
  if (restrictionLabels[code]) return { pattern: "Restrictivo", obstruction: "", restriction: restrictionLabels[code] };

  const restrictionCode = ["RMS", "RS", "RM", "RL"].find((candidate) => code.startsWith(candidate));
  const obstructionCode = restrictionCode ? code.slice(restrictionCode.length) : "";
  if (restrictionCode && obstructionLabels[obstructionCode]) {
    return {
      pattern: "Mixto",
      obstruction: obstructionLabels[obstructionCode],
      restriction: restrictionLabels[restrictionCode],
    };
  }
  return { pattern: "", obstruction: "", restriction: "" };
}

function capitalized(value: unknown) {
  const clean = cleanText(value).toLocaleLowerCase("es-AR");
  return clean ? `${clean.charAt(0).toLocaleUpperCase("es-AR")}${clean.slice(1)}` : "";
}

export function reportText(data: ReportData) {
  const fromCode = parseCode(data.resultCode);
  const pattern = normalizedPattern(data.respiratoryPattern) || fromCode.pattern || "Normal";
  const obstruction = cleanText(data.obstructionGrade).toLocaleLowerCase("es-AR") || fromCode.obstruction || "leve";
  const restriction = cleanText(data.restrictionGrade).toLocaleLowerCase("es-AR") || fromCode.restriction || "leve";

  if (pattern === "Normal") return "El paciente presenta resultados normales.";
  if (pattern === "Obstructivo") {
    return `El paciente presenta déficit respiratorio (obstrucción ${obstruction}) a las pequeñas vías respiratorias aéreas.`;
  }
  if (pattern === "Restrictivo") {
    return `El paciente presenta déficit respiratorio (restricción ${restriction}) a las vías respiratorias aéreas.`;
  }
  return [
    "El paciente presenta déficit respiratorio con patrón mixto:",
    ` Restricción ${capitalized(restriction)}.`,
    ` Obstrucción ${capitalized(obstruction)} a las pequeñas vías respiratorias aéreas.`,
  ].join("\n");
}

export function isNormalResult(data: ReportData) {
  return (normalizedPattern(data.respiratoryPattern) || parseCode(data.resultCode).pattern) === "Normal";
}

export function formatReportDate(value: string) {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

export function formatReportDni(value: string) {
  const digits = value.replace(/\D/g, "");
  if (!digits) return "0";
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export function normalizeDoctor(value: string) {
  const clean = (cleanText(value) || "DR. GUSTAVO PIGUILLEM").replace(/\s+/g, " ").toLocaleUpperCase("es-AR");
  const female = /^DRA\.?\s+/i.test(clean) || /^DR\.\s*A\.?\s+/i.test(clean);
  const withoutPrefix = clean
    .replace(/^DRA\.?\s+/i, "")
    .replace(/^DR\.\s*A\.?\s+/i, "")
    .replace(/^DR\.?\s+/i, "")
    .trim();
  return `${female ? "DRA." : "DR."} ${withoutPrefix || "GUSTAVO PIGUILLEM"}`;
}

function validated(value: unknown, minimum: number, maximum: number): number | "" {
  if (value == null || value === "") return "";
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) return "";
  return parsed;
}

function interpolate(startValue: number | null, endValue: number | null, minute: number, maximum: number): number | "" {
  const start = validated(startValue, 0, maximum);
  const end = validated(endValue, 0, maximum);
  if (start === "" && end === "") return "";
  if (start === "") return end;
  if (end === "") return start;
  return Math.min(Math.round(start + ((end - start) * minute / 6)), maximum);
}

export function buildWalkRows(data: ReportData): WalkReportRow[] {
  const rows: WalkReportRow[] = Array.from({ length: 7 }, (_, minute) => ({ minute, so2: "", fc: "", borg: "" }));
  for (const reading of data.walkMinuteReadings) {
    if (!Number.isInteger(reading.minute) || reading.minute < 0 || reading.minute > 6) continue;
    rows[reading.minute].so2 = validated(reading.so2, 0, 100);
    rows[reading.minute].fc = validated(reading.fc, 0, 300);
    rows[reading.minute].borg = validated(reading.borg, 0, 10);
  }

  for (let minute = 0; minute <= 6; minute += 1) {
    if (rows[minute].so2 === "") rows[minute].so2 = interpolate(data.so2Rest, data.so2Post, minute, 100);
    if (rows[minute].fc === "") rows[minute].fc = interpolate(data.fcRest, data.fcPost, minute, 300);
  }

  const finalBorg = validated(data.borgFinal || 1, 0, 10);
  if (finalBorg !== "") {
    for (let minute = 0; minute <= 6; minute += 1) {
      if (rows[minute].borg === "") rows[minute].borg = Math.min(Math.floor(finalBorg * minute / 6), 10);
    }
  }
  return rows;
}

export function walkAssessment(data: ReportData) {
  const drop = data.so2Rest == null || data.so2Post == null ? null : data.so2Rest - data.so2Post;
  const abnormal = (
    (data.so2Post != null && data.so2Post <= 88)
    || (drop != null && drop >= 4)
    || !data.walkCompleted
    || data.walkStopped
    || data.walkSymptoms
  );
  return abnormal ? "PRUEBA NO NORMAL" : "PRUEBA NORMAL";
}

export function mutualCvlResult(data: ReportData) {
  const fromCode = parseCode(data.resultCode);
  const pattern = normalizedPattern(data.respiratoryPattern) || fromCode.pattern || "Normal";
  const obstruction = cleanText(data.obstructionGrade).toLocaleLowerCase("es-AR") || fromCode.obstruction;
  const restriction = cleanText(data.restrictionGrade).toLocaleLowerCase("es-AR") || fromCode.restriction;
  if (pattern === "Normal") return "Normal";
  if (pattern === "Obstructivo") {
    if (obstruction === "leve") return "Levemente disminuida";
    if (obstruction === "moderado" || obstruction === "moderada") return "Moderadamente disminuida";
    if (obstruction === "moderadamente severa") return "Moderadamente a severamente disminuida";
    return "Severamente disminuida";
  }
  if (pattern === "Restrictivo") {
    if (restriction === "leve") return "Levemente reducida";
    if (restriction === "moderado" || restriction === "moderada") return "Moderadamente reducida";
    if (restriction === "moderadamente severa") return "Moderadamente a severamente reducida";
    return "Severamente reducida";
  }
  return "Reducida (patrón mixto)";
}
