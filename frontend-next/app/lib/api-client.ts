"use client";

/**
 * Calls the Django-backed API and handles an expired session consistently.
 * Without this, a Django login redirect is treated as an empty JSON response
 * by the Next screens, which looks like missing clinical data.
 */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, { credentials: "same-origin", ...init });
  if (response.status === 401 && typeof window !== "undefined") {
    const next = `${window.location.pathname}${window.location.search}`;
    window.location.assign(`/login/?next=${encodeURIComponent(next)}`);
    throw new Error("Tu sesion vencio. Redirigiendo al inicio de sesion...");
  }
  return response;
}
