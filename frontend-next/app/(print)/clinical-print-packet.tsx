import type { ReportAttachment } from "../lib/reports/load-report-data";
import {
  buildWalkRows,
  formatReportDate,
  formatReportDni,
  isNormalResult,
  mutualCvlResult,
  normalizeDoctor,
  reportText,
  type ReportData,
  walkAssessment,
} from "../lib/reports/clinical-report";
import { PrintSourcePages } from "./print-source-pages";

function Header() {
  return <div className="print-header-box">
    <strong>CENTRO RESPIRATORIO INTEGRAL</strong>
    <span>MARCONI 147 - TEL: 02657-705270</span>
    <span>VILLA MERCEDES (SAN LUIS)</span>
  </div>;
}

function PatientLines({ data, compact = false }: { data: ReportData; compact?: boolean }) {
  return <>
    <div className="print-date">{formatReportDate(data.date)}</div>
    <div className="print-line-item"><strong>PACIENTE:</strong> <span className={compact ? "" : "print-patient-value"}>{data.patientName.trim().toLocaleUpperCase("es-AR")}</span></div>
    <div className="print-line-item print-dni-line"><strong>DNI:</strong> <span className="print-dni-value">{formatReportDni(data.dni)}</span></div>
    <div className="print-line-item"><strong>DERIVA:</strong> {normalizeDoctor(data.physicianName)}</div>
  </>;
}

function Signature() {
  return <div className="print-signature">
    DR. PIGUILLEM GUSTAVO GABRIEL<br />
    MAT. 2083<br />
    ESP. EN VIAS RESPIRATORIAS
  </div>;
}

function WalkTable({ data }: { data: ReportData }) {
  return <table>
    <thead><tr><th>MINUTOS</th><th>SO2</th><th>FC</th><th>ESC. BORG</th></tr></thead>
    <tbody>{buildWalkRows(data).map((row) => <tr key={row.minute}>
      <td>{row.minute}</td><td>{row.so2}</td><td>{row.fc}</td><td>{row.borg}</td>
    </tr>)}</tbody>
  </table>;
}

export function ClinicalPrintPacket({ data, attachment }: { data: ReportData; attachment?: ReportAttachment }) {
  const includeWalk = data.studyType === "Ciclometria" && (data.hasVitals || data.hasWalk);
  const result = reportText(data);
  const assessment = walkAssessment(data);
  const so2 = data.so2Rest ?? "";
  const fc = data.fcRest ?? "";

  return <>
    <section className="print-sheet">
      <Header />
      <PatientLines data={data} />
      <h2>Resultado Espirometria Computarizada</h2>
      <p className="print-emphasis print-spirometry-result">{result}</p>
      <p className="print-emphasis print-so2-fc">SO2: {so2}% <span>FC: {fc}</span></p>
      {data.bronchodilatorPositive && <p className="print-emphasis print-bronchodilator">Broncodilatador Positivo</p>}
      {!isNormalResult(data) && <p className="print-clinical-note">Por antecedentes clinicos del paciente, sugiero control.</p>}
      <Signature />
    </section>

    {includeWalk && <section className="print-sheet print-page-break">
      <Header />
      <PatientLines data={data} />
      <h2>Prueba de los 6 y 12 minutos</h2>
      <p>Se realizo test de la marcha con monitoreo continuo; en reposo, durante la marcha (6 min.) y en la recuperacion (2 min.). Los parametros registrados fueron: Saturacion de O2, frecuencia de pulso, esfuerzo percibido por medio de escala de Borg y la distancia recorrida a la finalizacion.</p>
      <div className="print-walk-comments">
        <p><strong>Distancia recorrida:</strong> {data.distanceMeters || 200} mts.</p>
        <p><strong>Realizo correctamente la marcha:</strong> {data.walkCompleted ? "Si" : "No"}</p>
        <p><strong>Se detuvo durante la marcha:</strong> {data.walkStopped ? "Si" : "No"}</p>
        <p><strong>Presento sintomas al final de la marcha:</strong> {data.walkSymptoms ? "Si" : "No"}</p>
      </div>
      <WalkTable data={data} />
      <p className="print-walk-result">PRUEBA DE LOS 6 Y 12 MINUTOS: {assessment}</p>
      <Signature />
    </section>}

    {attachment && <PrintSourcePages attachment={attachment} />}

    {includeWalk && data.coverageType === "Mutual" && <section className="print-sheet print-mutual-sheet print-page-break">
      <Header />
      <PatientLines data={data} compact />
      <h2>PRUEBA DE LOS 6 Y 12 MINUTOS</h2>
      <p>Se realizo test de la marcha con monitoreo continuo; en reposo, durante la marcha (6 min.) y en la recuperacion (2 min.). Los parametros registrados fueron: Saturacion de O2, frecuencia de pulso, esfuerzo percibido por medio de escala de Borg y la distancia recorrida a la finalizacion.</p>
      <p><strong><u>COMENTARIOS:</u></strong></p>
      <div className="print-mutual-comments">
        <p><strong>Distancia recorrida:</strong> {data.distanceMeters || 200} mts.</p>
        <p><strong>Realizo correctamente la marcha:</strong> {data.walkCompleted ? "Si" : "No"}.</p>
        <p><strong>Se detuvo durante la marcha:</strong> {data.walkStopped ? "Si" : "No"}.</p>
        <p><strong>Presento algun sintoma al final de la marcha:</strong> {data.walkSymptoms ? "Si" : "No"}.</p>
      </div>
      <WalkTable data={data} />
      <p className="print-mutual-emphasis">SO2: {so2}% &nbsp;&nbsp;&nbsp; FC: {fc}</p>
      <p><strong><u>PRUEBA DE LOS 6 Y 12 MINUTOS:</u></strong> {assessment}</p>
      <h2>Resultado Espirometria Computarizada:</h2>
      <p className="print-spirometry-result">{result}</p>
      <h2>Capacidad Vital Lenta:</h2>
      <p className="print-mutual-emphasis">{mutualCvlResult(data)}</p>
      <Signature />
    </section>}
  </>;
}
