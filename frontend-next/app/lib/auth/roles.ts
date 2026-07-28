export const APP_ROLES = ["admin", "secretaria", "medico", "espirometrista"] as const;

export type AppRole = (typeof APP_ROLES)[number];

export const ROLE_LABEL: Record<AppRole, string> = {
  admin: "Administrador",
  secretaria: "Secretaria",
  medico: "Medico",
  espirometrista: "Espirometrista",
};
