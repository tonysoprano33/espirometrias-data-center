# Migracion completa a Next.js + Supabase

**Estado:** propuesta de Fase 1.  
**Fecha:** 2026-07-28.  
**Alcance de este documento:** analisis y planificacion. No autoriza cambios de codigo, datos, DNS, Vercel, Supabase ni produccion.

## Principios y limite de la migracion

La aplicacion actual es clinica y se usa durante la jornada laboral. La migracion debe priorizar continuidad operativa y fidelidad de los informes por encima de la velocidad de reescritura. Django quedara solo como sistema de rollback temporal durante el corte controlado; se retirara cuando Next haya superado la validacion funcional, de datos y de impresion definida en este documento.

Arquitectura objetivo:

- Next.js 16 con App Router, React y TypeScript.
- Vercel para frontend, Server Actions y Route Handlers.
- Supabase PostgreSQL como unica base de datos de aplicacion.
- Supabase Auth para cuentas individuales y sesiones.
- Supabase Storage privado para PDFs, imagenes e informes.
- RLS para aislamiento de datos y permisos de rol.
- Zod, React Hook Form, Vitest y Playwright.

No se incorporara Prisma. El cliente tipado de Supabase y SQL versionado son suficientes y evitan una capa ORM duplicada.

---

## 1. Inventario del sistema actual

### 1.1 Pantallas y flujos existentes

| Modulo actual | Uso real | Rol principal | Estado en la migracion |
| --- | --- | --- | --- |
| Inicio / agenda | Alta rapida, editar fila, signos, asistencia, control medico, importacion DrApp | Secretaria y espirometrista | Migrar como `agenda` con acciones explicitas de guardar, sin recarga ni salto de scroll. |
| Calendario | Dias con pacientes, navegacion mensual y acceso al dia | Espirometrista | Migrar como lectura rapida server-rendered. |
| Estadisticas | Mes, mutuales, perfiles, resultados, tiempos operativos y cohortes | Espirometrista | Migrar con consultas agregadas indexadas y filtros por periodo. |
| Pacientes | Busqueda, ficha, historial, adjuntos, comparacion longitudinal y editar | Espirometrista | Migrar como ficha clinica con paginacion y acciones auditadas. |
| Papelera | Restaurar o purgar pacientes y atenciones eliminadas | Espirometrista / administrador | Mantener soft delete y retencion de 30 dias. |
| Revision medica | Cola de PDFs, sugerencia, resultado final, navegacion anterior/siguiente, notas y control medico | Medico | Migrar como flujo simplificado de diagnostico, sin acciones administrativas. |
| Ficha de atencion | Ciclometria, espirometria, signos, caminata, broncodilatador, informes | Espirometrista | Migrar por componentes clinicos independientes. |
| Impresion individual y diaria | Informes DOCX/PDF, particular, mutual y completo | Espirometrista | Migrar despues de validar formato con muestras doradas. |
| Login y modos | Cuentas fijas y cambio de modo | Todos | Reemplazar por Supabase Auth y rol persistente por usuario. |
| Administracion Django | Operacion tecnica interna | Administrador | Reemplazar por una configuracion acotada; no exponer Django admin en el producto final. |

### 1.2 Modelos Django actuales

| Modelo | Datos y responsabilidad | Destino propuesto |
| --- | --- | --- |
| `Patient` | Identidad, DNI, telefono, datos demograficos, tabaquismo, medidas y soft delete | `patients` |
| `ReferringPhysician` | Medico derivante, activo y predeterminado | `referring_physicians` |
| `Encounter` | Atencion, fecha/hora, estudio, cobertura/mutual, asistencia, tiempos operativos, notas y papelera | `encounters` |
| `VitalSigns` | SO2/FC en reposo y post | `vital_signs` |
| `WalkTest` | Caminata, distancia, incidencias, Borg y lecturas por minuto JSON | `walk_tests` y `walk_measurements` |
| `SpirometryResult` | Patron, grados, sugerencia, valores extraidos y broncodilatador | `spirometry_results` |
| `Attachment` | PDF/foto/informe, nombre, tipo, usuario y estado de lectura | `attachments` + bucket privado |
| `GeneratedReport` | Tipo, version, hash, snapshot y reemplazos | `generated_reports` |
| `EncounterEvent` | Trazabilidad de cambios e importaciones | `encounter_events` |

Modelos auxiliares actuales: `TimeStampedModel` y `ActiveManager`. El segundo filtra eliminados; en PostgreSQL se reemplaza por `deleted_at is null` en vistas, consultas y RLS.

### 1.3 Estados, reglas clinicas y operaciones existentes

- Estudios: `Ciclometria` y `Espirometria`.
- Cobertura: `Particular` o `Mutual`, con `coverage_name` y numero de afiliado.
- Estados de atencion: pendiente, cargada, revisada por medico, informe generado, entregada y no llego; ademas la UI maneja esperando/atendido.
- Resultados: normal, obstructivo, restrictivo y mixto, con grados leve, moderada, moderadamente severa y severa.
- Informes: espirometria, completo y mutual.
- Caminata: conserva lecturas reales por minuto, distancia, incidencias y Borg final. La representacion de las filas debe conservar la regla actual aprobada, no rellenar huecos de manera inesperada.
- Operacion: espera, primer registro de signos, alta, y recordatorio de broncodilatador.
- Identidad: DNI es la clave principal. Telefono, fecha de nacimiento, obra social y nombre normalizado son evidencia secundaria; un mismo nombre no bloquea una nueva visita.

### 1.4 Endpoints y acciones Django actuales

El backend actual tiene 45 endpoints/rutas de negocio. Se migran por capacidad, no como una copia literal de URLs:

| Grupo | Rutas Django actuales | Sustitucion Next |
| --- | --- | --- |
| Agenda | `/`, `/agenda/estado/`, `/api/v1/agenda/hoy/`, `nueva`, `asistencia`, `signos`, `campo`, `control-medico` | Pagina `agenda`, Server Actions por operacion y un endpoint de lectura solo si Realtime lo necesita. |
| Importacion DrApp | Logica dentro de dashboard y helpers de OCR/texto | Action de previsualizacion y Action de confirmacion, ambas con deduplicacion. |
| Calendario/estadistica | `/calendario/`, `/estadistica/` y sus APIs | RSC de lectura con filtros en `searchParams`. |
| Pacientes | Lista, detalle, crear, editar, eliminar y APIs | Paginas y Server Actions protegidas; pagina de historial. |
| Papelera | Vista/API/accion | Pagina protegida, restauracion y purga mediante acciones administrativas. |
| Revision medica | Lista, cola, detalle, archivo, resultado y API | Paginas de cola/detalle y acciones separadas para upload, sugerencia y resultado final. |
| Informes | imprimir atencion, imprimir dia, generar informe, informe desde paciente | Route Handler para descarga/imprimir y Server Action para generar artefactos. |

### 1.5 Dependencias actuales

| Dependencia | Uso actual | Decicion de migracion |
| --- | --- | --- |
| Django 6 | vistas, formularios, sesiones, ORM, admin | Retirar al finalizar el corte. |
| psycopg | acceso PostgreSQL | Retirar del runtime de la app Next. |
| python-docx | DOCX de informes | Reimplementar con `docx` en TypeScript o un generador aislado, solo despues de pruebas visuales. |
| pypdfium2 | render/extraccion de PDF | No incluir en el bundle principal de Next. |
| RapidOCR + OpenCV | OCR de PDFs/fotos | Desacoplar; no ejecutar dentro de login ni ruta critica. |
| Whitenoise | estaticos Django | Retirar con Django. |

El OCR actual explica buena parte del peso y fragilidad del runtime Python. En Vercel hay limites de tamano para funciones Python; por eso no debe trasladarse de forma directa al runtime principal de Next.

### 1.6 Autenticacion y roles actuales

Hoy se usan sesiones Django y cuentas fijas: secretaria, medico, espirometro/espirometrista y administrador. Los permisos principales son gestionar agenda, revision medica, estadisticas y purga clinica. La UI oculta opciones segun modo, pero el backend tambien valida permisos.

Destino: cuentas individuales en Supabase Auth con perfil y rol persistente. No se mantendra una contrasena compartida en produccion. Cada persona tendra usuario propio, recuperacion de acceso y baja/activacion sin tocar codigo.

### 1.7 OCR, PDFs e informes actuales

- `pdf_intake.py` intenta extraer texto del PDF, renderiza paginas y usa RapidOCR como respaldo.
- Se detectan identidad, datos antropometricos, FVC, FEV1, FEV1/FVC, sugerencia de patron y posible broncodilatador positivo.
- El resultado final sigue siendo decision del medico; una sugerencia no debe autocompletarlo.
- Los adjuntos conservan estado `uploaded`, `detected` o `failed`, detalle de error y fecha de intento.
- `services.py` arma DOCX, caminata, informe de mutual, PDF/impresion y snapshots de fuente con SHA-256.

### 1.8 Pruebas existentes

El proyecto ya cubre validacion de archivos, nombres, edad, orden de agenda, informes, broncodilatador, coberturas, importacion DrApp, guardado inline, duplicados, revision, notas, PDF, impresion, papelera, calendario, estadisticas, busqueda y accesos clinicos. Estas pruebas son una base funcional valiosa y deben convertirse en contratos de la nueva aplicacion, no descartarse.

---

## 2. Mapa de migracion: Django a Next.js + Supabase

```text
Django models + PostgreSQL actual        ->  Supabase PostgreSQL + migraciones SQL versionadas
Django session/login                     ->  Supabase Auth + profiles + rol en servidor
Django views/forms                       ->  Server Components + Server Actions + React Hook Form/Zod
Django JSON APIs                         ->  Actions; Route Handlers solo para archivos, descarga o integraciones
Django FileField/Supabase adapter        ->  Supabase Storage privado + signed URLs de corta vida
python-docx                              ->  generador TypeScript validado con muestras doradas
pypdfium2/RapidOCR dentro del runtime    ->  pipeline opcional y desacoplado de lectura/OCR
Django templates                         ->  componentes React por dominio
Django permissions                       ->  RLS + validacion de autorizacion en Server Actions
soft delete Django                       ->  deleted_at/deleted_by/purge_after + RLS
EncounterEvent                           ->  audit log append-only
```

No se trasladara la redireccion/proxy actual de `frontend-next` a Django. Esa implementacion es solo una maqueta: el middleware redirige todas las rutas al backend Django y el Route Handler API actua como proxy. La migracion real reemplaza esos proxies por consultas y acciones propias.

---

## 3. Esquema PostgreSQL propuesto

### 3.1 Convenciones

- UUID como clave primaria nueva; `legacy_django_id` opcional y unico durante migracion para rastrear origen.
- Timestamps `timestamptz` en UTC; presentar America/Argentina/Buenos_Aires en UI.
- `created_at`, `updated_at`, `created_by`, `updated_by` donde sea clinicamente relevante.
- Soft delete con `deleted_at`, `deleted_by`, `deletion_batch` y `purge_after = deleted_at + interval '30 days'`.
- DNI normalizado solo con digitos y almacenado como texto; mostrar con puntos en UI. Nunca usar numero para evitar perder ceros iniciales.
- `coverage_name` se preserva aun cuando `coverage_type = mutual`; sirve para estadisticas por obra social.

### 3.2 Tablas principales

| Tabla | Campos principales | Relaciones y restricciones |
| --- | --- | --- |
| `profiles` | `id uuid pk references auth.users`, `display_name`, `role`, `is_active`, timestamps | Rol enum: `admin`, `secretaria`, `medico`, `espirometrista`. Solo admin puede modificar roles. |
| `patients` | identidad, `dni`, telefono, fecha nacimiento, sexo, tabaquismo, medidas, notas administrativas, soft delete | Indice unico parcial por DNI activo; no imponer unicidad por nombre. |
| `referring_physicians` | `full_name`, `normalized_name`, `is_default`, `active` | Unico por `normalized_name`; permite busqueda incremental. |
| `encounters` | paciente, fecha, hora, estudio, cobertura/tipo, mutual, afiliado, asistencia, estado de flujo, control medico, tiempos, notas tecnicas, soft delete | FK a paciente y derivante. Una atencion no se mueve de fecha al editar cobertura. |
| `vital_signs` | `encounter_id unique`, SO2/FC/TA reposo y post, timestamps de captura | Checks SO2 0-100 y FC clinicamente razonable 0-300, permitiendo nulos. |
| `walk_tests` | `encounter_id unique`, distancia, completada, detencion, sintomas, Borg final | Check Borg 0-10. |
| `walk_measurements` | `walk_test_id`, minuto 0-6, SO2, FC, Borg, origen | Unique `(walk_test_id, minute)`; no rellenar lecturas manuales con valores inventados. |
| `spirometry_results` | patron final, grados, broncodilatador positivo, comentario, valores extraidos JSONB, sugerencia separada | Resultado final y sugerencia nunca comparten el mismo campo. |
| `attachments` | atencion, bucket/path, nombre original, nombre seguro, MIME, bytes, SHA-256, tipo, estado OCR, error, payload extraido | Path unico; no usar URL publica persistente. |
| `generated_reports` | atencion, tipo, version, snapshot JSONB, checksum, path, reemplaza | El snapshot permite regenerar/auditar una version historica. |
| `clinical_notes` | atencion, texto, creado por, visible para medico | Nota breve del espirometrista; el medico solo lee. |
| `encounter_events` | atencion, paciente, actor, tipo, titulo, metadata JSONB, before/after JSONB | Insert-only para auditoria. |

### 3.3 Indices requeridos

```sql
create unique index patients_active_dni_key
  on public.patients (dni)
  where dni is not null and deleted_at is null;

create index encounters_active_date_time_idx
  on public.encounters (encounter_date, encounter_time, created_at)
  where deleted_at is null;
create index encounters_patient_date_idx
  on public.encounters (patient_id, encounter_date desc)
  where deleted_at is null;
create index encounters_status_date_idx
  on public.encounters (workflow_status, encounter_date)
  where deleted_at is null;
create index encounters_coverage_date_idx
  on public.encounters (coverage_name, encounter_date)
  where deleted_at is null and coverage_type = 'mutual';
create index attachments_encounter_kind_idx
  on public.attachments (encounter_id, file_kind, created_at desc);
create index events_encounter_created_idx
  on public.encounter_events (encounter_id, created_at desc);
```

Agregar `pg_trgm` solo si las mediciones demuestran que la busqueda por nombre lo necesita; en ese caso, indice GIN sobre `normalized_name`. La busqueda primaria por DNI debe ser B-tree exacta.

### 3.4 Integridad y auditoria

- Triggers para `updated_at` y para rechazar actualizaciones destructivas de `encounter_events`.
- Acciones clinicas sensibles deben crear evento: alta, cambio de asistencia, signos guardados, PDF cargado, OCR completado/fallido, resultado medico, informe generado, restauracion y purga.
- El borrado permanente solo se permite despues de 30 dias y para administrador/espirometrista autorizado.
- Informes generados no se sobrescriben: una regeneracion crea una nueva version y enlaza `supersedes`.
- Un cambio de cobertura, derivante o nombre no debe crear otra atencion ni modificar fecha/hora historica.

---

## 4. Diseno de RLS y permisos

### 4.1 Regla general

Todas las tablas de `public` tendran RLS activado. Las operaciones clinicas pasan por Server Actions o Route Handlers que verifican sesion y rol en el servidor. El navegador nunca recibe una `service_role key` ni URLs de Storage publicas.

El rol se mantiene en `profiles` y se replica como claim controlado de Supabase (`app_metadata`) solo desde una funcion administrativa. La fuente de autorizacion sigue siendo el perfil consultado del lado servidor; ocultar un boton no es seguridad.

### 4.2 Matriz de permisos

| Recurso / accion | Admin | Secretaria | Medico | Espirometrista |
| --- | --- | --- | --- | --- |
| Agenda de hoy: leer | Si | Si | No | Si |
| Agenda de hoy: alta/asistencia/control | Si | Si | No | Si |
| Signos, caminata, broncodilatador y adjuntos | Si | No | No | Si |
| Resultado final medico | Si | No | Si | Si, solo si flujo aprobado actualmente lo permite |
| Leer PDF y datos clinicos para revision | Si | No | Si | Si |
| Notas del espirometrista | Si | Crear/editar no | Solo leer | Crear/editar |
| Pacientes completos e historial | Si | Solo datos minimos de agenda | Solo pacientes en revision | Si |
| Informes e impresion | Si | No | No | Si |
| Estadisticas | Si | No | No | Si |
| Papelera/purga | Si | No | No | Si, purga con confirmacion |
| Gestion de usuarios/roles | Si | No | No | No |

La secretaria no recibira datos clinicos innecesarios. El medico no podra reemplazar PDF, editar notas tecnicas ni gestionar papelera. El espirometrista conserva la operacion integral actual.

### 4.3 Politicas por tabla (diseno)

| Tabla | Lectura | Escritura |
| --- | --- | --- |
| `profiles` | Usuario propio; admin todos | Usuario actualiza solo datos no sensibles; admin roles/altas |
| `patients` | Admin/espirometrista completos; secretaria solo campos agenda; medico solo pacientes con atencion revisable | Server Action con rol; secretaria crea identidad minima, no datos clinicos |
| `encounters` | Segun matriz y `deleted_at is null` | Secretaria crea y actualiza asistencia/control; espirometrista clinico; medico solo resultado/revision |
| `vital_signs`, `walk_tests`, `walk_measurements` | Esppirometrista/admin; medico lectura de su revision | Solo espirometrista/admin |
| `spirometry_results` | Medico, espirometrista, admin | Medico finaliza; espirometrista conserva carga permitida y sugerencias separadas |
| `attachments`, `generated_reports` | Solo roles con acceso a la atencion | Upload/generacion por espirometrista/admin; medico no reemplaza archivo |
| `clinical_notes` | Medico/espirometrista/admin | Solo espirometrista/admin |
| `encounter_events` | Admin/espirometrista; medico solo eventos de su atencion si se requiere | Solo funciones/acciones servidoras, insert-only |
| Papelera | Admin/espirometrista sobre filas eliminadas | Restaurar/purgar solo roles autorizados |

Para evitar que una policy de fila permita cambiar columnas no autorizadas, las mutaciones se implementaran en RPCs SQL restringidos o Server Actions con lista blanca de campos. Ejemplo: la accion de secretaria acepta solamente `full_name`, `dni`, `encounter_date`, `time`, `study_type`, `coverage` y `medical_control_today`; nunca recibe ni actualiza resultados clinicos.

### 4.4 Storage

- Buckets privados: `clinical-attachments`, `generated-reports`, `migration-backups` (ultimo solo servidor).
- Path con UUID: `encounters/{encounter_uuid}/{attachment_uuid}/{safe_filename}`.
- Politicas de `storage.objects` basadas en rol y pertenencia de la atencion; no basadas en que el usuario adivine una URL.
- Descargas mediante signed URL de corta vida emitida por Route Handler autenticado.
- Validar extension permitida, MIME declarado, firma real, tamano, nombre seguro ASCII y hash SHA-256 antes de persistir.

Referencia: [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security) y [control de acceso a Storage](https://supabase.com/docs/guides/storage/security/access-control).

---

## 5. Arquitectura Next.js propuesta

```text
frontend-next/
  app/
    (auth)/login/page.tsx
    (app)/layout.tsx
    (app)/agenda/page.tsx
    (app)/calendario/page.tsx
    (app)/estadisticas/page.tsx
    (app)/pacientes/page.tsx
    (app)/pacientes/[patientId]/page.tsx
    (app)/papelera/page.tsx
    (app)/revision-medica/page.tsx
    (app)/revision-medica/[encounterId]/page.tsx
    api/files/[attachmentId]/download/route.ts
    api/reports/[reportId]/download/route.ts
    api/health/route.ts
  actions/
    agenda.ts
    patients.ts
    encounters.ts
    review.ts
    reports.ts
    attachments.ts
    recycle-bin.ts
  components/
    agenda/
    review/
    patients/
    reports/
    shared/
  lib/
    supabase/server.ts
    supabase/browser.ts
    auth/require-role.ts
    db/queries/
    db/mappers/
    validation/
    reports/
    files/
  hooks/
    use-agenda-realtime.ts
    use-debounced-value.ts
  types/
  tests/
    unit/
    integration/
    e2e/
  supabase/
    migrations/
    seed.sql
    tests/
```

Reglas de separacion:

- Server Components para lecturas iniciales y paginas con datos clinicos.
- Client Components solo para formularios, filtros, temporizadores y actualizaciones de UI.
- Server Actions para mutaciones internas autenticadas. Cada action usa Zod, autentica, autoriza, crea evento y revalida solo el segmento afectado.
- Route Handlers solo cuando se necesita respuesta binaria, signed URL, webhook, health check o integracion externa. No crear una API REST paralela para cada formulario.
- `lib/db/queries` no conoce React; `actions` no contiene SQL ni JSX; componentes no conocen claves de Supabase.

Para auth SSR se utilizara el patron oficial de clientes browser/server y renovacion de cookies de Supabase: [Supabase Auth con Next.js](https://supabase.com/docs/guides/auth/server-side/nextjs).

---

## 6. OCR y lectura de PDF

### Estado actual y riesgo

El OCR funciona dentro del backend Python usando `pypdfium2`, RapidOCR y OpenCV. Es funcionalmente util, pero su peso y dependencias nativas elevan mucho el artefacto y pueden romper un despliegue de Vercel. Tampoco debe impedir login, agenda, generacion de informes o carga manual de resultado.

### Decision propuesta

**No migrar RapidOCR/Python al runtime principal de Next.** El pipeline final queda desacoplado y con estados visibles:

`subido -> extrayendo -> datos_detectados | sin_datos | fallo_reintentable`

Fase inicial:

1. Cargar el adjunto de manera segura a Storage.
2. Extraer texto solo si el PDF tiene capa textual mediante una dependencia JavaScript liviana o procesamiento cliente opcional.
3. Parsear campos con funciones TypeScript puras y conservar `parsed_data` + fuente de lectura.
4. Si no hay datos, dejar la carga disponible y permitir ingreso manual; nunca devolver 500 por OCR.

Fase posterior, solo si las pruebas muestran que hace falta OCR de imagen:

- Agregar un worker dedicado/cola fuera de las rutas criticas. Puede ser un servicio Python aislado, pero no backend principal ni requisito de arranque de Next.
- El worker recibe una URL firmada de un objeto, procesa, devuelve JSON validado y actualiza estado; no maneja sesiones ni UI.
- Reintento manual y registro de error por archivo.

El analisis automatico sera siempre ayuda de lectura, no diagnostico. El resultado final solo se guarda al confirmar el medico/espirometrista segun el flujo aprobado.

---

## 7. Fases de migracion y puertas de aprobacion

Cada fase termina con pruebas, demostracion en preview y aprobacion explicita. No se avanza sola.

### Fase 0 - Respaldo y linea de base

- Exportar PostgreSQL actual con `pg_dump` y verificar restauracion en entorno aislado.
- Inventariar objetos Storage: path, bytes, hash y relacion con adjunto.
- Congelar una lista de informes de referencia: particular, mutual, completo, caminata, patron mixto, broncodilatador, Borg y casos sin PDF.
- Registrar conteos por tabla y checksums de datos clinicos.
- Etiquetar el commit Django funcional y confirmar que Vercel actual puede volver a ese commit.

**Criterio de salida:** backup restaurable, inventario firmado y muestras de impresion aprobadas.

### Fase 1 - Base Next aislada y autenticacion (preview)

- Reemplazar la maqueta/proxy por shell Next real solo en preview.
- Configurar Supabase Auth, perfiles y RLS en un proyecto/esquema de staging.
- Implementar login, layout por rol y health check, sin pacientes reales ni escritura productiva.

**Rollback:** eliminar el preview; produccion Django no se toca.

### Fase 2 - Esquema y migracion de datos de ensayo

- Crear SQL versionado en Supabase staging.
- Migrar una copia anonimizada o controlada de datos, incluyendo adjuntos con hashes.
- Comparar conteos, DNI, atenciones, estados, PDFs e informes.

**Rollback:** descartar staging y repetir desde backup; no hay escritura en produccion.

### Fase 3 - Lecturas funcionales en preview

- Calendario, estadisticas, pacientes, historial y revision medica en modo solo lectura.
- Comparar resultados de consultas Django vs Next para misma fecha/paciente.
- Validar rol secretaria/medico/espirometrista con cuentas de prueba.

**Rollback:** preview vuelve a mostrar mensaje de mantenimiento; Django continua siendo fuente de verdad.

### Fase 4 - Mutaciones de bajo riesgo

- Alta de paciente, agenda, asistencia, signos, notas y control medico en staging.
- Deteccion de duplicados basada en DNI primero y datos secundarios como evidencia, sin bloquear visitas validas.
- Papelera y restauracion de ensayo.

**Rollback:** truncar staging y repetir pruebas; no hay corte productivo.

### Fase 5 - Adjuntos, OCR y revision

- Upload privado, validacion de archivo, estado de lectura, sugerencia y resultado final.
- El OCR se habilita como capacidad opcional; ningun fallo impide guardar PDF o resultado manual.

**Rollback:** desactivar solo el worker OCR; el resto sigue operativo.

### Fase 6 - Informes e impresion

- Reimplementar el generador con snapshots de entrada.
- Comparar visualmente DOCX/PDF/impresion contra muestras doradas aprobadas.
- Ejecutar pruebas de impresion individual, mutual, completo y dia entero.

**Rollback:** seguir generando desde Django durante el periodo paralelo; no cortar hasta igualdad funcional aprobada.

### Fase 7 - Migracion productiva y corte controlado

- Ventana de mantenimiento anunciada.
- Backup final, importacion incremental desde el ultimo corte, validacion de conteos y hashes.
- Next pasa a produccion; Django queda en modo solo lectura interno por un periodo acotado (por ejemplo 30 dias), sin nuevas operaciones.
- Monitorear errores, descargas, RLS y tiempo de carga.

**Criterio de retiro de Django:** todos los flujos pasan, cero discrepancias de datos pendientes, informes validados, rollback probado y aprobacion explicita.

---

## 8. Plan de rollback

1. Mantener el dominio productivo apuntando a la version Django hasta Fase 7.
2. Conservar etiqueta Git y variables de entorno del ultimo despliegue Django funcional.
3. Antes de corte: backup final de PostgreSQL + manifiesto de Storage + version de schema.
4. Durante corte: registrar hora, usuario y lote de importacion; no permitir doble escritura entre ambos sistemas.
5. Si falla un flujo critico (login, agenda, PDF, informe, impresion, datos clinicos), revertir el alias/deployment a Django y bloquear escrituras Next.
6. Si hubo escrituras Next antes del rollback, exportarlas como lote auditable y conciliarlas antes de reabrir Django para evitar perdida o duplicacion.
7. Restaurar objetos Storage solo desde manifiesto/hash, nunca por nombres manuales.

El rollback es temporal y probado. No contradice el objetivo de retirar Django: evita que una migracion incompleta afecte la atencion clinica.

---

## 9. Plan de pruebas

### 9.1 Unitarias (Vitest)

- Formateo/normalizacion de DNI, telefono, nombre y medico derivante.
- Reglas de deteccion de duplicado: DNI exacto, nombre igual con DNI distinto, telefono/fecha nacimiento coincidente, nueva visita.
- Validacion Zod de pacientes, signos, caminata, resultados y archivos.
- Calculo de tiempos espera -> primer signo -> alta.
- Borg y filas de caminata para minutos 0..6, incluyendo default y valores manuales.
- Texto de informes: normal, obstructivo, restrictivo y mixto; broncodilatador y mutual.
- Estado de archivo y transiciones permitidas.
- Formateo de cobertura, DNI e informe de medicos `Dr.`/`Dra.`.

### 9.2 Integracion (Supabase local/staging)

- RLS por cada rol y tabla; validar que el navegador no puede leer adjuntos ajenos ni escribir resultados como secretaria.
- Server Actions rechazan campos no permitidos aunque se manipule el request.
- Soft delete, restauracion por lote, retencion de 30 dias y purga autorizada.
- Versionado de informes y hashes/snapshots.
- Upload: PDF valido, imagen valida, extension falsa, MIME falso, archivo grande, nombre con espacios/tilde/ñ, archivo vacio y descarga firmada.
- Migracion: conteos, DNI, fecha/hora, cobertura, adjuntos, reportes y eventos coinciden con Django.

### 9.3 E2E (Playwright)

- Login/logout por Secretaria, Medico y Espirometrista; sesion persiste al recargar.
- Secretaria agrega paciente hoy, marca esperando/control y la agenda de espirometria se actualiza sin mover scroll.
- Espirometrista carga signos reposo/post solo al presionar Guardar, sin recargar ni perder foco.
- Flujo de broncodilatador y temporizador solo como ayuda visual.
- Carga de PDF, estado de lectura, fallo recuperable, sugerencia sin autocompletar resultado final.
- Medico abre cola, lee PDF, ve notas/control, elige resultado, navega anterior/siguiente y pendiente baja solo al guardar resultado.
- Impresion individual particular, mutual, completo y de todo el dia con 10 escenarios: normal, obstructivo, restrictivo, mixto, broncodilatador positivo, Borg distintos, caminata incompleta, no llego y PDF faltante.
- Papelera restaura y purga segun plazo/rol.
- Busqueda clinica unificada, paginacion de pacientes y estadisticas por periodo/mutual.
- Responsive en notebook y mobile; sin overflow horizontal, botones criticos accesibles.

### 9.4 Pruebas manuales de aceptacion clinica

- El responsable clinico revisa textos de resultados, especialmente patron mixto y referencia a pequenas vias aereas.
- Se comparan informes impresos contra los DOCX/PDF de referencia pixel a pixel o por checklist tipografico.
- Se valida que el resultado sugerido nunca se transforma solo en resultado medico.
- Se valida que ninguna sugerencia automatica se presenta como diagnostico definitivo.

---

## 10. Optimizacion, rendimiento y seguridad

### Rendimiento

- RSC para cargar agenda, calendario, estadistica y ficha en servidor; enviar al navegador solo componentes interactivos.
- Paginacion por defecto de 20 pacientes y busqueda indexada; no cargar historiales completos en listas.
- Consultas agregadas de estadistica en SQL con indices por fecha, cobertura y estado; cache por periodo invalidada al cambiar una atencion.
- Usar `revalidatePath` o tags granulares despues de una mutacion; no refrescar toda la pagina ni usar `window.location`.
- Supabase Realtime solo para agenda del dia y cambios de asistencia, con suscripcion limitada por fecha; no usar polling continuo.
- Lazy load de previsualizacion PDF, OCR, generador pesado y graficos. La cola medica muestra miniatura/metadata antes que un PDF completo.
- Medir Web Vitals y tiempos de Server Actions antes/despues de cada fase.

### Seguridad

- RLS en todas las tablas y Storage privado.
- Claves secretas solo en Vercel server-side; `NEXT_PUBLIC_*` solo para URL y anon/publishable key con RLS activo.
- Validacion de input en servidor con Zod y limites de payload.
- CSP, cookies seguras, CSRF inherente de actions/sesion y auditoria de operaciones clinicas.
- Logs sin DNI, PDFs, nombres completos ni contenido clinico; usar IDs de correlacion.
- Backups cifrados y politica de retencion definida con la clinica.
- Ninguna clave compartida se incluye en Git, screenshots, codigo cliente o documentos.

---

## 11. Analisis UX/UI (sin cambios en esta fase)

### Lo que conviene preservar

- Tres experiencias simples: Secretaria, Medico y Espirometrista.
- Revision medica centrada en PDF, resultado final, navegacion de pendientes y notas de solo lectura.
- Colores de estado semanticos: gris sin atender/PDF, naranja para revisar, verde resuelto. Un color no debe significar dos estados.
- Imprimir como accion prioritaria en operacion diaria.
- Vista compacta de agenda para notebook, pero con controles accesibles y sin zoom forzado.

### Mejoras propuestas para la futura implementacion

- Guardado explicito por grupo de signos y feedback local, sin salto a la parte superior ni sobrescribir texto mientras se escribe.
- Un solo patron de accion por campo: seleccionar/guardar, no autoguardados solapados.
- Agenda secretaria: alta arriba, estados grandes y legibles, hora/DNI/nombre con jerarquia visual; ocultar campos clinicos que no necesita.
- Medico: boton de siguiente/anterior siempre visible, prioridad visual a pendiente y control medico hoy; ocultar reemplazo de PDF, carga de archivos y edicion tecnica.
- Espirometrista: usar ancho completo, reducir espacio de resultado y eliminar repeticion de estado.
- Ficha de paciente: comparacion primero/medio/ultimo con datos reales, no inferencias exageradas.
- Estados de adjunto legibles: subido, leyendo, datos detectados, sin datos, fallo/reintentar.

No se cambia UI durante Fase 1. Estas decisiones se prototipan en preview y se validan con usuarios reales antes de quedar fijas.

---

## 12. Referencia de mercado y valor diferencial

La revision de productos modernos de funcion pulmonar muestra patrones utiles: control de calidad, comparacion PRE/POST, worklists, integracion con historia clinica y reportes centralizados. Ejemplos: [NDD EasyOne Connect](https://nddmed.com/products/spirometry-software/easyone-connect/), [NDD EasyOne Sky](https://nddmed.com/products/spirometers/easyone-sky/) y [MIR Spirolab Plus](https://spirometry.com/en/products/spirolab-plus/).

La app no debe copiarlos. Puede diferenciarse con foco en la operacion local:

1. Flujo de agenda -> realizacion -> revision -> informe con estados que cualquier secretaria y medico entiendan de un vistazo.
2. Historial longitudinal por paciente con evidencia de cada visita, valores y PDF original.
3. Informes por mutual y particular con formato clinico validado por el centro.
4. Trazabilidad fuerte: version, snapshot, hash y, en una fase futura aprobada, QR verificable de informes.
5. Estadisticas operativas y clinicas: tiempos de espera, tiempos de atencion, mutual, cohorte, resultado y calidad de datos.
6. Importador DrApp robusto con previsualizacion, deduplicacion explicable y confirmacion antes de crear registros.
7. Lectura automatica asistida que no suplanta el juicio medico.

---

## Riesgos principales y mitigacion

| Riesgo | Mitigacion |
| --- | --- |
| Perdida o duplicacion de pacientes/atenciones | Backups, IDs legacy, conteos/hash, migracion por lote y sin doble escritura. |
| Informes visualmente distintos | Muestras doradas y aprobacion clinica antes del corte. |
| OCR rompe deploy/login | Pipeline desacoplado, estados de fallo y carga manual siempre disponible. |
| Fuga de PDFs o datos clinicos | Storage privado, signed URLs, RLS, auditoria y secretos solo server-side. |
| Rol visible pero no seguro | Autorizacion en RLS y Server Actions, no solo ocultar botones. |
| Corte durante jornada | Ventana planificada, rollback inmediato y Django temporalmente solo lectura. |
| Rendimiento peor | Baseline de metricas, queries indexadas, carga parcial y pruebas de notebook/mobile. |

---

## Aprobacion requerida antes de Fase 2

Antes de implementar cualquier codigo de migracion se debe aprobar:

1. El esquema y matriz de permisos.
2. La estrategia de cuentas individuales Supabase Auth.
3. El alcance inicial de OCR (sin worker pesado en la primera entrega).
4. Las muestras de informes que se usarán como contrato visual.
5. La existencia de staging y un backup restaurable.

Con esa aprobacion, **Fase 2** implementara solamente la base aislada de Next/Supabase en preview. No se cambiara produccion ni se eliminara Django hasta superar todas las puertas de validacion anteriores.
