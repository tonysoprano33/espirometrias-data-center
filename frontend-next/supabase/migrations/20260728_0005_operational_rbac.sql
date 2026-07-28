-- Operational read boundary for the first Next.js screens.
-- Secretary accounts use a restricted agenda RPC instead of direct table access.
-- Clinical writes remain disabled until their Server Actions are implemented and tested.

create or replace function public.secretary_agenda_entries(target_date date default current_date)
returns table (
  encounter_id uuid,
  patient_id uuid,
  encounter_time time,
  patient_name text,
  dni text,
  study_type public.next_study_type,
  coverage_type public.next_coverage_type,
  coverage_name text,
  attendance_status public.next_attendance_status,
  medical_control_today boolean
)
language sql
stable
security definer
set search_path = public
as $$
  select
    e.id,
    p.id,
    e.encounter_time,
    p.full_name,
    p.dni,
    e.study_type,
    e.coverage_type,
    e.coverage_name,
    e.attendance_status,
    e.medical_control_today
  from public.encounters e
  join public.patients p on p.id = e.patient_id
  where e.encounter_date = target_date
    and e.deleted_at is null
    and p.deleted_at is null
    and private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[])
  order by e.encounter_time nulls last, e.created_at;
$$;

revoke all on function public.secretary_agenda_entries(date) from public;
grant execute on function public.secretary_agenda_entries(date) to authenticated;

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
language sql
stable
security definer
set search_path = public
as $$
  select
    e.id,
    e.encounter_time,
    p.full_name,
    p.dni,
    e.study_type,
    e.coverage_type,
    e.attendance_status,
    e.workflow_status,
    exists (select 1 from public.spirometry_results s where s.encounter_id = e.id and s.respiratory_pattern is not null),
    exists (select 1 from public.attachments a where a.encounter_id = e.id and a.file_kind in ('pdf_resultado', 'foto_resultado')),
    e.medical_control_today
  from public.encounters e
  join public.patients p on p.id = e.patient_id
  where e.encounter_date = target_date
    and e.deleted_at is null
    and p.deleted_at is null
    and private.has_app_role(array['admin', 'medico', 'espirometrista']::public.app_role[])
  order by e.encounter_time nulls last, e.created_at;
$$;

revoke all on function public.medical_review_queue(date) from public;
grant execute on function public.medical_review_queue(date) to authenticated;
