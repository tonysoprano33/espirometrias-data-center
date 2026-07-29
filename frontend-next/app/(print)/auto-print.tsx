"use client";

import { useEffect } from "react";

export function AutoPrint({ enabled }: { enabled: boolean }) {
  useEffect(() => {
    if (!enabled) return;

    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      const pending = document.querySelector("[data-print-loading='true']");
      if (!pending || Date.now() - startedAt > 20_000) {
        window.clearInterval(timer);
        window.setTimeout(() => window.print(), 250);
      }
    }, 120);
    return () => window.clearInterval(timer);
  }, [enabled]);

  return null;
}
