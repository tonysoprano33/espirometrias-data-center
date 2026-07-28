-- The legacy SQL import copied attachment metadata, not binary files.
-- This bucket is required for new uploads and re-uploads from medical review.
insert into storage.buckets (id, name, public)
values ('attachments', 'attachments', false)
on conflict (id) do nothing;

create policy "clinical_attachment_objects_read" on storage.objects
for select to authenticated
using (
  bucket_id = 'attachments'
  and private.has_app_role(array['admin', 'espirometrista', 'medico']::public.app_role[])
);

create policy "clinical_attachment_objects_insert" on storage.objects
for insert to authenticated
with check (
  bucket_id = 'attachments'
  and private.has_app_role(array['admin', 'espirometrista']::public.app_role[])
);

create policy "clinical_attachment_objects_update" on storage.objects
for update to authenticated
using (
  bucket_id = 'attachments'
  and private.has_app_role(array['admin', 'espirometrista']::public.app_role[])
)
with check (
  bucket_id = 'attachments'
  and private.has_app_role(array['admin', 'espirometrista']::public.app_role[])
);

create policy "clinical_attachment_objects_delete" on storage.objects
for delete to authenticated
using (
  bucket_id = 'attachments'
  and private.has_app_role(array['admin', 'espirometrista']::public.app_role[])
);
