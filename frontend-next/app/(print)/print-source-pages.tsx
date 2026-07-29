"use client";

import { useEffect, useRef, useState } from "react";
import type { ReportAttachment } from "../lib/reports/load-report-data";

export function PrintSourcePages({ attachment }: { attachment: ReportAttachment }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const sourceUrl = `/api/attachments/${attachment.id}/content`;

  useEffect(() => {
    if (attachment.fileKind !== "pdf_resultado") return;
    let cancelled = false;

    async function renderPdf() {
      const host = hostRef.current;
      if (!host) return;
      try {
        const response = await fetch(sourceUrl, { cache: "no-store" });
        if (!response.ok) throw new Error(`No se pudo abrir el PDF (${response.status})`);
        const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const pdf = await pdfjs.getDocument({ data: new Uint8Array(await response.arrayBuffer()) }).promise;
        if (cancelled) return;
        host.replaceChildren();

        for (let index = 1; index <= pdf.numPages; index += 1) {
          const page = await pdf.getPage(index);
          const base = page.getViewport({ scale: 1 });
          const viewport = page.getViewport({ scale: 1536 / base.width });
          const sheet = document.createElement("section");
          sheet.className = "print-sheet-pdf print-page-break";
          const canvas = document.createElement("canvas");
          canvas.width = Math.ceil(viewport.width);
          canvas.height = Math.ceil(viewport.height);
          canvas.setAttribute("aria-label", `${attachment.originalName}, página ${index}`);
          sheet.append(canvas);
          host.append(sheet);
          const context = canvas.getContext("2d");
          if (!context) throw new Error("No se pudo preparar la página del PDF");
          await page.render({ canvas, canvasContext: context, viewport }).promise;
          if (cancelled) return;
        }
        host.dataset.printLoading = "false";
      } catch (reason) {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "No se pudo mostrar el PDF original.");
        host.dataset.printLoading = "false";
      }
    }

    renderPdf();
    return () => { cancelled = true; };
  }, [attachment.fileKind, attachment.originalName, sourceUrl]);

  if (attachment.fileKind === "foto_resultado") {
    return <section className="print-sheet-pdf print-page-break">
      <img src={sourceUrl} alt={`Resultado original ${attachment.originalName}`} />
    </section>;
  }

  return <div ref={hostRef} data-print-loading="true" className="print-source-host">
    {error
      ? <section className="print-sheet print-page-break"><div className="print-source-error"><b>No se pudo incorporar el PDF original.</b><span>{error}</span></div></section>
      : <section className="print-sheet print-page-break"><div className="print-source-loading">Preparando resultado original...</div></section>}
  </div>;
}
