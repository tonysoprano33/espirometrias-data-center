"use client";

import { useEffect, useRef, useState } from "react";

type PdfPreviewProps = { url: string; name: string };

export function PdfPreview({ url, name }: PdfPreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [message, setMessage] = useState("Preparando vista previa...");

  useEffect(() => {
    let cancelled = false;

    async function renderFirstPage() {
      try {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) throw new Error(`No se pudo abrir el archivo (${response.status})`);
        const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const documentTask = pdfjs.getDocument({
          data: new Uint8Array(await response.arrayBuffer()),
        });
        const pdf = await documentTask.promise;
        const page = await pdf.getPage(1);
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = Math.min(2.25, 1500 / baseViewport.width);
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;

        const context = canvas.getContext("2d", { alpha: false });
        if (!context) throw new Error("No se pudo preparar el canvas");
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        await page.render({ canvas, canvasContext: context, viewport }).promise;
        if (!cancelled) setMessage("");
      } catch {
        if (!cancelled) {
          setMessage("No se pudo generar la vista previa. Usa las opciones del archivo.");
        }
      }
    }

    renderFirstPage();
    return () => {
      cancelled = true;
    };
  }, [url]);

  return (
    <div className="pdf-page-frame spirometry-primary" aria-label={`Vista previa de ${name}`}>
      <span className="pdf-page-label">Pagina 1</span>
      <div className="pdf-page-viewport">
        {message && <p className="document-empty">{message}</p>}
        <canvas ref={canvasRef} className="pdf-page-canvas" aria-label={name} />
      </div>
    </div>
  );
}
