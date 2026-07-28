-- Explicit operator writes. Typing in a field never changes the encounter;
-- only these actions commit a complete pair of measurements.

create or replace function public.save_encounter_vitals(
  p_encounter_id uuid,
  p_stage text,
  p_so2 smallint,
  p_fc smallint
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_patient_id uuid;
  v_now timestamptz := timezone('utc', now());
begin
  if not private.has_app_role(array['admin', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para guardar mediciones.' using errcode = '42501';
  end if;

  if p_stage not in ('rest', 'post') then
    raise exception 'Etapa de medicion invalida.' using errcode = '22023';
  end if;
  if p_so2 is null or p_so2 < 0 or p_so2 > 100 then
    raise exception 'SO2 debe estar entre 0 y 100.' using errcode = '22023';
  end if;
  if p_fc is null or p_fc < 0 or p_fc > 300 then
    raise exception 'FC debe estar entre 0 y 300.' using errcode = '22023';
  end if;

  select patient_id into v_patient_id
  from public.encounters
  where id = p_encounter_id and deleted_at is null;
  if v_patient_id is null then
    raise exception 'La atencion no existe.' using errcode = '22023';
  end if;

  insert into public.vital_signs (encounter_id, so2_rest, fc_rest, so2_post, fc_post, rest_recorded_at, post_recorded_at, created_at, updated_at)
  values (
    p_encounter_id,
    case when p_stage = 'rest' then p_so2 end,
    case when p_stage = 'rest' then p_fc end,
    case when p_stage = 'post' then p_so2 end,
    case when p_stage = 'post' then p_fc end,
    case when p_stage = 'rest' then v_now end,
    case when p_stage = 'post' then v_now end,
    v_now,
    v_now
  )
  on conflict (encounter_id) do update set
    so2_rest = case when p_stage = 'rest' then excluded.so2_rest else public.vital_signs.so2_rest end,
    fc_rest = case when p_stage = 'rest' then excluded.fc_rest else public.vital_signs.fc_rest end,
    so2_post = case when p_stage = 'post' then excluded.so2_post else public.vital_signs.so2_post end,
    fc_post = case when p_stage = 'post' then excluded.fc_post else public.vital_signs.fc_post end,
    rest_recorded_at = case when p_stage = 'rest' then v_now else public.vital_signs.rest_recorded_at end,
    post_recorded_at = case when p_stage = 'post' then v_now else public.vital_signs.post_recorded_at end,
    updated_at = v_now;

  update public.encounters
  set attendance_status = case when p_stage = 'rest' then 'atendido'::public.next_attendance_status else attendance_status end,
      attended_at = case when p_stage = 'rest' then coalesce(attended_at, v_now) else attended_at end,
      first_vitals_recorded_at = case when p_stage = 'rest' then coalesce(first_vitals_recorded_at, v_now) else first_vitals_recorded_at end,
      discharged_at = case when p_stage = 'post' then v_now else discharged_at end,
      updated_by = auth.uid(),
      updated_at = v_now
  where id = p_encounter_id;

  insert into public.encounter_events (encounter_id, patient_id, actor_id, event_type, title, details, created_at, updated_at)
  values (
    p_encounter_id, v_patient_id, auth.uid(),
    case when p_stage = 'rest' then 'rest_vitals_saved' else 'post_vitals_saved' end,
    case when p_stage = 'rest' then 'SO2/FC de reposo guardados' else 'SO2/FC post guardados' end,
    format('SO2 %s | FC %s', p_so2, p_fc), v_now, v_now
  );
end;
$$;

revoke all on function public.save_encounter_vitals(uuid, text, smallint, smallint) from public;
grant execute on function public.save_encounter_vitals(uuid, text, smallint, smallint) to authenticated;

create or replace function public.set_encounter_attendance(
  p_encounter_id uuid,
  p_status public.next_attendance_status
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_patient_id uuid;
  v_now timestamptz := timezone('utc', now());
begin
  if not private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para cambiar la asistencia.' using errcode = '42501';
  end if;

  select patient_id into v_patient_id from public.encounters where id = p_encounter_id and deleted_at is null;
  if v_patient_id is null then
    raise exception 'La atencion no existe.' using errcode = '22023';
  end if;

  update public.encounters
  set attendance_status = p_status,
      waiting_started_at = case when p_status = 'esperando' then coalesce(waiting_started_at, v_now) else waiting_started_at end,
      updated_by = auth.uid(), updated_at = v_now
  where id = p_encounter_id;

  insert into public.encounter_events (encounter_id, patient_id, actor_id, event_type, title, details, created_at, updated_at)
  values (p_encounter_id, v_patient_id, auth.uid(), 'attendance_changed', 'Asistencia actualizada', p_status::text, v_now, v_now);
end;
$$;

revoke all on function public.set_encounter_attendance(uuid, public.next_attendance_status) from public;
grant execute on function public.set_encounter_attendance(uuid, public.next_attendance_status) to authenticated;
