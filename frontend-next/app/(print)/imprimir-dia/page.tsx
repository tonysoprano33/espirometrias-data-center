import { requireProfile } from "../../lib/auth/require-profile";
import { loadReportData, type ReportAttachment } from "../../lib/reports/load-report-data";
import type { ReportData } from "../../lib/reports/clinical-report";
import { createClient } from "../../lib/supabase/server";
import { AutoPrint } from "../auto-print";
import { ClinicalPrintPacket } from "../clinical-print-packet";
import { PrintToolbar } from "../print-toolbar";

export const dynamic = "force-dynamic";

type DailyPrintProps = {
  searchParams: Promise<{ auto?: string; date?: string }>;
};

type AgendaEntry = {
  encounter_id: string;
  patient_id: string;
  patient_name: string;
  dni: string | null;
  encounter_time: string | null;
  attendance_status: string;
  workflow_status: string;
  so2_rest: number | null;
  fc_rest: number | null;
  so2_post: number | null;
  fc_post: number | null;
  result_code: string;
};

type PrintablePacket = {
  id: string;
  data: ReportData;
  attachment?: ReportAttachment;
};

type LoadedEntry = {
  entry: AgendaEntry;
  loaded: Awaited<ReturnType<typeof loadReportData>>;
  originalIndex: number;
};

function identityKey(entry: AgendaEntry) {
  const dni = entry.dni?.replace(/\D/g, "");
  if (dni) return `dni:${dni}`;
  const name = entry.patient_name
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^A-Za-z0-9]/g, "")
    .toUpperCase();
  return name ? `name:${name}` : `encounter:${entry.encounter_id}`;
}

function dedupeRank(candidate: LoadedEntry) {
  const { data, sourceAttachment } = candidate.loaded;
  const vitalCompleteness = [
    candidate.entry.so2_rest,
    candidate.entry.fc_rest,
    candidate.entry.so2_post,
    candidate.entry.fc_post,
  ].filter((value) => value != null).length;
  const workflowRank: Record<string, number> = {
    entregada: 5,
    informe_generado: 4,
    revisada: 3,
    cargada: 2,
    pendiente: 1,
  };
  return [
    data ? 1 : 0,
    sourceAttachment ? 1 : 0,
    candidate.entry.attendance_status === "atendido" ? 1 : 0,
    candidate.entry.attendance_status !== "no_llego" ? 1 : 0,
    data?.resultCode || candidate.entry.result_code ? 1 : 0,
    vitalCompleteness,
    workflowRank[candidate.entry.workflow_status] ?? 0,
  ];
}

function isHigherRank(left: LoadedEntry, right: LoadedEntry) {
  const leftRank = dedupeRank(left);
  const rightRank = dedupeRank(right);
  for (let index = 0; index < leftRank.length; index += 1) {
    if (leftRank[index] !== rightRank[index]) return leftRank[index] > rightRank[index];
  }
  return false;
}

function uniqueEntriesByPatientDay(entries: LoadedEntry[]) {
  const selected = new Map<string, LoadedEntry>();
  for (const candidate of entries) {
    const key = identityKey(candidate.entry);
    const previous = selected.get(key);
    if (!previous || isHigherRank(candidate, previous)) selected.set(key, candidate);
  }
  return [...selected.values()].sort((left, right) => {
    const leftTime = left.entry.encounter_time || "23:59:59";
    const rightTime = right.entry.encounter_time || "23:59:59";
    return leftTime.localeCompare(rightTime) || left.originalIndex - right.originalIndex;
  });
}

export default async function DailyPrintPage({ searchParams }: DailyPrintProps) {
  await requireProfile(["admin", "espirometrista"]);
  const query = await searchParams;
  const date = query.date || new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).format(new Date());
  const supabase = await createClient();
  const { data: rawEntries } = await supabase.rpc("agenda_entries_v2", { target_date: date });
  const entries = (rawEntries ?? []) as AgendaEntry[];
  const printable: PrintablePacket[] = [];
  const blocked: Array<{ name: string; reason: string }> = [];
  const loadedEntries = await Promise.all(entries.map(async (entry, originalIndex) => ({
    entry,
    loaded: await loadReportData(supabase, entry.encounter_id),
    originalIndex,
  })));

  for (const { entry, loaded } of uniqueEntriesByPatientDay(loadedEntries)) {
    if (entry.attendance_status === "no_llego") {
      blocked.push({ name: entry.patient_name, reason: "No llego" });
      continue;
    }
    if (loaded.data) {
      printable.push({ id: entry.encounter_id, data: loaded.data, attachment: loaded.sourceAttachment });
    } else {
      blocked.push({
        name: entry.patient_name,
        reason: loaded.error || `Completar: ${loaded.missing?.join(", ") || "datos clinicos"}`,
      });
    }
  }

  return <main className="print-root">
    <AutoPrint enabled={query.auto === "1"} />
    <PrintToolbar />
    {blocked.length > 0 && <section className="print-sheet print-blocked-sheet">
      <h1>Faltan datos antes de imprimir todo el dia</h1>
      <p>Estas atenciones no estan listas todavia. Las demas si las deje imprimibles en las hojas siguientes.</p>
      <ul>{blocked.map((entry, index) => <li key={`${entry.name}-${index}`}><b>{entry.name}</b> - {entry.reason}</li>)}</ul>
    </section>}
    {!entries.length && <section className="print-sheet print-blocked-sheet"><h1>No hay pacientes en esta fecha</h1></section>}
    {printable.map((packet) => <ClinicalPrintPacket key={packet.id} data={packet.data} attachment={packet.attachment} />)}
  </main>;
}
