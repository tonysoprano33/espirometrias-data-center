create or replace function public.restore_patient(p_patient_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not private.has_app_role(array['admin', 'espirometrista']::public.app_role[]) then
    raise exception 'No tenes permisos para restaurar un paciente.' using errcode = '42501';
  end if;
  update public.patients
  set deleted_at = null, deleted_by = null, deletion_batch = null, purge_after = null,
      updated_by = auth.uid(), updated_at = timezone('utc', now())
  where id = p_patient_id and deleted_at is not null;
  if not found then raise exception 'El paciente no existe en la papelera.' using errcode = '22023'; end if;
end;
$$;

revoke all on function public.restore_patient(uuid) from public;
grant execute on function public.restore_patient(uuid) to authenticated;
