-- Next clinical schema. It intentionally coexists with Django's clinic_* tables
-- until the final cutover has been tested and approved.

create extension if not exists pgcrypto;

do $$ begin
  create type public.next_study_type as enum ('Ciclometria', 'Espirometria');
exception when duplicate_object then null;
end $$;
do $$ begin
  create type public.next_coverage_type as enum ('Mutual', 'Particular');
exception when duplicate_object then null;
end $$;
do $$ begin
  create type public.next_attendance_status as enum ('no_llego', 'esperando', 'atendido');
exception when duplicate_object then null;
end $$;
do $$ begin
  create type public.next_workflow_status as enum ('pendiente', 'cargada', 'revisada', 'informe_generado', 'entregada');
exception when duplicate_object then null;
end $$;
do $$ begin
  create type public.next_respiratory_pattern as enum ('Normal', 'Obstructivo', 'Restrictivo', 'Mixto');
exception when duplicate_object then null;
end $$;
do $$ begin
  create type public.next_severity_grade as enum ('Leve', 'Moderada', 'Moderadamente severa', 'Severa');
exception when duplicate_object then null;
end $$;
do $$ begin
  create type public.next_attachment_kind as enum ('pdf_resultado', 'foto_resultado', 'informe_docx', 'informe_pdf', 'otro');
exception when duplicate_object then null;
end $$;
do $$ begin
  create type public.next_attachment_status as enum ('uploaded', 'extracting', 'detected', 'no_data', 'failed');
exception when duplicate_object then null;
end $$;
do $$ begin
  create type public.next_report_type as enum ('Espirometria', 'Completo', 'Mutual');
exception when duplicate_object then null;
end $$;

create table if not exists public.patients (
  id uuid primary key default gen_random_uuid(),
  legacy_django_id bigint unique,
  full_name text not null,
  full_name_normalized text not null default '',
  patient_code text not null default '',
  last_name text not null default '',
  first_name text not null default '',
  dni text,
  birth_date date,
  age_reported smallint check (age_reported between 0 and 130),
  gender text not null default '',
  ethnicity text not null default '',
  smoking_status text not null default '',
  patient_group text not null default '',
  height_cm smallint check (height_cm between 30 and 260),
  weight_kg numeric(6,2) check (weight_kg between 1 and 500),
  bmi numeric(6,2) check (bmi between 1 and 150),
  pack_years numeric(6,2) check (pack_years between 0 and 500),
  phone text not null default '',
  phone_normalized text not null default '',
  notes text not null default '',
  deleted_at timestamptz,
  deleted_by uuid references public.profiles(id) on delete set null,
  deletion_batch uuid,
  purge_after timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create unique index if not exists patients_active_dni_key
  on public.patients (dni) where dni is not null and deleted_at is null;
create index if not exists patients_name_search_idx on public.patients (full_name_normalized);
create index if not exists patients_phone_search_idx on public.patients (phone_normalized) where phone_normalized <> '';
create index if not exists patients_deleted_idx on public.patients (deleted_at) where deleted_at is not null;

create table if not exists public.referring_physicians (
  id uuid primary key default gen_random_uuid(),
  legacy_django_id bigint unique,
  full_name text not null,
  normalized_name text not null unique,
  is_default boolean not null default false,
  active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.encounters (
  id uuid primary key default gen_random_uuid(),
  legacy_django_id bigint unique,
  patient_id uuid not null references public.patients(id) on delete restrict,
  encounter_date date not null,
  encounter_time time,
  study_type public.next_study_type not null default 'Ciclometria',
  coverage_type public.next_coverage_type not null default 'Particular',
  coverage_name text not null default '',
  affiliate_number text not null default '',
  referring_physician_id uuid references public.referring_physicians(id) on delete set null,
  attendance_status public.next_attendance_status not null default 'no_llego',
  workflow_status public.next_workflow_status not null default 'cargada',
  attended_at timestamptz,
  waiting_started_at timestamptz,
  first_vitals_recorded_at timestamptz,
  discharged_at timestamptz,
  bronchodilator_administered_at timestamptz,
  bronchodilator_wait_minutes smallint not null default 10 check (bronchodilator_wait_minutes between 1 and 60),
  technician_notes text not null default '',
  medical_control_today boolean not null default false,
  validated_by uuid references public.profiles(id) on delete set null,
  validated_at timestamptz,
  created_by uuid references public.profiles(id) on delete set null,
  updated_by uuid references public.profiles(id) on delete set null,
  deleted_at timestamptz,
  deleted_by uuid references public.profiles(id) on delete set null,
  deletion_batch uuid,
  purge_after timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists encounters_active_date_time_idx
  on public.encounters (encounter_date, encounter_time, created_at)
  where deleted_at is null;
create index if not exists encounters_patient_date_idx
  on public.encounters (patient_id, encounter_date desc)
  where deleted_at is null;
create index if not exists encounters_workflow_date_idx
  on public.encounters (workflow_status, encounter_date)
  where deleted_at is null;
create index if not exists encounters_attendance_date_idx
  on public.encounters (attendance_status, encounter_date)
  where deleted_at is null;
create index if not exists encounters_mutual_date_idx
  on public.encounters (coverage_name, encounter_date)
  where coverage_type = 'Mutual' and deleted_at is null;

create table if not exists public.vital_signs (
  encounter_id uuid primary key references public.encounters(id) on delete cascade,
  so2_rest smallint check (so2_rest between 0 and 100),
  fc_rest smallint check (fc_rest between 0 and 300),
  ta_rest text not null default '',
  so2_post smallint check (so2_post between 0 and 100),
  fc_post smallint check (fc_post between 0 and 300),
  rest_recorded_at timestamptz,
  post_recorded_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.walk_tests (
  encounter_id uuid primary key references public.encounters(id) on delete cascade,
  distance_meters smallint not null default 200 check (distance_meters between 0 and 10000),
  completed boolean not null default true,
  stopped boolean not null default false,
  symptoms boolean not null default false,
  borg_final smallint not null default 1 check (borg_final between 0 and 10),
  minute_readings jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.walk_measurements (
  id uuid primary key default gen_random_uuid(),
  walk_test_id uuid not null references public.walk_tests(encounter_id) on delete cascade,
  minute smallint not null check (minute between 0 and 6),
  so2 smallint check (so2 between 0 and 100),
  fc smallint check (fc between 0 and 300),
  borg smallint check (borg between 0 and 10),
  source text not null default 'manual',
  unique (walk_test_id, minute)
);

create table if not exists public.spirometry_results (
  encounter_id uuid primary key references public.encounters(id) on delete cascade,
  respiratory_pattern public.next_respiratory_pattern,
  obstruction_grade public.next_severity_grade,
  restriction_grade public.next_severity_grade,
  bronchodilator_positive boolean not null default false,
  suggested_bronchodilator_positive boolean,
  suggested_bronchodilator_reason text not null default '',
  physician_comment text not null default '',
  measured_values jsonb not null default '{}'::jsonb,
  suggested_code text not null default '',
  suggested_probability smallint check (suggested_probability between 0 and 100),
  suggested_summary text not null default '',
  extracted_source text not null default '',
  finalised_by uuid references public.profiles(id) on delete set null,
  finalised_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.attachments (
  id uuid primary key default gen_random_uuid(),
  legacy_django_id bigint unique,
  encounter_id uuid not null references public.encounters(id) on delete cascade,
  file_kind public.next_attachment_kind not null,
  storage_bucket text not null default 'attachments',
  object_path text not null,
  original_name text not null,
  safe_name text not null,
  mime_type text not null default '',
  byte_size bigint check (byte_size >= 0),
  sha256 text not null default '',
  uploaded_by uuid references public.profiles(id) on delete set null,
  analysis_status public.next_attachment_status not null default 'uploaded',
  analysis_error text not null default '',
  analysis_attempted_at timestamptz,
  parsed_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (storage_bucket, object_path)
);
create index if not exists attachments_encounter_kind_idx
  on public.attachments (encounter_id, file_kind, created_at desc);

create table if not exists public.generated_reports (
  id uuid primary key default gen_random_uuid(),
  legacy_django_id bigint unique,
  encounter_id uuid not null references public.encounters(id) on delete cascade,
  report_type public.next_report_type not null,
  attachment_id uuid references public.attachments(id) on delete set null,
  generated_by uuid references public.profiles(id) on delete set null,
  generator_version text not null default '',
  source_snapshot jsonb not null default '{}'::jsonb,
  content_sha256 text not null default '',
  supersedes_id uuid references public.generated_reports(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index if not exists reports_encounter_created_idx
  on public.generated_reports (encounter_id, created_at desc);

create table if not exists public.clinical_notes (
  id uuid primary key default gen_random_uuid(),
  encounter_id uuid not null references public.encounters(id) on delete cascade,
  body text not null check (char_length(body) <= 2000),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.encounter_events (
  id uuid primary key default gen_random_uuid(),
  legacy_django_id bigint unique,
  encounter_id uuid not null references public.encounters(id) on delete cascade,
  patient_id uuid not null references public.patients(id) on delete restrict,
  actor_id uuid references public.profiles(id) on delete set null,
  legacy_actor_id bigint,
  event_type text not null,
  title text not null,
  details text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  before_data jsonb not null default '{}'::jsonb,
  after_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index if not exists encounter_events_encounter_created_idx
  on public.encounter_events (encounter_id, created_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

do $$
declare table_name text;
begin
  foreach table_name in array array[
    'patients', 'referring_physicians', 'encounters', 'vital_signs', 'walk_tests',
    'spirometry_results', 'attachments', 'generated_reports', 'clinical_notes'
  ] loop
    execute format('drop trigger if exists %I on public.%I', table_name || '_set_updated_at', table_name);
    execute format('create trigger %I before update on public.%I for each row execute procedure public.set_updated_at()', table_name || '_set_updated_at', table_name);
  end loop;
end $$;

create or replace function private.has_app_role(allowed_roles public.app_role[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select private.current_app_role() = any(allowed_roles);
$$;
revoke all on function private.has_app_role(public.app_role[]) from public;
grant execute on function private.has_app_role(public.app_role[]) to authenticated;

alter table public.patients enable row level security;
alter table public.referring_physicians enable row level security;
alter table public.encounters enable row level security;
alter table public.vital_signs enable row level security;
alter table public.walk_tests enable row level security;
alter table public.walk_measurements enable row level security;
alter table public.spirometry_results enable row level security;
alter table public.attachments enable row level security;
alter table public.generated_reports enable row level security;
alter table public.clinical_notes enable row level security;
alter table public.encounter_events enable row level security;

-- Initial read policies. Mutations are deliberately withheld until their Server
-- Actions are implemented and tested, preventing an unfinished client from
-- writing clinical data through PostgREST.
create policy "patients_read_clinical_roles" on public.patients for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "physicians_read_clinical_roles" on public.referring_physicians for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "encounters_read_clinical_roles" on public.encounters for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "vitals_read_clinical_roles" on public.vital_signs for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "walk_tests_read_clinical_roles" on public.walk_tests for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "walk_measurements_read_clinical_roles" on public.walk_measurements for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "results_read_clinical_roles" on public.spirometry_results for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "attachments_read_clinical_roles" on public.attachments for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "reports_read_clinical_roles" on public.generated_reports for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "notes_read_clinical_roles" on public.clinical_notes for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[]));
create policy "events_read_operational_roles" on public.encounter_events for select to authenticated
  using (private.has_app_role(array['admin', 'espirometrista']::public.app_role[]));
