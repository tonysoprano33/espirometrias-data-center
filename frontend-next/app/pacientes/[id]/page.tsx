"use client";

import { useEffect, useState } from "react";

type EncounterRow = {
  encounter_id: number; date: string; time: string; study_type: string; coverage: string; result_code: string; attendance: string;
  progression: { label: string; tone: string; detail: string };
  vitals: { so2_rest: number | null; fc_rest: number | null; so2_post: number | null; fc_post: number | null };
  file: { present: boolean; url: string; name: string; status: string };
  reports: { complete_url: string; mutual_url: string };
  review_url: string; print_url: string; can_print: boolean;
};
type Payload = { patient: { name: string; dni: string; phone: string; birth_date: string; gender: string; bmi: string | number }; encounters: EncounterRow[]; can_manage: boolean; legacy_url: string };

export default function PatientDetailNextPage({ params }: { params: Promise<{ id: string }> }) {
  const [id, setId] = useState(""); const [data, setData] = useState<Payload | null>(null); const [error, setError] = useState("");
  useEffect(() => { void params.then((value) => setId(value.id)); }, [params]);
  useEffect(() => { if (!id) return; let active = true; fetch(`/api/v1/pacientes/${id}/`, { credentials: "same-origin" }).then(async (response) => { const payload = await response.json(); if (!response.ok) throw new Error(payload.message || "No se pudo cargar la historia."); return payload as Payload; }).then((payload) => { if (active) setData(payload); }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "No se pudo cargar la historia."); }); return () => { active = false; }; }, [id]);
  return <main className="agenda-shell patient-detail-next"><a className="back-link" href="/pacientes/">Volver a pacientes</a>{error && <p className="notice error">{error}</p>}{!data && !error && <p className="notice">Cargando historia clinica...</p>}{data && <><header className="patient-history-head"><div><p className="eyebrow">Historia clinica</p><h1>{data.patient.name}</h1><p>DNI {data.patient.dni} | Tel. {data.patient.phone}</p></div><a href={`/django${data.legacy_url}`}>Abrir opciones avanzadas</a></header><section className="patient-profile-next"><Info label="Nacimiento" value={data.patient.birth_date} /><Info label="Genero" value={data.patient.gender} /><Info label="BMI" value={String(data.patient.bmi)} /><Info label="Atenciones" value={String(data.encounters.length)} /></section><section className="patient-history-list"><div className="patients-list-head"><div><p className="eyebrow">Evolucion</p><h2>Estudios y comparacion</h2></div><span>Mas reciente primero</span></div>{data.encounters.map((encounter) => <article className="history-encounter" key={encounter.encounter_id}><div className="history-date"><b>{encounter.date}</b><span>{encounter.time}</span></div><div className="history-main"><strong>{encounter.study_type}</strong><span>{encounter.coverage} | Resultado <b>{encounter.result_code}</b> | {encounter.attendance}</span><p className={`progression-${encounter.progression.tone}`}>{encounter.progression.label}: {encounter.progression.detail}</p></div><div className="history-vitals"><span>Reposo {encounter.vitals.so2_rest ?? "-"}/{encounter.vitals.fc_rest ?? "-"}</span><span>Post {encounter.vitals.so2_post ?? "-"}/{encounter.vitals.fc_post ?? "-"}</span></div><div className="history-actions"><a href={`/revision-medica/${encounter.encounter_id}/`}>Revision</a>{encounter.can_print && <a href={`/django${encounter.print_url}`} target="_blank">Imprimir</a>}{encounter.file.present && <a href={`/django${encounter.file.url}`} target="_blank">PDF</a>}{encounter.reports.complete_url && <a href={`/django${encounter.reports.complete_url}`} target="_blank">Informe</a>}{encounter.reports.mutual_url && <a href={`/django${encounter.reports.mutual_url}`} target="_blank">Mutual</a>}</div></article>)}{!data.encounters.length && <p className="empty">Este paciente todavia no tiene atenciones registradas.</p>}</section></>}</main>;
}

function Info({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><b>{value}</b></div>; }
