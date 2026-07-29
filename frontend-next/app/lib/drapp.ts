export type DrappRow = {
  time: string;
  name: string;
  dni: string;
  studyType: "Ciclometria" | "Espirometria";
  coverageType: "Particular" | "Mutual";
  coverageName: string;
};

const coverageMatchers = [
  "PAMI",
  "DOSEP",
  "GRASSI",
  "OSDE",
  "SWISS MEDICAL",
  "GALENO",
  "MEDIFE",
  "SANCOR",
  "APROSS",
  "IOSFA",
  "OSPIP",
  "OSPACA",
];

function cleanName(value: string) {
  return value
    .replace(/\b(?:hace\s+\d+\s+(?:horas?|dias?|minutos?)|reservado|link\s+de\s+pago)\b/gi, " ")
    .replace(/^\s*[o0]\s+(?=[A-ZÁÉÍÓÚÑ])/i, "")
    .replace(/\b(?:espirometria|cicloespirometria|ciclometria)\b.*$/i, "")
    .replace(/[|_]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+|[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+$/g, "")
    .trim();
}

function normalizeNameForValidation(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
}

function coverageFromBlock(block: string) {
  if (/\bPARTICULAR\b/i.test(block)) {
    return { coverageType: "Particular" as const, coverageName: "" };
  }
  const known = coverageMatchers.find((item) => block.toUpperCase().includes(item));
  if (known) return { coverageType: "Mutual" as const, coverageName: known };
  return { coverageType: "Particular" as const, coverageName: "" };
}

function findDni(block: string) {
  const dotted = block.match(/\b\d{1,2}\.\d{3}\.\d{3}\b/);
  if (dotted) return dotted[0].replace(/\D/g, "");
  const candidates = [...block.matchAll(/\b\d{7,8}\b/g)].map((match) => match[0]);
  return candidates.find((value) => !/^54/.test(value)) ?? "";
}

function findName(block: string, time: string, dni: string) {
  let candidate = block.replace(time, " ");
  candidate = candidate.replace(/\+?\s*54[\d\s-]{7,}/g, " ");
  if (dni) {
    const dotted = dni.replace(/(\d{1,2})(\d{3})(\d{3})$/, "$1.$2.$3");
    candidate = candidate.replace(dni, " ").replace(dotted, " ");
  }

  const markers = [
    /\bPARTICULAR\b/i,
    ...coverageMatchers.map((item) => new RegExp(`\\b${item.replace(/\s+/g, "\\s+")}\\b`, "i")),
    /\bLINK\s+DE\s+PAGO\b/i,
    /\bCICLO(?:ESPIROMETRIA|METRIA)\b/i,
    /\bESPIROMETRIA\b/i,
    /\bDR\.?\b/i,
    /\bCENTRO\s+RESPIRATORIO\b/i,
  ];
  const firstMarker = markers
    .map((pattern) => candidate.search(pattern))
    .filter((index) => index >= 0)
    .sort((a, b) => a - b)[0];
  if (firstMarker !== undefined) candidate = candidate.slice(0, firstMarker);

  const cleaned = cleanName(candidate);
  const normalized = normalizeNameForValidation(cleaned);
  if (
    cleaned.length < 3
    || !/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2}/.test(cleaned)
    || /ESPIRO|CICLO|CENTRO|PIGUILLEM|PAGO|RESERVADO/.test(normalized)
  ) return "";
  return cleaned.toLocaleUpperCase("es-AR");
}

export function parseDrappText(rawText: string): DrappRow[] {
  const text = rawText.replace(/\r/g, "\n").replace(/[ \t]+/g, " ").replace(/\n+/g, " ").trim();
  const matches = [...text.matchAll(/\b(?:[01]?\d|2[0-3]):[0-5]\d\b/g)];
  const rows: DrappRow[] = [];

  for (let index = 0; index < matches.length; index += 1) {
    const current = matches[index];
    const start = current.index ?? 0;
    const end = matches[index + 1]?.index ?? text.length;
    const block = text.slice(start, end).trim();
    const time = current[0].padStart(5, "0");
    const dni = findDni(block);
    const name = findName(block, current[0], dni);
    if (!name) continue;
    const coverage = coverageFromBlock(block);
    rows.push({
      time,
      name,
      dni,
      studyType: /\bESPIROMETRIA\b/i.test(block) && !/\bCICLO/i.test(block) ? "Espirometria" : "Ciclometria",
      ...coverage,
    });
  }

  return rows.filter((row, index, allRows) => {
    const key = row.dni || `${normalizeNameForValidation(row.name)}-${row.time}`;
    return allRows.findIndex((candidate) => (candidate.dni || `${normalizeNameForValidation(candidate.name)}-${candidate.time}`) === key) === index;
  });
}
