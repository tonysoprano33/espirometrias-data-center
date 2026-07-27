"use client";

import { FormEvent, useEffect, useState } from "react";

type PatientRow = {
  patient_id: number;
  full_name: string;
  dni: string;
  phone: string;
  patient_code: string;
  encounter_count: number;
  last_encounter_date: string;
  detail_url: string;
  edit_url: string;
  can_manage: boolean;
};

type PatientPayload = {
  query: string;
  total: number;
  page: number;
  pages: number;
  has_previous: boolean;
  has_next: boolean;
  rows: PatientRow[];
};

export default function PatientsPage() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PatientPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const params = new URLSearchParams({ page: String(page) });
        if (submittedQuery) params.set("q", submittedQuery);
        const response = await fetch(`/api/v1/pacientes/?${params.toString()}`, { cache: "no-store", credentials: "same-origin" });
        if (!response.ok) throw new Error("No se pudo cargar la base de pacientes.");
        const payload = await response.json() as PatientPayload;
        if (!active) return;
        setData(payload); setError("");
        window.history.replaceState({}, "", `/pacientes/${submittedQuery ? `?q=${encodeURIComponent(submittedQuery)}&` : "?"}page=${payload.page}`);
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : "Error de conexion."); }
    };
    void load();
    return () => { active = false; };
  }, [submittedQuery, page]);

  const submit = (event: FormEvent) => { event.preventDefault(); setPage(1); setSubmittedQuery(query.trim()); };

  return <main className="agenda-shell patients-next">
    <header className="agenda-header"><div><p className="eyebrow">Base clinica</p><h1>Pacientes</h1><p className="subtitle">Busca por nombre, DNI, codigo, mutual, fecha o resultado sin recorrer una tabla larga.</p></div><div className="header-actions"><nav className="next-nav" aria-label="Navegacion nueva"><a href="/">Agenda</a><a href="/calendario/">Calendario</a><a href="/estadistica/">Estadisticas</a><a className="is-current" href="/pacientes/">Pacientes</a><a href="/revision-medica/">Revision medica</a></nav><a className="back-link" href="/django/pacientes/">Vista actual</a></div></header>
    <form className="patient-search-next" onSubmit={submit}><label htmlFor="patient-search">Buscar historia clinica</label><div><input id="patient-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nombre, DNI, codigo, mutual, fecha o resultado" autoComplete="off" /><button type="submit">Buscar</button></div><p>Ejemplos: `30.111.222`, `PAMI`, `N`, `12/06/2026` o un apellido.</p></form>
    {error && <p className="notice error" role="alert">{error}</p>}{!data && !error && <p className="notice">Cargando pacientes...</p>}
    {data && <section className="patients-list-next"><div className="patients-list-head"><div><p className="eyebrow">Resultado</p><h2>{data.total} historia{data.total === 1 ? "" : "s"}{submittedQuery ? ` para ${submittedQuery}` : " cargada"}</h2></div><span>Pagina {data.page} de {data.pages || 1}</span></div><div className="patients-cards">{data.rows.map((row) => <article key={row.patient_id} className="patient-card-next"><div className="patient-card-main"><span className="patient-card-accent" /><div><strong>{row.full_name}</strong><span>Cod. {row.patient_code}</span></div></div><div className="patient-data"><span>DNI</span><b>{row.dni}</b></div><div className="patient-data"><span>Telefono</span><b>{row.phone}</b></div><div className="patient-data"><span>Atenciones</span><b>{row.encounter_count}</b></div><div className="patient-data"><span>Ultima visita</span><b>{row.last_encounter_date}</b></div><div className="patient-card-actions"><a href={`/pacientes/${row.patient_id}/`}>Abrir ficha</a>{row.can_manage && <a href={`/django${row.edit_url}`}>Editar</a>}</div></article>)}{!data.rows.length && <p className="empty">No encontramos pacientes con esa busqueda.</p>}</div><nav className="patient-pagination-next" aria-label="Paginacion de pacientes"><button disabled={!data.has_previous} onClick={() => setPage(data.page - 1)}>Anterior</button><span>Pagina {data.page} de {data.pages || 1}</span><button disabled={!data.has_next} onClick={() => setPage(data.page + 1)}>Siguiente</button></nav></section>}
  </main>;
}
