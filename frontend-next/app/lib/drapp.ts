export type DrappRow = {
  agendaDate: string;
  time: string;
  name: string;
  dni: string;
  studyType: "Ciclometria" | "Espirometria";
  coverageType: "Particular" | "Mutual";
  coverageName: string;
};

export type DrappOcrItem = {
  text: string;
  x: number;
  y: number;
  height?: number;
};

export type DrappOcrLine = {
  text: string;
  y: number;
  items: DrappOcrItem[];
};

const coverageMatchers = [
  "PARTICULAR",
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
  "OSECAC",
];

const invalidNameWords = [
  "ESPIROMETRIA",
  "CICLOMETRIA",
  "CICLOESPIROMETRIA",
  "CENTRO RESPIRATORIO",
  "PIGUILLEM",
  "LINK DE PAGO",
  "RESERVADO",
];

const spanishMonths: Record<string, number> = {
  ENERO: 1,
  FEBRERO: 2,
  MARZO: 3,
  ABRIL: 4,
  MAYO: 5,
  JUNIO: 6,
  JULIO: 7,
  AGOSTO: 8,
  SEPTIEMBRE: 9,
  SETIEMBRE: 9,
  OCTUBRE: 10,
  NOVIEMBRE: 11,
  DICIEMBRE: 12,
};

function collapseSpaces(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function normalizeForMatch(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Z0-9]+/gi, "")
    .toUpperCase();
}

function cleanName(value: string) {
  let cleaned = collapseSpaces(value)
    .replace(/\+?\s*54[\d\s-]{7,}/g, " ")
    .replace(/\b\d{1,3}(?:[.\s]\d{3}){1,3}\b|\b\d{7,8}\b/g, " ")
    .replace(/\bHACE\s+\d+\s+(?:DIAS?|HORAS?|MINUTOS?)\b/gi, " ")
    .replace(/\bRESERVAD[OA]S?\b/gi, " ")
    .replace(/\bLINK\s+DE\s+PAGO\b/gi, " ")
    .replace(/\bCENTRO\s+RESPIRATORIO\s+INTEGRAL\b/gi, " ")
    .replace(/\bPIGUILLEM\s+GUSTAVO\b/gi, " ")
    .replace(/\b(?:CICLO\s*ESPIROMETRIA|CICLOMETRIA|ESPIROMETRIA)\b.*$/i, " ")
    .replace(/[|_]+/g, " ")
    .replace(/^\s*[O0]\s+(?=\p{L}{3})/u, "")
    .replace(/[^\p{L},.' -]+/gu, " ");

  for (const coverage of coverageMatchers) {
    cleaned = cleaned.replace(new RegExp(`\\b${coverage.replace(/\s+/g, "\\s+")}\\b`, "gi"), " ");
  }

  cleaned = collapseSpaces(cleaned).replace(/^[^\p{L}]+|[^\p{L}']+$/gu, "");
  if (
    cleaned.length < 3
    || !/\p{L}{2}/u.test(cleaned)
    || invalidNameWords.some((word) => normalizeForMatch(cleaned).includes(normalizeForMatch(word)))
  ) {
    return "";
  }
  return cleaned.toLocaleUpperCase("es-AR");
}

function cleanCoverageName(value: string) {
  const chunks = value
    .split("|")
    .map((chunk) => collapseSpaces(chunk)
      .replace(/\bLINK\s+DE\s+PAGO\b/gi, " ")
      .replace(/\b\d{1,3}(?:[./-]\d{1,3})+\b/g, " ")
      .replace(/[|_:]+/g, " "))
    .map(collapseSpaces)
    .filter((chunk) => /\p{L}{2}/u.test(chunk));

  const known = coverageMatchers.find((item) =>
    chunks.some((chunk) => normalizeForMatch(chunk).includes(normalizeForMatch(item))));
  if (known) return known;

  const candidate = chunks.find((chunk) =>
    !/ESPIRO|CICLO|CENTRO|PIGUILLEM|PAGO|RESERVAD|HACE/i.test(normalizeForMatch(chunk)));
  return candidate?.toLocaleUpperCase("es-AR").slice(0, 120) ?? "";
}

function coverageFromBlock(block: string, structuredCoverage = "") {
  const combined = collapseSpaces(`${structuredCoverage} ${block}`);
  if (/\bPARTICULAR\b/i.test(combined)) {
    return { coverageType: "Particular" as const, coverageName: "" };
  }

  const coverageName = cleanCoverageName(structuredCoverage)
    || coverageMatchers.find((item) =>
      item !== "PARTICULAR" && normalizeForMatch(combined).includes(normalizeForMatch(item)))
    || "";

  return coverageName
    ? { coverageType: "Mutual" as const, coverageName }
    : { coverageType: "Particular" as const, coverageName: "" };
}

function findDni(block: string) {
  const dotted = block.match(/\b\d{1,2}[.\s]\d{3}[.\s]\d{3}\b/);
  if (dotted) return dotted[0].replace(/\D/g, "");
  const withoutPhones = block.replace(/\+?\s*54[\d\s-]{7,}/g, " ");
  const candidates = [...withoutPhones.matchAll(/\b\d{7,8}\b/g)].map((match) => match[0]);
  return candidates.find((value) => !/^54/.test(value)) ?? "";
}

function studyFromBlock(block: string) {
  const normalized = normalizeForMatch(block);
  return normalized.includes("ESPIROMETRIA") && !normalized.includes("CICLO")
    ? "Espirometria" as const
    : "Ciclometria" as const;
}

function validIsoDate(year: number, month: number, day: number) {
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
  ) {
    return "";
  }
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

export function parseDrappAgendaDate(rawValue: string) {
  const normalized = collapseSpaces(rawValue)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase();

  const numericMatch = normalized.match(/\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b/);
  if (numericMatch) {
    return validIsoDate(Number(numericMatch[3]), Number(numericMatch[2]), Number(numericMatch[1]));
  }

  const words = normalized.replace(/[^A-Z0-9]+/g, " ");
  const writtenMatch = words.match(
    /\b(?:LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO)?\s*(\d{1,2})(?:\s+DE)?\s+([A-Z]+)\s+(\d{4})\b/,
  );
  if (!writtenMatch) return "";
  const month = spanishMonths[writtenMatch[2]];
  return month ? validIsoDate(Number(writtenMatch[3]), month, Number(writtenMatch[1])) : "";
}

function uniqueRows(rows: DrappRow[]) {
  return rows.filter((row, index, allRows) => {
    const key = `${row.agendaDate}-${row.dni || `${normalizeForMatch(row.name)}-${row.time}`}`;
    return allRows.findIndex((candidate) =>
      `${candidate.agendaDate}-${candidate.dni || `${normalizeForMatch(candidate.name)}-${candidate.time}`}` === key) === index;
  });
}

function zoneText(line: DrappOcrLine, minRatio: number, maxRatio: number | null, canvasWidth: number) {
  return collapseSpaces(line.items
    .filter((item) => item.x >= canvasWidth * minRatio && (maxRatio === null || item.x < canvasWidth * maxRatio))
    .sort((left, right) => left.x - right.x)
    .map((item) => item.text)
    .join(" "));
}

export function parseDrappOcrLines(lines: DrappOcrLine[], sourceWidth?: number): DrappRow[] {
  const agendaDate = parseDrappAgendaDate(lines.slice(0, 8).map((line) => line.text).join(" "));
  const maxX = Math.max(0, ...lines.flatMap((line) => line.items.map((item) => item.x)));
  const canvasWidth = Math.max(sourceWidth ?? 0, maxX);
  if (!canvasWidth) return parseDrappText(lines.map((line) => line.text).join("\n"));

  const timePattern = /(?<!\d)(\d{1,2}:[0-5]\d)(?!\d)/;
  const groups: Array<{ time: string; lines: DrappOcrLine[] }> = [];

  for (const line of [...lines].sort((left, right) => left.y - right.y)) {
    const match = line.text.match(timePattern);
    if (match) {
      const timeItems = line.items.filter((item) => !timePattern.test(item.text));
      groups.push({
        time: match[1].padStart(5, "0"),
        lines: [{ ...line, items: timeItems, text: collapseSpaces(timeItems.map((item) => item.text).join(" ")) }],
      });
    } else if (groups.length) {
      groups[groups.length - 1].lines.push(line);
    }
  }

  const rows = groups.map((group) => {
    const patientChunks = group.lines.map((line) => zoneText(line, 0.11, 0.42, canvasWidth)).filter(Boolean);
    const coverageChunks = group.lines.map((line) => zoneText(line, 0.42, 0.60, canvasWidth)).filter(Boolean);
    const practiceChunks = group.lines.map((line) => zoneText(line, 0.60, null, canvasWidth)).filter(Boolean);
    const patientBlock = patientChunks.join(" | ");
    const coverageBlock = coverageChunks.join(" | ");
    const practiceBlock = practiceChunks.join(" | ");
    const fallbackBlock = group.lines.map((line) => line.text).join(" | ");
    const coverage = coverageFromBlock(fallbackBlock, coverageBlock);

    const nameCandidates = patientChunks
      .map(cleanName)
      .filter(Boolean)
      .sort((left, right) => {
        const commaDifference = Number(right.includes(",")) - Number(left.includes(","));
        return commaDifference || right.length - left.length;
      });

    return {
      agendaDate,
      time: group.time,
      name: nameCandidates[0] ?? cleanName(patientBlock),
      dni: findDni(patientBlock || fallbackBlock),
      studyType: studyFromBlock(practiceBlock || fallbackBlock),
      ...coverage,
    };
  }).filter((row) => row.name);

  return uniqueRows(rows);
}

export function parseDrappText(rawText: string): DrappRow[] {
  const lines = rawText.replace(/\r/g, "\n").split(/\n+/).map(collapseSpaces).filter(Boolean);
  const agendaDate = parseDrappAgendaDate(lines.slice(0, 8).join(" "));
  const text = lines.join(" ");
  const matches = [...text.matchAll(/\b(?:[01]?\d|2[0-3]):[0-5]\d\b/g)];
  const rows: DrappRow[] = [];

  for (let index = 0; index < matches.length; index += 1) {
    const current = matches[index];
    const start = current.index ?? 0;
    const end = matches[index + 1]?.index ?? text.length;
    const block = text.slice(start, end).trim();
    const time = current[0].padStart(5, "0");
    const dni = findDni(block);
    const coverage = coverageFromBlock(block);

    let nameBlock = block
      .replace(current[0], " ")
      .replace(/\+?\s*54[\d\s-]{7,}/g, " ");
    const markerPatterns = [
      /\bPARTICULAR\b/i,
      ...coverageMatchers.map((item) => new RegExp(`\\b${item.replace(/\s+/g, "\\s+")}\\b`, "i")),
      /\bLINK\s+DE\s+PAGO\b/i,
      /\b(?:CICLO\s*ESPIROMETRIA|CICLOMETRIA|ESPIROMETRIA)\b/i,
    ];
    const marker = markerPatterns.map((pattern) => nameBlock.search(pattern)).filter((position) => position >= 0).sort((a, b) => a - b)[0];
    if (marker !== undefined) nameBlock = nameBlock.slice(0, marker);
    const name = cleanName(nameBlock);
    if (!name) continue;

    rows.push({
      agendaDate,
      time,
      name,
      dni,
      studyType: studyFromBlock(block),
      ...coverage,
    });
  }

  return uniqueRows(rows);
}
