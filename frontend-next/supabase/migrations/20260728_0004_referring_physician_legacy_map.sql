-- Multiple Django physician IDs can represent the same normalized person.
-- Keep every legacy ID as a traceable mapping while exposing one canonical row.

create table if not exists public.legacy_referring_physician_map (
  legacy_django_id bigint primary key,
  referring_physician_id uuid not null references public.referring_physicians(id) on delete restrict,
  created_at timestamptz not null default timezone('utc', now())
);
