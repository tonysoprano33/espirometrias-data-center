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
        const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
        const documentTask = pdfjs.getDocument({ url });
        const pdf = await documentTask.promise;
        const page = await pdf.getPage(1);
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = Math.min(1.35, 1100 / baseViewport.width);
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;

        const context = canvas.getContext("2d");
        if (!context) throw new Error("No se pudo preparar el canvas");
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        await page.render({ canvas, canvasContext: context, viewport }).promise;
        if (!cancelled) setMessage("");
      } catch {
        if (!cancelled) setMessage("No se pudo generar la vista previa. Abrí el archivo grande para verlo.");
      }
    }

    renderFirstPage();
    return () => { cancelled = true; };
  }, [url]);

  return (
    <div className="pdf-image-preview" aria-label={`Vista previa de ${name}`}>
      {message && <p className="document-empty">{message}</p>}
      <canvas ref={canvasRef} aria-label={name} />
    </div>
  );
}
