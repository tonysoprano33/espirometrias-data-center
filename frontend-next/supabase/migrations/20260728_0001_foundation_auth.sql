-- Foundation only: profiles and RBAC for the isolated Next.js preview.
-- Run in a staging Supabase project first. Do not run against production yet.

create type public.app_role as enum ('admin', 'secretaria', 'medico', 'espirometrista');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  role public.app_role not null default 'secretaria',
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

alter table public.profiles enable row level security;

create schema if not exists private;

create or replace function private.current_app_role()
returns public.app_role
language sql
stable
security definer
set search_path = public
as $$
  select role from public.profiles where id = auth.uid();
$$;

revoke all on function private.current_app_role() from public;
grant usage on schema private to authenticated;
grant execute on function private.current_app_role() to authenticated;

create policy "profiles_read_own_or_admin"
on public.profiles for select to authenticated
using (id = auth.uid() or private.current_app_role() = 'admin');

create policy "profiles_admin_manage"
on public.profiles for all to authenticated
using (private.current_app_role() = 'admin')
with check (private.current_app_role() = 'admin');

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', new.email));
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute procedure public.set_updated_at();

-- Seed accounts are deliberately omitted. Create test users through Supabase Auth,
-- then promote their profiles from the Supabase dashboard or a server-only admin tool.
