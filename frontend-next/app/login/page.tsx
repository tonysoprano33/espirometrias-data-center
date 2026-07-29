"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { createClient } from "../lib/supabase/client";

const SESSION_OPTIONS = [
  { value: "espirometro", label: "Espirometria" },
  { value: "secretaria", label: "Secretaria" },
  { value: "medico", label: "Medico" },
] as const;

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="auth-shell"><p>Preparando acceso...</p></main>}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [sessionRole, setSessionRole] = useState<(typeof SESSION_OPTIONS)[number]["value"]>("espirometro");
  const [password, setPassword] = useState("");
  const [keepSignedIn, setKeepSignedIn] = useState(true);
  const [message, setMessage] = useState(searchParams.get("error") === "profile"
    ? "Tu cuenta no tiene un perfil activo en este sistema."
    : "");
  const [submitting, setSubmitting] = useState(false);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    try {
      const supabase = createClient(keepSignedIn);
      const email = `${sessionRole}@clinica-espiro.local`;
      const { error } = await supabase.auth.signInWithPassword({ email, password: password.trim() });
      if (error) throw error;
      router.replace(searchParams.get("next") || "/agenda");
      router.refresh();
    } catch (error) {
      const detail = error instanceof Error ? error.message : "";
      setMessage(detail === "Invalid login credentials"
        ? "Contraseña incorrecta para la sesion seleccionada."
        : detail || "No se pudo iniciar sesion.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <form className="auth-card" onSubmit={signIn}>
        <p className="eyebrow">Clinica Espiro · Acceso</p>
        <h1>Iniciar sesion</h1>
        <p>Elegí la sesión de trabajo y usá la clave asignada a ese rol.</p>
        <label>
          Sesion
          <select value={sessionRole} onChange={(event) => setSessionRole(event.target.value as typeof sessionRole)}>
            {SESSION_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>
          Contraseña
          <input
            type="password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
          />
        </label>
        <label className="auth-remember">
          <input type="checkbox" checked={keepSignedIn} onChange={(event) => setKeepSignedIn(event.target.checked)} />
          Mantener la sesión iniciada en este navegador
        </label>
        {message && <p className="auth-message" role="alert">{message}</p>}
        <button disabled={submitting}>{submitting ? "Ingresando..." : "Ingresar"}</button>
      </form>
    </main>
  );
}
