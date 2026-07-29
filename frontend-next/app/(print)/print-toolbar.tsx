"use client";

import Link from "next/link";

export function PrintToolbar({ sourceUrl }: { sourceUrl?: string }) {
  return <div className="print-toolbar">
    <button className="print-button" type="button" onClick={() => window.print()}>Imprimir</button>
    <Link className="print-button alt" href="/agenda">Volver</Link>
    {sourceUrl && <a className="print-button alt" href={sourceUrl} target="_blank" rel="noreferrer">Abrir resultado original</a>}
  </div>;
}
