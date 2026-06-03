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

1. `DATABASE_URL`:

```env
DATABASE_URL=postgresql://postgres:[TU_PASSWORD]@db.[TU_PROYECTO].supabase.co:5432/postgres?sslmode=require
```

2. Variables separadas:

- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `DB_SSLMODE`

Si no existen, usa `SQLite`.

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
