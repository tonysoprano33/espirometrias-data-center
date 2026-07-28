create or replace function public.update_agenda_encounter(
  p_encounter_id uuid,
  p_encounter_date date,
  p_encounter_time time,
  p_study_type public.next_study_type,
  p_coverage_type public.next_coverage_type,
  p_coverage_name text default '',
  p_medical_control_today boolean default false
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para editar la agenda.' using errcode = '42501';
  end if;
  update public.encounters
  set encounter_date = p_encounter_date,
      encounter_time = p_encounter_time,
      study_type = p_study_type,
      coverage_type = p_coverage_type,
      coverage_name = case when p_coverage_type = 'Mutual' then btrim(coalesce(p_coverage_name, '')) else '' end,
      medical_control_today = coalesce(p_medical_control_today, false),
      updated_by = auth.uid(), updated_at = timezone('utc', now())
  where id = p_encounter_id and deleted_at is null;
  if not found then raise exception 'La atencion no existe.' using errcode = '22023'; end if;
end;
$$;

create or replace function public.soft_delete_encounter(p_encounter_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare v_batch uuid := gen_random_uuid();
begin
  if not private.has_app_role(array['admin', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para eliminar una atencion.' using errcode = '42501';
  end if;
  update public.encounters
  set deleted_at = timezone('utc', now()), deleted_by = auth.uid(), deletion_batch = v_batch,
      purge_after = timezone('utc', now()) + interval '30 days', updated_by = auth.uid(), updated_at = timezone('utc', now())
  where id = p_encounter_id and deleted_at is null;
  if not found then raise exception 'La atencion ya fue eliminada o no existe.' using errcode = '22023'; end if;
end;
$$;

create or replace function public.restore_encounter(p_encounter_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not private.has_app_role(array['admin', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para restaurar una atencion.' using errcode = '42501';
  end if;
  update public.encounters set deleted_at = null, deleted_by = null, deletion_batch = null, purge_after = null,
    updated_by = auth.uid(), updated_at = timezone('utc', now()) where id = p_encounter_id;
  if not found then raise exception 'La atencion no existe.' using errcode = '22023'; end if;
end;
$$;

revoke all on function public.update_agenda_encounter(uuid, date, time, public.next_study_type, public.next_coverage_type, text, boolean) from public;
revoke all on function public.soft_delete_encounter(uuid) from public;
revoke all on function public.restore_encounter(uuid) from public;
grant execute on function public.update_agenda_encounter(uuid, date, time, public.next_study_type, public.next_coverage_type, text, boolean) to authenticated;
grant execute on function public.soft_delete_encounter(uuid) to authenticated;
grant execute on function public.restore_encounter(uuid) to authenticated;
