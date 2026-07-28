"use client";

export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="shell route-error"><section className="error-card"><p className="pill">No se pudo cargar esta pantalla</p><h1>La agenda sigue protegida</h1><p>El sistema no perdió tus datos. Probá nuevamente; si el problema continúa, volvé al inicio.</p><div><button className="button" type="button" onClick={reset}>Reintentar</button><a className="button alt" href="/agenda">Ir a Inicio</a></div></section></main>;
}
