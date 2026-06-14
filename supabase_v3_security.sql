-- PetPass MX V3 seguridad minima profesional.
-- Ejecutar despues de supabase_schema.sql.
-- Activa Auth/RLS por clinica y deja la demo publica solo para datos ficticios.

create extension if not exists "pgcrypto";
create schema if not exists private;

alter table public.clinicas add column if not exists owner_user_id uuid;
alter table public.clinicas add column if not exists creado_por uuid;
alter table public.clinicas add column if not exists plan text default 'demo';

create table if not exists public.clinica_usuarios (
    id uuid primary key default gen_random_uuid(),
    clinica_id uuid references public.clinicas(id) on delete cascade,
    user_id uuid not null,
    rol text not null default 'admin',
    activo boolean default true,
    creado_en timestamptz default now(),
    unique(clinica_id, user_id)
);

create index if not exists idx_clinica_usuarios_clinica on public.clinica_usuarios(clinica_id);
create index if not exists idx_clinica_usuarios_user on public.clinica_usuarios(user_id);

insert into public.clinicas (nombre, telefono, email, codigo_acceso, activo, plan)
values ('Clinica Demo PetPass MX', '5512345678', 'demo@petpass.mx', 'PETPASS-DEMO', true, 'demo')
on conflict (codigo_acceso) do update
set plan = 'demo', activo = true;

create or replace function private.is_clinic_member(target_clinica_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.clinica_usuarios cu
        where cu.clinica_id = target_clinica_id
          and cu.user_id = auth.uid()
          and cu.activo = true
    );
$$;

create or replace function private.is_clinic_admin(target_clinica_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.clinica_usuarios cu
        where cu.clinica_id = target_clinica_id
          and cu.user_id = auth.uid()
          and cu.rol = 'admin'
          and cu.activo = true
    );
$$;

create or replace function private.is_demo_clinic(target_clinica_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.clinicas c
        where c.id = target_clinica_id
          and c.codigo_acceso = 'PETPASS-DEMO'
          and c.plan = 'demo'
          and c.activo = true
    );
$$;

grant usage on schema private to anon, authenticated;
grant execute on all functions in schema private to anon, authenticated;

grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on public.clinicas to anon, authenticated;
grant select, insert, update, delete on public.clinica_usuarios to authenticated;
grant select, insert, update, delete on public.tutores to anon, authenticated;
grant select, insert, update, delete on public.mascotas to anon, authenticated;
grant select, insert, update, delete on public.vacunas to anon, authenticated;

alter table public.clinicas enable row level security;
alter table public.clinica_usuarios enable row level security;
alter table public.tutores enable row level security;
alter table public.mascotas enable row level security;
alter table public.vacunas enable row level security;

drop policy if exists clinicas_select_member_or_demo on public.clinicas;
drop policy if exists clinicas_insert_owner on public.clinicas;
drop policy if exists clinicas_insert_demo on public.clinicas;
drop policy if exists clinicas_update_admin on public.clinicas;

create policy clinicas_select_member_or_demo
on public.clinicas for select to anon, authenticated
using (
    private.is_demo_clinic(id)
    or owner_user_id = auth.uid()
    or creado_por = auth.uid()
    or private.is_clinic_member(id)
);

create policy clinicas_insert_owner
on public.clinicas for insert to authenticated
with check (owner_user_id = auth.uid() and creado_por = auth.uid());

create policy clinicas_insert_demo
on public.clinicas for insert to anon
with check (codigo_acceso = 'PETPASS-DEMO' and plan = 'demo');

create policy clinicas_update_admin
on public.clinicas for update to authenticated
using (private.is_clinic_admin(id))
with check (private.is_clinic_admin(id));

drop policy if exists clinica_usuarios_select_member on public.clinica_usuarios;
drop policy if exists clinica_usuarios_insert_admin_or_owner on public.clinica_usuarios;
drop policy if exists clinica_usuarios_update_admin on public.clinica_usuarios;
drop policy if exists clinica_usuarios_delete_admin on public.clinica_usuarios;

create policy clinica_usuarios_select_member
on public.clinica_usuarios for select to authenticated
using (user_id = auth.uid() or private.is_clinic_member(clinica_id));

create policy clinica_usuarios_insert_admin_or_owner
on public.clinica_usuarios for insert to authenticated
with check (
    private.is_clinic_admin(clinica_id)
    or (
        user_id = auth.uid()
        and rol = 'admin'
        and exists (
            select 1
            from public.clinicas c
            where c.id = clinica_id
              and (c.owner_user_id = auth.uid() or c.creado_por = auth.uid())
        )
    )
);

create policy clinica_usuarios_update_admin
on public.clinica_usuarios for update to authenticated
using (private.is_clinic_admin(clinica_id))
with check (private.is_clinic_admin(clinica_id));

create policy clinica_usuarios_delete_admin
on public.clinica_usuarios for delete to authenticated
using (private.is_clinic_admin(clinica_id));

drop policy if exists tutores_member_all on public.tutores;
drop policy if exists tutores_demo_all on public.tutores;
drop policy if exists mascotas_member_all on public.mascotas;
drop policy if exists mascotas_demo_all on public.mascotas;
drop policy if exists vacunas_member_all on public.vacunas;
drop policy if exists vacunas_demo_all on public.vacunas;

create policy tutores_member_all
on public.tutores for all to authenticated
using (private.is_clinic_member(clinica_id))
with check (private.is_clinic_member(clinica_id));

create policy tutores_demo_all
on public.tutores for all to anon
using (private.is_demo_clinic(clinica_id))
with check (private.is_demo_clinic(clinica_id));

create policy mascotas_member_all
on public.mascotas for all to authenticated
using (private.is_clinic_member(clinica_id))
with check (private.is_clinic_member(clinica_id));

create policy mascotas_demo_all
on public.mascotas for all to anon
using (private.is_demo_clinic(clinica_id))
with check (private.is_demo_clinic(clinica_id));

create policy vacunas_member_all
on public.vacunas for all to authenticated
using (private.is_clinic_member(clinica_id))
with check (private.is_clinic_member(clinica_id));

create policy vacunas_demo_all
on public.vacunas for all to anon
using (private.is_demo_clinic(clinica_id))
with check (private.is_demo_clinic(clinica_id));

-- Storage queda temporalmente con configuración demo.
-- Endurecer policies de Storage en una fase posterior.
