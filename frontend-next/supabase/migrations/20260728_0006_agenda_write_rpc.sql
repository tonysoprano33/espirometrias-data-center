-- First audited write path used by the Next.js agenda. A same DNI means the
-- same patient and creates a new encounter; a matching name alone is never
-- enough to merge records.

create or replace function private.normalize_search_text(value text)
returns text
language sql
immutable
set search_path = public
as $$
  select lower(regexp_replace(
    translate(coalesce(value, ''), 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun'),
    '[^a-zA-Z0-9]+', '', 'g'
  ));
$$;

revoke all on function private.normalize_search_text(text) from public;

create or replace function public.create_agenda_encounter(
  p_full_name text,
  p_dni text default null,
  p_encounter_date date default current_date,
  p_encounter_time time default null,
  p_study_type public.next_study_type default 'Ciclometria',
  p_coverage_type public.next_coverage_type default 'Particular',
  p_coverage_name text default '',
  p_medical_control_today boolean default false
)
returns table (
  encounter_id uuid,
  patient_id uuid,
  reused_patient boolean
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_patient_id uuid;
  v_dni text := nullif(regexp_replace(coalesce(p_dni, ''), '[^0-9]', '', 'g'), '');
  v_full_name text := btrim(coalesce(p_full_name, ''));
  v_reused boolean := false;
  v_encounter_id uuid;
begin
  if not private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para cargar pacientes.' using errcode = '42501';
  end if;

  if char_length(v_full_name) < 2 then
    raise exception 'El nombre del paciente es obligatorio.' using errcode = '22023';
  end if;

  if v_dni is not null then
    select p.id into v_patient_id
    from public.patients p
    where p.dni = v_dni and p.deleted_at is null
    limit 1;
  end if;

  if v_patient_id is null then
    insert into public.patients (
      full_name, full_name_normalized, dni, created_at, updated_at
    ) values (
      v_full_name, private.normalize_search_text(v_full_name), v_dni,
      timezone('utc', now()), timezone('utc', now())
    ) returning id into v_patient_id;
  else
    v_reused := true;
  end if;

  insert into public.encounters (
    patient_id, encounter_date, encounter_time, study_type, coverage_type,
    coverage_name, attendance_status, workflow_status, medical_control_today,
    created_by, updated_by, created_at, updated_at
  ) values (
    v_patient_id, coalesce(p_encounter_date, current_date), p_encounter_time,
    p_study_type, p_coverage_type,
    case when p_coverage_type = 'Mutual' then btrim(coalesce(p_coverage_name, '')) else '' end,
    'no_llego', 'cargada', coalesce(p_medical_control_today, false),
    auth.uid(), auth.uid(), timezone('utc', now()), timezone('utc', now())
  ) returning id into v_encounter_id;

  insert into public.encounter_events (
    encounter_id, patient_id, actor_id, event_type, title, details, created_at, updated_at
  ) values (
    v_encounter_id, v_patient_id, auth.uid(), 'encounter_created', 'Atencion creada desde Next',
    case when v_reused then 'Nueva visita asociada al DNI existente.' else 'Nuevo paciente creado.' end,
    timezone('utc', now()), timezone('utc', now())
  );

  return query select v_encounter_id, v_patient_id, v_reused;
end;
$$;

revoke all on function public.create_agenda_encounter(text, text, date, time, public.next_study_type, public.next_coverage_type, text, boolean) from public;
grant execute on function public.create_agenda_encounter(text, text, date, time, public.next_study_type, public.next_coverage_type, text, boolean) to authenticated;
