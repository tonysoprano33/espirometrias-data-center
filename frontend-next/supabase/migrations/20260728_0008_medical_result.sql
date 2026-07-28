alter table public.spirometry_results
  add column if not exists final_code text not null default '';

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
  if not private.has_app_role(array['admin', 'medico']::public.app_role[]) then
    raise exception 'No tenes permisos para guardar el resultado medico.' using errcode = '42501';
  end if;
  if v_code !~ '^[A-Z]{1,8}$' then
    raise exception 'El resultado debe usar un codigo valido, por ejemplo N, OL o RLOMS.' using errcode = '22023';
  end if;
  if char_length(coalesce(p_comment, '')) > 4000 then
    raise exception 'El comentario es demasiado largo.' using errcode = '22023';
  end if;

  select patient_id into v_patient_id from public.encounters where id = p_encounter_id and deleted_at is null;
  if v_patient_id is null then
    raise exception 'La atencion no existe.' using errcode = '22023';
  end if;

  insert into public.spirometry_results (encounter_id, final_code, physician_comment, finalised_by, finalised_at, created_at, updated_at)
  values (p_encounter_id, v_code, btrim(coalesce(p_comment, '')), auth.uid(), v_now, v_now, v_now)
  on conflict (encounter_id) do update set
    final_code = excluded.final_code,
    physician_comment = excluded.physician_comment,
    finalised_by = auth.uid(),
    finalised_at = v_now,
    updated_at = v_now;

  update public.encounters
  set workflow_status = 'revisada'::public.next_workflow_status,
      validated_by = auth.uid(), validated_at = v_now,
      updated_by = auth.uid(), updated_at = v_now
  where id = p_encounter_id;

  insert into public.encounter_events (encounter_id, patient_id, actor_id, event_type, title, details, created_at, updated_at)
  values (p_encounter_id, v_patient_id, auth.uid(), 'medical_result_saved', 'Resultado medico guardado', v_code, v_now, v_now);
end;
$$;

revoke all on function public.save_medical_result(uuid, text, text) from public;
grant execute on function public.save_medical_result(uuid, text, text) to authenticated;

create or replace function public.medical_review_queue(target_date date default current_date)
returns table (
  encounter_id uuid,
  encounter_time time,
  patient_name text,
  dni text,
  study_type public.next_study_type,
  coverage_type public.next_coverage_type,
  attendance_status public.next_attendance_status,
  workflow_status public.next_workflow_status,
  has_result boolean,
  has_source_file boolean,
  medical_control_today boolean
)
language sql stable security definer set search_path = public
as $$
  select e.id, e.encounter_time, p.full_name, p.dni, e.study_type, e.coverage_type,
    e.attendance_status, e.workflow_status,
    exists (select 1 from public.spirometry_results s where s.encounter_id = e.id and (s.respiratory_pattern is not null or nullif(s.final_code, '') is not null)),
    exists (select 1 from public.attachments a where a.encounter_id = e.id and a.file_kind in ('pdf_resultado', 'foto_resultado')),
    e.medical_control_today
  from public.encounters e join public.patients p on p.id = e.patient_id
  where e.encounter_date = target_date and e.deleted_at is null and p.deleted_at is null
    and private.has_app_role(array['admin', 'medico', 'espirometrista']::public.app_role[])
  order by e.encounter_time nulls last, e.created_at;
$$;

revoke all on function public.medical_review_queue(date) from public;
grant execute on function public.medical_review_queue(date) to authenticated;
