# Clinica automatizador espiro

MVP web para agenda, carga de estudios respiratorios, clasificacion medica y futura integracion con el motor de informes de `E:\espiro`.

## Stack

- Python
- Django
- SQLite en desarrollo
- PostgreSQL / Supabase en nube

## Como correr

1. Instalar dependencias:

```powershell
python -m pip install -r requirements.txt
```

2. Ejecutar migraciones:

```powershell
python src/manage.py migrate
```

3. Crear usuario administrador:

```powershell
python src/manage.py createsuperuser
```

4. Levantar servidor:

```powershell
python src/manage.py runserver
```

## Variables de entorno

La app acepta dos formas de conectar la base:

1. `DATABASE_URL` o `POSTGRES_URL`:

```env
DATABASE_URL=postgresql://postgres.[TU_PROYECTO]:[TU_PASSWORD]@[POOLER_HOST]:5432/postgres?sslmode=require
```

La integracion de Supabase en Vercel suele inyectar `POSTGRES_URL`, por lo que la app acepta ambos nombres.

Importante: el host directo de Supabase (`db.[TU_PROYECTO].supabase.co`) usa IPv6 por defecto. Si tu red o plataforma no soporta IPv6, usa la URL de `Session Pooler` de Supabase como `DATABASE_URL`.

2. Variables separadas:

- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `DB_SSLMODE`

Tambien reconoce las variables que suele crear Vercel al conectar Supabase:

- `POSTGRES_DATABASE`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`

Si esas variables vienen incompletas, por ejemplo `POSTGRES_PASSWORD=""`, en desarrollo la app vuelve a SQLite. Para exigir PostgreSQL y fallar con un error claro, define:

```env
REQUIRE_DATABASE=True
```

Si no existen, usa `SQLite`.

Para desarrollo local con Vercel, tambien podes traer secretos a `.env.local`:

```powershell
vercel env pull .env.local --yes
```

La configuracion de Django carga `.env` y luego `.env.local`, asi que si ahi definis `DATABASE_URL` la app usara Supabase automaticamente.

Para deploy tambien conviene definir:

- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `SECURE_SSL_REDIRECT=True`
- `SESSION_COOKIE_SECURE=True`
- `CSRF_COOKIE_SECURE=True`

En desarrollo, la base y los archivos subidos se guardan por defecto en:

`C:\Users\Tony\AppData\Local\ClinicaEspiro`

## Alcance actual

- login
- agenda operativa diaria
- pacientes
- trazabilidad por eventos
- repositorio documental por paciente
- alertas operativas y estadisticas clinicas
- signos vitales
- datos de caminata
- clasificacion respiratoria
- upload simple de PDF

## Proximo paso

Conectar el backend con la logica real de generacion de informes que hoy existe en `E:\espiro`.
