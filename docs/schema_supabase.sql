-- Esquema inicial para Postgres (Supabase) --

-- Extensiones necesarias
create extension if not exists pgcrypto; -- para gen_random_uuid()

-- Usuarios y perfiles
create table if not exists profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  rfc text,
  legal_name text,
  regime text,
  firma_ref text, -- referencia en storage; contenido cifrado
  sat_status text
);

-- Empresas (soporte multi-empresa)
create table if not exists companies (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  rfc text not null,
  name text not null,
  created_at timestamptz default now()
);

create table if not exists company_members (
  company_id uuid references companies(id) on delete cascade,
  user_id uuid references auth.users(id) on delete cascade,
  role text check (role in ('owner','admin','viewer')),
  primary key (company_id, user_id)
);

-- CFDI
create table if not exists cfdi (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  uuid text unique,
  tipo text check (tipo in ('I','E','P')),
  emisor_rfc text,
  receptor_rfc text,
  fecha date,
  subtotal numeric,
  impuestos numeric,
  total numeric,
  xml_ref text, -- storage path
  status text
);

-- Clasificación de gastos
create table if not exists gastos_clasificados (
  cfdi_id uuid primary key references cfdi(id) on delete cascade,
  categoria text,
  subcategoria text,
  score numeric,
  fuente text check (fuente in ('regla','ia')),
  corrected_by uuid references auth.users(id),
  corrected_at timestamptz
);

-- Impuestos mensuales
create table if not exists taxes_monthly (
  company_id uuid references companies(id) on delete cascade,
  periodo date, -- usar primer día del mes
  isr_base numeric,
  isr numeric,
  iva_cobrado numeric,
  iva_acreditable numeric,
  iva_a_pagar numeric,
  primary key (company_id, periodo)
);

-- Bancos
create table if not exists bank_statements (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id) on delete cascade,
  periodo_d1 date,
  periodo_d2 date,
  file_ref text
);

create table if not exists bank_tx (
  id uuid primary key default gen_random_uuid(),
  statement_id uuid references bank_statements(id) on delete cascade,
  fecha date,
  concepto text,
  monto numeric,
  cuenta text,
  match_cfdi_id uuid references cfdi(id)
);

-- Planes y suscripciones
create table if not exists plans (
  plan_id text primary key,
  name text,
  limits jsonb,
  price_mxn numeric
);

create table if not exists subscriptions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id) on delete cascade,
  plan_id text references plans(plan_id),
  status text,
  current_period_end timestamptz
);

create table if not exists usage_counters (
  company_id uuid references companies(id) on delete cascade,
  metric text,
  period date,
  count int,
  primary key (company_id, metric, period)
);

-- RLS (borrador – activar en Supabase y restringir por user_id miembro de la compañía)
-- alter table ... enable row level security;
-- create policy ... on companies for select using (auth.uid() = owner_id or exists(select 1 from company_members m where m.company_id = id and m.user_id = auth.uid()));
