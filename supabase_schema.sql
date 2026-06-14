-- PetPass MX V2 demo schema para Supabase.
-- Ejecutar en Supabase SQL Editor.
-- RLS queda pendiente para una version productiva; no usar datos reales sensibles en esta demo.

create extension if not exists "pgcrypto";

create table if not exists public.clinicas (
    id uuid primary key default gen_random_uuid(),
    nombre text not null,
    telefono text,
    email text,
    logo_url text,
    codigo_acceso text unique,
    activo boolean default true,
    creado_en timestamptz default now()
);

create table if not exists public.tutores (
    id uuid primary key default gen_random_uuid(),
    clinica_id uuid references public.clinicas(id),
    nombre text not null,
    telefono text not null,
    email text,
    notas text,
    creado_en timestamptz default now()
);

create table if not exists public.mascotas (
    id uuid primary key default gen_random_uuid(),
    clinica_id uuid references public.clinicas(id),
    tutor_id uuid references public.tutores(id),
    nombre text not null,
    especie text,
    raza text,
    sexo text,
    fecha_nacimiento date,
    peso numeric,
    notas text,
    foto_url text,
    creado_en timestamptz default now()
);

create table if not exists public.vacunas (
    id uuid primary key default gen_random_uuid(),
    clinica_id uuid references public.clinicas(id),
    mascota_id uuid references public.mascotas(id),
    nombre_vacuna text not null,
    fecha_aplicada date,
    proxima_fecha date,
    responsable text,
    notas text,
    creado_en timestamptz default now()
);

create index if not exists idx_tutores_clinica on public.tutores(clinica_id);
create index if not exists idx_mascotas_clinica on public.mascotas(clinica_id);
create index if not exists idx_mascotas_tutor on public.mascotas(tutor_id);
create index if not exists idx_vacunas_clinica on public.vacunas(clinica_id);
create index if not exists idx_vacunas_mascota on public.vacunas(mascota_id);
create index if not exists idx_vacunas_proxima on public.vacunas(proxima_fecha);

insert into storage.buckets (id, name, public)
values ('pet-photos', 'pet-photos', true)
on conflict (id) do nothing;

-- Permisos abiertos para demo con anon/publishable key.
-- Pendiente para produccion: activar RLS y reemplazar por policies por clinica/usuario.
grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on public.clinicas to anon, authenticated;
grant select, insert, update, delete on public.tutores to anon, authenticated;
grant select, insert, update, delete on public.mascotas to anon, authenticated;
grant select, insert, update, delete on public.vacunas to anon, authenticated;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'pet_photos_public_select'
    ) then
        create policy pet_photos_public_select
        on storage.objects for select to anon, authenticated
        using (bucket_id = 'pet-photos');
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'pet_photos_public_insert'
    ) then
        create policy pet_photos_public_insert
        on storage.objects for insert to anon, authenticated
        with check (bucket_id = 'pet-photos');
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'pet_photos_public_update'
    ) then
        create policy pet_photos_public_update
        on storage.objects for update to anon, authenticated
        using (bucket_id = 'pet-photos')
        with check (bucket_id = 'pet-photos');
    end if;
end $$;
