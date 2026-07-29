-- Complete clinical editor used by the spirometry operator. This is a single
-- audited write so reports never see a half-updated encounter.
create or replace function public.save_encounter_clinical_details(
  p_encounter_id uuid,
  p_full_name text,
  p_dni text,
  p_encounter_time time,
  p_study_type public.next_study_type,
  p_coverage_type public.next_coverage_type,
  p_coverage_name text,
  p_referring_physician_id uuid,
  p_medical_control_today boolean,
  p_attendance_status public.next_attendance_status,
  p_so2_rest smallint,
  p_fc_rest smallint,
  p_so2_post smallint,
  p_fc_post smallint,
  p_distance_meters smallint,
  p_completed boolean,
  p_stopped boolean,
  p_symptoms boolean,
  p_borg_final smallint,
  p_result_code text,
  p_bronchodilator_positive boolean
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_encounter public.encounters;
  v_name text := upper(btrim(regexp_replace(coalesce(p_full_name, ''), '\s+', ' ', 'g')));
  v_dni text := nullif(regexp_replace(coalesce(p_dni, ''), '[^0-9]', '', 'g'), '');
  v_result text := upper(btrim(coalesce(p_result_code, '')));
  v_now timestamptz := timezone('utc', now());
begin
  if not private.has_app_role(array['admin', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para editar la atencion.' using errcode = '42501';
  end if;

  select *
  into v_encounter
  from public.encounters
  where id = p_encounter_id and deleted_at is null
  for update;

  if v_encounter.id is null then
    raise exception 'La atencion no existe.' using errcode = '22023';
  end if;
  if char_length(v_name) < 2 then
    raise exception 'El nombre del paciente es obligatorio.' using errcode = '22023';
  end if;
  if v_dni is not null and exists (
    select 1 from public.patients
    where dni = v_dni and id <> v_encounter.patient_id and deleted_at is null
  ) then
    raise exception 'Ese DNI ya pertenece a otro paciente.' using errcode = '23505';
  end if;
  if p_so2_rest is not null and (p_so2_rest < 50 or p_so2_rest > 100) then
    raise exception 'SO2 en reposo fuera de rango.' using errcode = '22023';
  end if;
  if p_so2_post is not null and (p_so2_post < 50 or p_so2_post > 100) then
    raise exception 'SO2 post fuera de rango.' using errcode = '22023';
  end if;
  if p_fc_rest is not null and (p_fc_rest < 20 or p_fc_rest > 250) then
    raise exception 'FC en reposo fuera de rango.' using errcode = '22023';
  end if;
  if p_fc_post is not null and (p_fc_post < 20 or p_fc_post > 250) then
    raise exception 'FC post fuera de rango.' using errcode = '22023';
  end if;
  if p_distance_meters < 0 or p_distance_meters > 10000 then
    raise exception 'Distancia de caminata fuera de rango.' using errcode = '22023';
  end if;
  if p_borg_final < 0 or p_borg_final > 10 then
    raise exception 'Escala de Borg fuera de rango.' using errcode = '22023';
  end if;
  if v_result <> '' and v_result not in (
    'N', 'OL', 'OM', 'OMS', 'OS', 'RL', 'RM', 'RMS', 'RS',
    'RLOL', 'RLOM', 'RLOMS', 'RLOS', 'RMOL', 'RMOM', 'RMOMS', 'RMOS',
    'RMSOL', 'RMSOM', 'RMSOMS', 'RMSOS', 'RSOL', 'RSOM', 'RSOMS', 'RSOS'
  ) then
    raise exception 'Codigo de resultado no valido.' using errcode = '22023';
  end if;

  update public.patients
  set full_name = v_name,
      full_name_normalized = private.normalize_search_text(v_name),
      dni = v_dni,
      updated_at = v_now
  where id = v_encounter.patient_id;

  update public.encounters
  set encounter_time = p_encounter_time,
      study_type = p_study_type,
      coverage_type = p_coverage_type,
      coverage_name = case when p_coverage_type = 'Mutual' then btrim(coalesce(p_coverage_name, '')) else '' end,
      referring_physician_id = p_referring_physician_id,
      medical_control_today = coalesce(p_medical_control_today, false),
      attendance_status = p_attendance_status,
      waiting_started_at = case
        when p_attendance_status = 'esperando' then coalesce(waiting_started_at, v_now)
        else waiting_started_at
      end,
      attended_at = case
        when p_attendance_status = 'atendido' then coalesce(attended_at, v_now)
        else attended_at
      end,
      updated_by = auth.uid(),
      updated_at = v_now
  where id = p_encounter_id;

  insert into public.vital_signs (
    encounter_id, so2_rest, fc_rest, so2_post, fc_post,
    rest_recorded_at, post_recorded_at, created_at, updated_at
  )
  values (
    p_encounter_id, p_so2_rest, p_fc_rest, p_so2_post, p_fc_post,
    case when p_so2_rest is not null and p_fc_rest is not null then v_now end,
    case when p_so2_post is not null and p_fc_post is not null then v_now end,
    v_now, v_now
  )
  on conflict (encounter_id) do update set
    so2_rest = excluded.so2_rest,
    fc_rest = excluded.fc_rest,
    so2_post = excluded.so2_post,
    fc_post = excluded.fc_post,
    rest_recorded_at = case
      when excluded.so2_rest is not null and excluded.fc_rest is not null
        then coalesce(public.vital_signs.rest_recorded_at, v_now)
      else public.vital_signs.rest_recorded_at
    end,
    post_recorded_at = case
      when excluded.so2_post is not null and excluded.fc_post is not null
        then coalesce(public.vital_signs.post_recorded_at, v_now)
      else public.vital_signs.post_recorded_at
    end,
    updated_at = v_now;

  insert into public.walk_tests (
    encounter_id, distance_meters, completed, stopped, symptoms, borg_final, created_at, updated_at
  )
  values (
    p_encounter_id, p_distance_meters, p_completed, p_stopped, p_symptoms, p_borg_final, v_now, v_now
  )
  on conflict (encounter_id) do update set
    distance_meters = excluded.distance_meters,
    completed = excluded.completed,
    stopped = excluded.stopped,
    symptoms = excluded.symptoms,
    borg_final = excluded.borg_final,
    updated_at = v_now;

  insert into public.spirometry_results (
    encounter_id, final_code, bronchodilator_positive, finalised_by, finalised_at, created_at, updated_at
  )
  values (
    p_encounter_id, v_result, p_bronchodilator_positive,
    case when v_result <> '' then auth.uid() end,
    case when v_result <> '' then v_now end,
    v_now, v_now
  )
  on conflict (encounter_id) do update set
    final_code = excluded.final_code,
    bronchodilator_positive = excluded.bronchodilator_positive,
    finalised_by = case when excluded.final_code <> '' then auth.uid() else public.spirometry_results.finalised_by end,
    finalised_at = case when excluded.final_code <> '' then v_now else public.spirometry_results.finalised_at end,
    updated_at = v_now;

  update public.encounters
  set first_vitals_recorded_at = case
        when p_so2_rest is not null and p_fc_rest is not null then coalesce(first_vitals_recorded_at, v_now)
        else first_vitals_recorded_at
      end,
      discharged_at = case
        when p_so2_post is not null and p_fc_post is not null then coalesce(discharged_at, v_now)
        else discharged_at
      end,
      workflow_status = case
        when v_result <> '' then 'revisada'::public.next_workflow_status
        when workflow_status = 'pendiente' and (p_so2_rest is not null or p_so2_post is not null)
          then 'cargada'::public.next_workflow_status
        else workflow_status
      end,
      updated_by = auth.uid(),
      updated_at = v_now
  where id = p_encounter_id;

  insert into public.encounter_events (
    encounter_id, patient_id, actor_id, event_type, title, details, metadata, created_at, updated_at
  )
  values (
    p_encounter_id, v_encounter.patient_id, auth.uid(),
    'encounter_clinical_details_updated', 'Atencion clinica editada',
    format('Distancia %s m | Borg %s | Resultado %s', p_distance_meters, p_borg_final, coalesce(nullif(v_result, ''), '-')),
    jsonb_build_object(
      'study_type', p_study_type,
      'coverage_type', p_coverage_type,
      'attendance_status', p_attendance_status,
      'distance_meters', p_distance_meters,
      'borg_final', p_borg_final,
      'bronchodilator_positive', p_bronchodilator_positive
    ),
    v_now, v_now
  );
end;
$$;

revoke all on function public.save_encounter_clinical_details(
  uuid, text, text, time, public.next_study_type, public.next_coverage_type, text, uuid,
  boolean, public.next_attendance_status, smallint, smallint, smallint, smallint,
  smallint, boolean, boolean, boolean, smallint, text, boolean
) from public;

grant execute on function public.save_encounter_clinical_details(
  uuid, text, text, time, public.next_study_type, public.next_coverage_type, text, uuid,
  boolean, public.next_attendance_status, smallint, smallint, smallint, smallint,
  smallint, boolean, boolean, boolean, smallint, text, boolean
) to authenticated;
