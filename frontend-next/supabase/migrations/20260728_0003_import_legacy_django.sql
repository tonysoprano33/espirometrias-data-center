-- One-way copy from Django tables to the isolated Next schema.
-- It is idempotent through legacy_django_id and does not alter clinic_* rows.

insert into public.patients (
  legacy_django_id, full_name, full_name_normalized, patient_code, last_name, first_name,
  dni, birth_date, age_reported, gender, ethnicity, smoking_status, patient_group,
  height_cm, weight_kg, bmi, pack_years, phone, phone_normalized, notes,
  deleted_at, deletion_batch, purge_after, created_at, updated_at
)
select
  p.id,
  p.full_name,
  lower(regexp_replace(translate(p.full_name, 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun'), '[^a-zA-Z0-9]+', '', 'g')),
  coalesce(p.patient_code, ''), coalesce(p.last_name, ''), coalesce(p.first_name, ''),
  nullif(regexp_replace(coalesce(p.dni, ''), '[^0-9]', '', 'g'), ''),
  p.birth_date, p.age_reported, coalesce(p.gender, ''), coalesce(p.ethnicity, ''),
  coalesce(p.smoking_status, ''), coalesce(p.patient_group, ''), p.height_cm,
  p.weight_kg, p.bmi, p.pack_years, coalesce(p.phone, ''),
  regexp_replace(coalesce(p.phone, ''), '[^0-9]', '', 'g'), coalesce(p.notes, ''),
  p.deleted_at, p.deletion_batch,
  case when p.deleted_at is null then null else p.deleted_at + interval '30 days' end,
  p.created_at, p.updated_at
from public.clinic_patient p
on conflict (legacy_django_id) do update set
  full_name = excluded.full_name, full_name_normalized = excluded.full_name_normalized,
  dni = excluded.dni, phone = excluded.phone, phone_normalized = excluded.phone_normalized,
  updated_at = excluded.updated_at;

insert into public.referring_physicians (
  legacy_django_id, full_name, normalized_name, is_default, active, created_at, updated_at
)
select distinct on (normalized_name)
  legacy_django_id, full_name, normalized_name, is_default, active, created_at, updated_at
from (
  select d.id as legacy_django_id, d.full_name,
    lower(regexp_replace(translate(d.full_name, 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun'), '[^a-zA-Z0-9]+', '', 'g')) as normalized_name,
    d.is_default, d.active, d.created_at, d.updated_at
  from public.clinic_referringphysician d
) source
order by normalized_name, is_default desc, active desc, legacy_django_id
on conflict (legacy_django_id) do update set
  full_name = excluded.full_name, is_default = excluded.is_default,
  active = excluded.active, updated_at = excluded.updated_at;

insert into public.legacy_referring_physician_map (legacy_django_id, referring_physician_id)
select d.id, rp.id
from public.clinic_referringphysician d
join public.referring_physicians rp on rp.normalized_name =
  lower(regexp_replace(translate(d.full_name, 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun'), '[^a-zA-Z0-9]+', '', 'g'))
on conflict (legacy_django_id) do update set referring_physician_id = excluded.referring_physician_id;

insert into public.encounters (
  legacy_django_id, patient_id, encounter_date, encounter_time, study_type,
  coverage_type, coverage_name, affiliate_number, referring_physician_id,
  attendance_status, workflow_status, attended_at, waiting_started_at,
  first_vitals_recorded_at, discharged_at, bronchodilator_administered_at,
  bronchodilator_wait_minutes, technician_notes, medical_control_today,
  validated_at, deleted_at, deletion_batch, purge_after, created_at, updated_at
)
select
  e.id, p.id, e.encounter_date, e.encounter_time,
  case when e.study_type = 'Espirometria' then 'Espirometria'::public.next_study_type else 'Ciclometria'::public.next_study_type end,
  case when e.coverage_type = 'Mutual' then 'Mutual'::public.next_coverage_type else 'Particular'::public.next_coverage_type end,
  coalesce(e.coverage_name, ''), coalesce(e.affiliate_number, ''), d.referring_physician_id,
  case when e.no_show then 'no_llego'::public.next_attendance_status
       when e.attended then 'atendido'::public.next_attendance_status
       else 'esperando'::public.next_attendance_status end,
  case e.status
       when 'Revisada por medico' then 'revisada'::public.next_workflow_status
       when 'Informe generado' then 'informe_generado'::public.next_workflow_status
       when 'Entregada' then 'entregada'::public.next_workflow_status
       when 'Pendiente' then 'pendiente'::public.next_workflow_status
       else 'cargada'::public.next_workflow_status end,
  e.attended_at, e.waiting_started_at, e.first_vitals_recorded_at, e.discharged_at,
  e.bronchodilator_administered_at, coalesce(e.bronchodilator_wait_minutes, 10),
  coalesce(e.technician_notes, ''), coalesce(e.medical_control_today, false), e.validated_at,
  e.deleted_at, e.deletion_batch,
  case when e.deleted_at is null then null else e.deleted_at + interval '30 days' end,
  e.created_at, e.updated_at
from public.clinic_encounter e
join public.patients p on p.legacy_django_id = e.patient_id
left join public.legacy_referring_physician_map d on d.legacy_django_id = e.referring_physician_id
on conflict (legacy_django_id) do update set
  patient_id = excluded.patient_id, encounter_date = excluded.encounter_date,
  encounter_time = excluded.encounter_time, coverage_type = excluded.coverage_type,
  coverage_name = excluded.coverage_name, attendance_status = excluded.attendance_status,
  workflow_status = excluded.workflow_status, updated_at = excluded.updated_at;

insert into public.vital_signs (
  encounter_id, so2_rest, fc_rest, ta_rest, so2_post, fc_post, created_at, updated_at
)
select e.id, v.so2_rest, v.fc_rest, coalesce(v.ta_rest, ''), v.so2_post, v.fc_post, v.created_at, v.updated_at
from public.clinic_vitalsigns v
join public.encounters e on e.legacy_django_id = v.encounter_id
on conflict (encounter_id) do update set
  so2_rest = excluded.so2_rest, fc_rest = excluded.fc_rest, ta_rest = excluded.ta_rest,
  so2_post = excluded.so2_post, fc_post = excluded.fc_post, updated_at = excluded.updated_at;

insert into public.walk_tests (
  encounter_id, distance_meters, completed, stopped, symptoms, borg_final, minute_readings, created_at, updated_at
)
select e.id, w.distance_meters, w.completed, w.stopped, w.symptoms,
  coalesce(w.borg_final, 1), coalesce(w.minute_readings, '[]'::jsonb), w.created_at, w.updated_at
from public.clinic_walktest w
join public.encounters e on e.legacy_django_id = w.encounter_id
on conflict (encounter_id) do update set
  distance_meters = excluded.distance_meters, completed = excluded.completed,
  stopped = excluded.stopped, symptoms = excluded.symptoms, borg_final = excluded.borg_final,
  minute_readings = excluded.minute_readings, updated_at = excluded.updated_at;

insert into public.spirometry_results (
  encounter_id, respiratory_pattern, obstruction_grade, restriction_grade,
  bronchodilator_positive, suggested_bronchodilator_positive, suggested_bronchodilator_reason,
  physician_comment, measured_values, suggested_code, suggested_probability,
  suggested_summary, extracted_source, created_at, updated_at
)
select e.id,
  case s.respiratory_pattern
    when 'Normal' then 'Normal'::public.next_respiratory_pattern
    when 'Obstructivo' then 'Obstructivo'::public.next_respiratory_pattern
    when 'Restrictivo' then 'Restrictivo'::public.next_respiratory_pattern
    when 'Mixto' then 'Mixto'::public.next_respiratory_pattern else null end,
  case s.obstruction_grade when 'Leve' then 'Leve'::public.next_severity_grade when 'Moderada' then 'Moderada'::public.next_severity_grade when 'Moderadamente severa' then 'Moderadamente severa'::public.next_severity_grade when 'Severa' then 'Severa'::public.next_severity_grade else null end,
  case s.restriction_grade when 'Leve' then 'Leve'::public.next_severity_grade when 'Moderada' then 'Moderada'::public.next_severity_grade when 'Moderadamente severa' then 'Moderadamente severa'::public.next_severity_grade when 'Severa' then 'Severa'::public.next_severity_grade else null end,
  s.bronchodilator_positive, s.suggested_bronchodilator_positive,
  coalesce(s.suggested_bronchodilator_reason, ''), coalesce(s.physician_comment, ''),
  coalesce(s.measured_values, '{}'::jsonb), coalesce(s.suggested_code, ''),
  s.suggested_probability, coalesce(s.suggested_summary, ''), coalesce(s.extracted_source, ''),
  s.created_at, s.updated_at
from public.clinic_spirometryresult s
join public.encounters e on e.legacy_django_id = s.encounter_id
on conflict (encounter_id) do update set
  respiratory_pattern = excluded.respiratory_pattern,
  obstruction_grade = excluded.obstruction_grade,
  restriction_grade = excluded.restriction_grade,
  bronchodilator_positive = excluded.bronchodilator_positive,
  measured_values = excluded.measured_values, suggested_code = excluded.suggested_code,
  suggested_summary = excluded.suggested_summary, updated_at = excluded.updated_at;

insert into public.attachments (
  legacy_django_id, encounter_id, file_kind, storage_bucket, object_path,
  original_name, safe_name, mime_type, uploaded_by, analysis_status,
  analysis_error, analysis_attempted_at, created_at, updated_at
)
select a.id, e.id,
  case a.file_kind
    when 'pdf_resultado' then 'pdf_resultado'::public.next_attachment_kind
    when 'foto_resultado' then 'foto_resultado'::public.next_attachment_kind
    when 'informe_docx' then 'informe_docx'::public.next_attachment_kind
    when 'informe_pdf' then 'informe_pdf'::public.next_attachment_kind
    else 'otro'::public.next_attachment_kind end,
  'attachments', a.file, a.original_name,
  regexp_replace(translate(a.original_name, 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun'), '[^A-Za-z0-9._-]+', '_', 'g'),
  coalesce(a.mime_type, ''), null::uuid,
  case a.analysis_status
    when 'detected' then 'detected'::public.next_attachment_status
    when 'failed' then 'failed'::public.next_attachment_status
    else 'uploaded'::public.next_attachment_status end,
  coalesce(a.analysis_error, ''), a.analysis_attempted_at, a.created_at, a.updated_at
from public.clinic_attachment a
join public.encounters e on e.legacy_django_id = a.encounter_id
on conflict (legacy_django_id) do update set
  object_path = excluded.object_path, original_name = excluded.original_name,
  mime_type = excluded.mime_type, analysis_status = excluded.analysis_status,
  analysis_error = excluded.analysis_error, updated_at = excluded.updated_at;

insert into public.generated_reports (
  legacy_django_id, encounter_id, report_type, attachment_id, generator_version,
  source_snapshot, content_sha256, created_at, updated_at
)
select r.id, e.id,
  case r.report_type when 'Mutual' then 'Mutual'::public.next_report_type when 'Completo' then 'Completo'::public.next_report_type else 'Espirometria'::public.next_report_type end,
  a.id, coalesce(r.generator_version, ''), coalesce(r.source_snapshot, '{}'::jsonb),
  coalesce(r.content_sha256, ''), r.created_at, r.updated_at
from public.clinic_generatedreport r
join public.encounters e on e.legacy_django_id = r.encounter_id
left join public.attachments a on a.legacy_django_id = r.attachment_id
on conflict (legacy_django_id) do update set
  attachment_id = excluded.attachment_id, generator_version = excluded.generator_version,
  source_snapshot = excluded.source_snapshot, content_sha256 = excluded.content_sha256,
  updated_at = excluded.updated_at;

insert into public.encounter_events (
  legacy_django_id, encounter_id, patient_id, legacy_actor_id, event_type, title,
  details, metadata, created_at, updated_at
)
select ev.id, e.id, p.id, ev.actor_id, ev.event_type, ev.title,
  coalesce(ev.details, ''), coalesce(ev.metadata, '{}'::jsonb), ev.created_at, ev.updated_at
from public.clinic_encounterevent ev
join public.encounters e on e.legacy_django_id = ev.encounter_id
join public.patients p on p.legacy_django_id = ev.patient_id
on conflict (legacy_django_id) do update set
  title = excluded.title, details = excluded.details, metadata = excluded.metadata,
  updated_at = excluded.updated_at;
