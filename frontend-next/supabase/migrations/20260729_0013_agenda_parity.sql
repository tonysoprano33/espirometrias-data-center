-- Functional parity for the Next.js operator agenda.
-- This migration only extends the Next schema and leaves all legacy Django
-- tables untouched.

create or replace function public.agenda_entries_v2(target_date date default current_date)
returns table (
  encounter_id uuid,
  patient_id uuid,
  encounter_date date,
  encounter_time time,
  patient_name text,
  dni text,
  study_type public.next_study_type,
  coverage_type public.next_coverage_type,
  coverage_name text,
  referring_physician_id uuid,
  referring_physician_name text,
  attendance_status public.next_attendance_status,
  workflow_status public.next_workflow_status,
  medical_control_today boolean,
  so2_rest smallint,
  fc_rest smallint,
  so2_post smallint,
  fc_post smallint,
  result_code text,
  can_print boolean,
  missing_for_print text
)
language sql
stable
security definer
set search_path = public
as $$
  select
    e.id,
    p.id,
    e.encounter_date,
    e.encounter_time,
    p.full_name,
    p.dni,
    e.study_type,
    e.coverage_type,
    e.coverage_name,
    e.referring_physician_id,
    coalesce(rp.full_name, ''),
    e.attendance_status,
    e.workflow_status,
    e.medical_control_today,
    v.so2_rest,
    v.fc_rest,
    v.so2_post,
    v.fc_post,
    coalesce(sr.final_code, ''),
    (
      nullif(btrim(p.full_name), '') is not null
      and nullif(regexp_replace(coalesce(p.dni, ''), '[^0-9]', '', 'g'), '') is not null
      and v.so2_rest is not null
      and v.fc_rest is not null
      and v.so2_post is not null
      and v.fc_post is not null
      and nullif(btrim(coalesce(sr.final_code, '')), '') is not null
    ),
    concat_ws(', ',
      case when nullif(btrim(p.full_name), '') is null then 'nombre' end,
      case when nullif(regexp_replace(coalesce(p.dni, ''), '[^0-9]', '', 'g'), '') is null then 'DNI' end,
      case when v.so2_rest is null then 'SO2 reposo' end,
      case when v.fc_rest is null then 'FC reposo' end,
      case when v.so2_post is null then 'SO2 post' end,
      case when v.fc_post is null then 'FC post' end,
      case when nullif(btrim(coalesce(sr.final_code, '')), '') is null then 'resultado' end
    )
  from public.encounters e
  join public.patients p on p.id = e.patient_id
  left join public.referring_physicians rp on rp.id = e.referring_physician_id
  left join public.vital_signs v on v.encounter_id = e.id
  left join public.spirometry_results sr on sr.encounter_id = e.id
  where e.encounter_date = target_date
    and e.deleted_at is null
    and p.deleted_at is null
    and private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[])
  order by e.encounter_time nulls last, e.created_at;
$$;

revoke all on function public.agenda_entries_v2(date) from public;
grant execute on function public.agenda_entries_v2(date) to authenticated;

create or replace function public.agenda_physicians()
returns table (
  physician_id uuid,
  full_name text,
  is_default boolean
)
language sql
stable
security definer
set search_path = public
as $$
  select rp.id, rp.full_name, rp.is_default
  from public.referring_physicians rp
  where rp.active
    and private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[])
  order by rp.is_default desc, rp.full_name;
$$;

revoke all on function public.agenda_physicians() from public;
grant execute on function public.agenda_physicians() to authenticated;

create or replace function public.create_agenda_encounter_v2(
  p_full_name text,
  p_dni text default null,
  p_encounter_date date default current_date,
  p_encounter_time time default null,
  p_study_type public.next_study_type default 'Ciclometria',
  p_coverage_type public.next_coverage_type default 'Particular',
  p_coverage_name text default '',
  p_medical_control_today boolean default false,
  p_referring_physician_id uuid default null
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
  v_full_name text := upper(btrim(regexp_replace(coalesce(p_full_name, ''), '\s+', ' ', 'g')));
  v_reused boolean := false;
  v_encounter_id uuid;
  v_physician_id uuid := p_referring_physician_id;
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
    insert into public.patients (full_name, full_name_normalized, dni, created_at, updated_at)
    values (
      v_full_name, private.normalize_search_text(v_full_name), v_dni,
      timezone('utc', now()), timezone('utc', now())
    )
    returning id into v_patient_id;
  else
    v_reused := true;
  end if;

  if v_physician_id is null then
    select id into v_physician_id
    from public.referring_physicians
    where active
    order by is_default desc, full_name
    limit 1;
  end if;

  insert into public.encounters (
    patient_id, encounter_date, encounter_time, study_type, coverage_type,
    coverage_name, referring_physician_id, attendance_status, workflow_status,
    medical_control_today, created_by, updated_by, created_at, updated_at
  )
  values (
    v_patient_id, coalesce(p_encounter_date, current_date), p_encounter_time,
    p_study_type, p_coverage_type,
    case when p_coverage_type = 'Mutual' then btrim(coalesce(p_coverage_name, '')) else '' end,
    v_physician_id, 'no_llego', 'cargada', coalesce(p_medical_control_today, false),
    auth.uid(), auth.uid(), timezone('utc', now()), timezone('utc', now())
  )
  returning id into v_encounter_id;

  insert into public.encounter_events (
    encounter_id, patient_id, actor_id, event_type, title, details, created_at, updated_at
  )
  values (
    v_encounter_id, v_patient_id, auth.uid(), 'encounter_created',
    'Atencion creada desde Next',
    case when v_reused then 'Nueva visita asociada al DNI existente.' else 'Nuevo paciente creado.' end,
    timezone('utc', now()), timezone('utc', now())
  );

  return query select v_encounter_id, v_patient_id, v_reused;
end;
$$;

revoke all on function public.create_agenda_encounter_v2(
  text, text, date, time, public.next_study_type, public.next_coverage_type, text, boolean, uuid
) from public;
grant execute on function public.create_agenda_encounter_v2(
  text, text, date, time, public.next_study_type, public.next_coverage_type, text, boolean, uuid
) to authenticated;

create or replace function public.update_agenda_encounter_full(
  p_encounter_id uuid,
  p_full_name text,
  p_dni text,
  p_encounter_time time,
  p_study_type public.next_study_type,
  p_coverage_type public.next_coverage_type,
  p_coverage_name text default '',
  p_referring_physician_id uuid default null,
  p_medical_control_today boolean default false
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_patient_id uuid;
  v_full_name text := upper(btrim(regexp_replace(coalesce(p_full_name, ''), '\s+', ' ', 'g')));
  v_dni text := nullif(regexp_replace(coalesce(p_dni, ''), '[^0-9]', '', 'g'), '');
begin
  if not private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para editar la agenda.' using errcode = '42501';
  end if;
  if char_length(v_full_name) < 2 then
    raise exception 'El nombre del paciente es obligatorio.' using errcode = '22023';
  end if;

  select patient_id into v_patient_id
  from public.encounters
  where id = p_encounter_id and deleted_at is null;
  if v_patient_id is null then
    raise exception 'La atencion no existe.' using errcode = '22023';
  end if;

  if v_dni is not null and exists (
    select 1 from public.patients
    where dni = v_dni and id <> v_patient_id and deleted_at is null
  ) then
    raise exception 'Ese DNI ya pertenece a otro paciente.' using errcode = '23505';
  end if;

  update public.patients
  set full_name = v_full_name,
      full_name_normalized = private.normalize_search_text(v_full_name),
      dni = v_dni,
      updated_at = timezone('utc', now())
  where id = v_patient_id;

  update public.encounters
  set encounter_time = p_encounter_time,
      study_type = p_study_type,
      coverage_type = p_coverage_type,
      coverage_name = case when p_coverage_type = 'Mutual' then btrim(coalesce(p_coverage_name, '')) else '' end,
      referring_physician_id = p_referring_physician_id,
      medical_control_today = coalesce(p_medical_control_today, false),
      updated_by = auth.uid(),
      updated_at = timezone('utc', now())
  where id = p_encounter_id;
end;
$$;

revoke all on function public.update_agenda_encounter_full(
  uuid, text, text, time, public.next_study_type, public.next_coverage_type, text, uuid, boolean
) from public;
grant execute on function public.update_agenda_encounter_full(
  uuid, text, text, time, public.next_study_type, public.next_coverage_type, text, uuid, boolean
) to authenticated;

create or replace function public.upsert_agenda_physician(p_full_name text)
returns table (physician_id uuid, full_name text)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_name text := btrim(regexp_replace(coalesce(p_full_name, ''), '\s+', ' ', 'g'));
  v_normalized text;
  v_id uuid;
begin
  if not private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para agregar medicos.' using errcode = '42501';
  end if;
  if char_length(v_name) < 4 then
    raise exception 'Escribi el nombre completo del medico.' using errcode = '22023';
  end if;
  v_name := regexp_replace(v_name, '^(dr|dra)\.?\s*', '', 'i');
  v_name := case
    when lower(p_full_name) ~ '^\s*dra' then 'Dra. '
    else 'Dr. '
  end || initcap(lower(v_name));
  v_normalized := private.normalize_search_text(v_name);

  insert into public.referring_physicians (full_name, normalized_name, active, created_at, updated_at)
  values (v_name, v_normalized, true, timezone('utc', now()), timezone('utc', now()))
  on conflict (normalized_name) do update
    set active = true, updated_at = timezone('utc', now())
  returning id into v_id;

  return query
  select rp.id, rp.full_name from public.referring_physicians rp where rp.id = v_id;
end;
$$;

revoke all on function public.upsert_agenda_physician(text) from public;
grant execute on function public.upsert_agenda_physician(text) to authenticated;

create or replace function public.save_medical_result(
  p_encounter_id uuid,
  p_final_code text,
  p_comment text default ''
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_patient_id uuid;
  v_code text := upper(btrim(coalesce(p_final_code, '')));
  v_now timestamptz := timezone('utc', now());
begin
  if not private.has_app_role(array['admin', 'medico', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para guardar el resultado medico.' using errcode = '42501';
  end if;
  if v_code !~ '^[A-Z]{1,8}$' then
    raise exception 'El resultado debe usar un codigo valido, por ejemplo N, OL o RLOMS.' using errcode = '22023';
  end if;

  select patient_id into v_patient_id
  from public.encounters
  where id = p_encounter_id and deleted_at is null;
  if v_patient_id is null then
    raise exception 'La atencion no existe.' using errcode = '22023';
  end if;

  insert into public.spirometry_results (
    encounter_id, final_code, physician_comment, finalised_by, finalised_at, created_at, updated_at
  )
  values (
    p_encounter_id, v_code, btrim(coalesce(p_comment, '')), auth.uid(), v_now, v_now, v_now
  )
  on conflict (encounter_id) do update set
    final_code = excluded.final_code,
    physician_comment = excluded.physician_comment,
    finalised_by = auth.uid(),
    finalised_at = v_now,
    updated_at = v_now;

  update public.encounters
  set workflow_status = 'revisada'::public.next_workflow_status,
      validated_by = auth.uid(),
      validated_at = v_now,
      updated_by = auth.uid(),
      updated_at = v_now
  where id = p_encounter_id;

  insert into public.encounter_events (
    encounter_id, patient_id, actor_id, event_type, title, details, created_at, updated_at
  )
  values (
    p_encounter_id, v_patient_id, auth.uid(), 'medical_result_saved',
    'Resultado medico guardado', v_code, v_now, v_now
  );
end;
$$;

