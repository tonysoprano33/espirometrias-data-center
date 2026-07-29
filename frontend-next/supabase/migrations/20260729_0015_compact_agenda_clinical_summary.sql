-- Compact operator agenda with the clinical walk summary needed at a glance.

create or replace function public.agenda_entries_v3(target_date date default current_date)
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
  walk_distance_meters smallint,
  walk_completed boolean,
  walk_stopped boolean,
  walk_symptoms boolean,
  borg_final smallint,
  bronchodilator_positive boolean,
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
    coalesce(w.distance_meters, 200),
    coalesce(w.completed, true),
    coalesce(w.stopped, false),
    coalesce(w.symptoms, false),
    coalesce(w.borg_final, 1),
    coalesce(sr.bronchodilator_positive, false),
    (
      nullif(btrim(p.full_name), '') is not null
      and nullif(regexp_replace(coalesce(p.dni, ''), '[^0-9]', '', 'g'), '') is not null
      and v.so2_rest is not null
      and v.fc_rest is not null
      and (
        e.study_type = 'Espirometria'
        or (v.so2_post is not null and v.fc_post is not null)
      )
      and nullif(btrim(coalesce(sr.final_code, '')), '') is not null
    ),
    concat_ws(', ',
      case when nullif(btrim(p.full_name), '') is null then 'nombre' end,
      case when nullif(regexp_replace(coalesce(p.dni, ''), '[^0-9]', '', 'g'), '') is null then 'DNI' end,
      case when v.so2_rest is null then 'SO2 reposo' end,
      case when v.fc_rest is null then 'FC reposo' end,
      case when e.study_type = 'Ciclometria' and v.so2_post is null then 'SO2 post' end,
      case when e.study_type = 'Ciclometria' and v.fc_post is null then 'FC post' end,
      case when nullif(btrim(coalesce(sr.final_code, '')), '') is null then 'resultado' end
    )
  from public.encounters e
  join public.patients p on p.id = e.patient_id
  left join public.referring_physicians rp on rp.id = e.referring_physician_id
  left join public.vital_signs v on v.encounter_id = e.id
  left join public.walk_tests w on w.encounter_id = e.id
  left join public.spirometry_results sr on sr.encounter_id = e.id
  where e.encounter_date = target_date
    and e.deleted_at is null
    and p.deleted_at is null
    and private.has_app_role(array['admin', 'secretaria', 'espirometrista']::public.app_role[])
  order by e.encounter_time nulls last, e.created_at;
$$;

revoke all on function public.agenda_entries_v3(date) from public;
grant execute on function public.agenda_entries_v3(date) to authenticated;
