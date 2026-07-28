create or replace function public.save_clinical_note(p_encounter_id uuid, p_body text)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_patient_id uuid;
begin
  if not private.has_app_role(array['admin', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para guardar notas.' using errcode = '42501';
  end if;
  if char_length(btrim(coalesce(p_body, ''))) = 0 or char_length(p_body) > 2000 then
    raise exception 'La nota debe tener entre 1 y 2000 caracteres.' using errcode = '22023';
  end if;
  select patient_id into v_patient_id from public.encounters where id = p_encounter_id and deleted_at is null;
  if v_patient_id is null then raise exception 'La atencion no existe.' using errcode = '22023'; end if;
  insert into public.clinical_notes (encounter_id, body, created_by)
  values (p_encounter_id, btrim(p_body), auth.uid());
end;
$$;

revoke all on function public.save_clinical_note(uuid, text) from public;
grant execute on function public.save_clinical_note(uuid, text) to authenticated;
