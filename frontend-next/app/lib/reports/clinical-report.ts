import { PDFDocument, StandardFonts, rgb, type PDFFont, type PDFPage } from "pdf-lib";

export type ReportData = {
  date: string;
  patientName: string;
  dni: string;
  physicianName: string;
  studyType: "Ciclometria" | "Espirometria";
  coverageType: "Mutual" | "Particular";
  coverageName: string;
  so2Rest: number;
  fcRest: number;
  so2Post: number;
  fcPost: number;
  resultCode: string;
  bronchodilatorPositive: boolean;
  distanceMeters: number;
  walkCompleted: boolean;
  walkStopped: boolean;
  walkSymptoms: boolean;
  borgFinal: number;
};

type Fonts = {
  regular: PDFFont;
  bold: PDFFont;
  italic: PDFFont;
};

const navy = rgb(0.10, 0.20, 0.34);
const blue = rgb(0.10, 0.45, 0.92);

function formatDate(value: string) {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function formatDni(value: string) {
  const digits = value.replace(/\D/g, "");
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function titleCaseDoctor(value: string) {
  const name = value.trim() || "Dr. Gustavo Piguillem";
  return name.toUpperCase();
}

function parseResult(codeValue: string) {
  const code = codeValue.toUpperCase().trim();
  if (code === "N") return { type: "normal" as const, restriction: "", obstruction: "" };

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

  if (obstructionLabels[code]) {
    return { type: "obstructive" as const, restriction: "", obstruction: obstructionLabels[code] };
  }
  if (restrictionLabels[code]) {
    return { type: "restrictive" as const, restriction: restrictionLabels[code], obstruction: "" };
  }

  const restrictionCode = ["RMS", "RS", "RM", "RL"].find((candidate) => code.startsWith(candidate));
  const obstructionCode = restrictionCode ? code.slice(restrictionCode.length) : "";
  if (restrictionCode && obstructionLabels[obstructionCode]) {
    return {
      type: "mixed" as const,
      restriction: restrictionLabels[restrictionCode],
      obstruction: obstructionLabels[obstructionCode],
    };
  }
  return { type: "unknown" as const, restriction: "", obstruction: "" };
}

function resultLines(code: string) {
  const result = parseResult(code);
  if (result.type === "normal") return ["El paciente presenta resultados normales."];
  if (result.type === "obstructive") {
    return [`El paciente presenta deficit respiratorio (obstruccion ${result.obstruction})`, "a las pequenas vias respiratorias aereas."];
  }
  if (result.type === "restrictive") {
    return [`El paciente presenta deficit respiratorio (restriccion ${result.restriction})`, "a las vias respiratorias aereas."];
  }
  if (result.type === "mixed") {
    return [
      "El paciente presenta deficit respiratorio con patron mixto:",
      `  Restriccion ${result.restriction}.`,
      `  Obstruccion ${result.obstruction} a las pequenas vias respiratorias aereas.`,
    ];
  }
  return [`Resultado de espirometria: ${code}.`];
}

function drawHeader(page: PDFPage, fonts: Fonts) {
  page.drawRectangle({ x: 78, y: 710, width: 439, height: 60, borderColor: blue, borderWidth: 1 });
  page.drawText("CENTRO RESPIRATORIO INTEGRAL", { x: 178, y: 748, size: 12, font: fonts.bold, color: navy });
  page.drawText("MARCONI 147 - TEL: 02657-705270", { x: 197, y: 733, size: 8.5, font: fonts.regular });
  page.drawText("VILLA MERCEDES (SAN LUIS)", { x: 216, y: 720, size: 8.5, font: fonts.regular });
}

function drawPatientData(page: PDFPage, fonts: Fonts, data: ReportData, startY = 667) {
  page.drawText(formatDate(data.date), { x: 455, y: startY + 8, size: 11.5, font: fonts.bold });
  const values = [
    ["PACIENTE:", data.patientName.toUpperCase()],
    ["DNI:", formatDni(data.dni)],
    ["DERIVA:", titleCaseDoctor(data.physicianName)],
  ];
  values.forEach(([label, value], index) => {
    const y = startY - index * 25;
    page.drawText(label, { x: 88, y, size: 10.5, font: fonts.bold, color: navy });
    page.drawLine({ start: { x: 88, y: y - 2 }, end: { x: 88 + fonts.bold.widthOfTextAtSize(label, 10.5), y: y - 2 }, thickness: 0.8, color: navy });
    page.drawText(value, { x: 153, y, size: 10.5, font: fonts.regular });
  });
}

function drawSignature(page: PDFPage, fonts: Fonts) {
  page.drawText("DR. PIGUILLEM GUSTAVO GABRIEL", { x: 221, y: 62, size: 6.3, font: fonts.regular, color: rgb(0.42, 0.42, 0.42) });
  page.drawText("MAT. 2083", { x: 274, y: 52, size: 6.3, font: fonts.regular, color: rgb(0.42, 0.42, 0.42) });
  page.drawText("ESP. EN VIAS RESPIRATORIAS", { x: 238, y: 42, size: 6.3, font: fonts.regular, color: rgb(0.42, 0.42, 0.42) });
}

function drawSpirometryPage(pdf: PDFDocument, fonts: Fonts, data: ReportData) {
  const page = pdf.addPage([595.28, 841.89]);
  drawHeader(page, fonts);
  drawPatientData(page, fonts, data);
  page.drawText("Resultado Espirometria Computarizada:", { x: 88, y: 570, size: 12.5, font: fonts.bold, color: navy });
  page.drawLine({ start: { x: 88, y: 568 }, end: { x: 316, y: 568 }, thickness: 0.8, color: navy });

  let y = 535;
  for (const line of resultLines(data.resultCode)) {
    page.drawText(line, { x: line.startsWith("  ") ? 101 : 88, y, size: 12.5, font: fonts.bold });
    y -= 25;
  }

  page.drawText(`SO2: ${data.so2Rest}%`, { x: 88, y: y - 18, size: 11.5, font: fonts.bold });
  page.drawText(`FC: ${data.fcRest} lpm`, { x: 230, y: y - 18, size: 11.5, font: fonts.bold });
  if (data.bronchodilatorPositive) {
    page.drawText("Broncodilatador positivo", { x: 88, y: y - 46, size: 11.5, font: fonts.bold, color: rgb(0.04, 0.45, 0.34) });
  }
  if (data.resultCode !== "N") {
    page.drawText("Por antecedentes clinicos del paciente, sugiero control.", { x: 88, y: y - 86, size: 10.5, font: fonts.italic });
  }
  drawSignature(page, fonts);
}

function interpolate(start: number, end: number, minute: number) {
  return Math.round(start + ((end - start) * minute / 6));
}

function walkRows(data: ReportData) {
  const finalBorg = data.borgFinal > 0 ? data.borgFinal : 1;
  return Array.from({ length: 7 }, (_, minute) => ({
    minute,
    so2: interpolate(data.so2Rest, data.so2Post, minute),
    fc: interpolate(data.fcRest, data.fcPost, minute),
    borg: Math.floor((finalBorg * minute) / 6),
  }));
}

function drawWalkPage(pdf: PDFDocument, fonts: Fonts, data: ReportData) {
  const page = pdf.addPage([595.28, 841.89]);
  drawHeader(page, fonts);
  drawPatientData(page, fonts, data);
  page.drawText("PRUEBA DE LOS 6 Y 12 MINUTOS", { x: 88, y: 570, size: 10.5, font: fonts.bold });
  page.drawLine({ start: { x: 88, y: 568 }, end: { x: 258, y: 568 }, thickness: 0.8 });

  const description = "Se realizo test de la marcha con monitoreo continuo; en reposo, durante la marcha (6 min.) y en la recuperacion (2 min.).";
  page.drawText(description, { x: 88, y: 548, size: 7.8, font: fonts.regular, maxWidth: 430 });
  page.drawText(`Distancia recorrida: ${data.distanceMeters} mts.`, { x: 101, y: 518, size: 8.2, font: fonts.regular });
  page.drawText(`Realizo correctamente la marcha: ${data.walkCompleted ? "Si" : "No"}`, { x: 101, y: 500, size: 8.2, font: fonts.regular });
  page.drawText(`Se detuvo durante la marcha: ${data.walkStopped ? "Si" : "No"}`, { x: 101, y: 482, size: 8.2, font: fonts.regular });
  page.drawText(`Presento sintomas al final de la marcha: ${data.walkSymptoms ? "Si" : "No"}`, { x: 101, y: 464, size: 8.2, font: fonts.regular });

  const columns = [88, 210, 300, 383, 507];
  const top = 435;
  const rowHeight = 22;
  const headers = ["MINUTOS", "SO2", "FC", "ESC. BORG"];
  for (let index = 0; index < headers.length; index += 1) {
    page.drawRectangle({ x: columns[index], y: top, width: columns[index + 1] - columns[index], height: rowHeight, borderWidth: 0.5, borderColor: rgb(0, 0, 0), color: rgb(0.92, 0.96, 0.98) });
    const text = headers[index];
    const width = fonts.bold.widthOfTextAtSize(text, 7.5);
    page.drawText(text, { x: columns[index] + ((columns[index + 1] - columns[index] - width) / 2), y: top + 7, size: 7.5, font: fonts.bold });
  }

  walkRows(data).forEach((row, rowIndex) => {
    const y = top - ((rowIndex + 1) * rowHeight);
    [row.minute, row.so2, row.fc, row.borg].forEach((value, columnIndex) => {
      page.drawRectangle({ x: columns[columnIndex], y, width: columns[columnIndex + 1] - columns[columnIndex], height: rowHeight, borderWidth: 0.5, borderColor: rgb(0, 0, 0) });
      const text = String(value);
      const width = fonts.regular.widthOfTextAtSize(text, 8);
      page.drawText(text, { x: columns[columnIndex] + ((columns[columnIndex + 1] - columns[columnIndex] - width) / 2), y: y + 7, size: 8, font: fonts.regular });
    });
  });

  const abnormal = data.so2Post <= 88 || data.so2Rest - data.so2Post >= 4 || !data.walkCompleted || data.walkStopped || data.walkSymptoms;
  page.drawText(`PRUEBA DE LOS 6 Y 12 MINUTOS: ${abnormal ? "PRUEBA NO NORMAL" : "PRUEBA NORMAL"}`, { x: 88, y: 245, size: 9, font: fonts.bold });
  drawSignature(page, fonts);
}

function drawMutualPage(pdf: PDFDocument, fonts: Fonts, data: ReportData) {
  const page = pdf.addPage([595.28, 841.89]);
  drawHeader(page, fonts);
  drawPatientData(page, fonts, data);
  page.drawText("INFORME PARA MUTUAL", { x: 88, y: 570, size: 12, font: fonts.bold, color: navy });
  page.drawText(`Cobertura: ${data.coverageName || "Mutual"}`, { x: 88, y: 540, size: 10.5, font: fonts.regular });
  page.drawText(`Estudio realizado: ${data.studyType}`, { x: 88, y: 515, size: 10.5, font: fonts.regular });
  page.drawText(`Resultado: ${data.resultCode}`, { x: 88, y: 490, size: 10.5, font: fonts.bold });
  drawSignature(page, fonts);
}

export async function createClinicalReport(data: ReportData) {
  const pdf = await PDFDocument.create();
  const fonts: Fonts = {
    regular: await pdf.embedFont(StandardFonts.TimesRoman),
    bold: await pdf.embedFont(StandardFonts.TimesRomanBold),
    italic: await pdf.embedFont(StandardFonts.TimesRomanItalic),
  };
  drawSpirometryPage(pdf, fonts, data);
  if (data.studyType === "Ciclometria") drawWalkPage(pdf, fonts, data);
  if (data.coverageType === "Mutual") drawMutualPage(pdf, fonts, data);
  return pdf.save();
}
