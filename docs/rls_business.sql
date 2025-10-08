-- RLS para tablas de negocio (Supabase Postgres)
-- Ejecuta este archivo en el editor de SQL de Supabase (con tu proyecto seleccionado)
-- Ajusta si cambias nombres de tablas/relaciones.

-- Habilitar RLS
alter table if exists profiles enable row level security;
alter table if exists companies enable row level security;
alter table if exists company_members enable row level security;
alter table if exists cfdi enable row level security;
alter table if exists gastos_clasificados enable row level security;
alter table if exists taxes_monthly enable row level security;
alter table if exists bank_statements enable row level security;
alter table if exists bank_tx enable row level security;

-- ==========================================================
-- Helper functions (SECURITY DEFINER) para evitar recursión
-- ==========================================================
-- Nota: estas funciones se ejecutan con privilegios del owner (postgres)
-- y por tanto no aplican RLS internamente, evitando ciclos entre policies.
-- Asegúrate de que el search_path esté fijado a 'public'.

create or replace function public.is_company_owner(_company_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(
    select 1 from public.companies c
    where c.id = _company_id
      and c.owner_id = auth.uid()
  );
$$;

create or replace function public.is_company_member(_company_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(
    select 1 from public.company_members m
    where m.company_id = _company_id
      and m.user_id = auth.uid()
  );
$$;

create or replace function public.is_company_admin(_company_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.is_company_owner(_company_id)
      or exists(
           select 1 from public.company_members m
           where m.company_id = _company_id
             and m.user_id = auth.uid()
             and m.role in ('owner','admin')
         );
$$;

-- Acceso por entidad hija
create or replace function public.can_access_cfdi(_cfdi_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(
    select 1
    from public.cfdi c
    where c.id = _cfdi_id
      and (public.is_company_owner(c.company_id) or public.is_company_member(c.company_id))
  );
$$;

create or replace function public.is_cfdi_admin(_cfdi_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(
    select 1
    from public.cfdi c
    where c.id = _cfdi_id
      and public.is_company_admin(c.company_id)
  );
$$;

create or replace function public.can_access_statement(_statement_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(
    select 1
    from public.bank_statements s
    where s.id = _statement_id
      and (public.is_company_owner(s.company_id) or public.is_company_member(s.company_id))
  );
$$;

create or replace function public.is_statement_admin(_statement_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(
    select 1
    from public.bank_statements s
    where s.id = _statement_id
      and public.is_company_admin(s.company_id)
  );
$$;

-- Permisos de ejecución para usuarios autenticados
revoke all on function public.is_company_owner(uuid)     from public;
revoke all on function public.is_company_member(uuid)    from public;
revoke all on function public.is_company_admin(uuid)     from public;
revoke all on function public.can_access_cfdi(uuid)      from public;
revoke all on function public.is_cfdi_admin(uuid)        from public;
revoke all on function public.can_access_statement(uuid) from public;
revoke all on function public.is_statement_admin(uuid)   from public;

grant execute on function public.is_company_owner(uuid)     to authenticated;
grant execute on function public.is_company_member(uuid)    to authenticated;
grant execute on function public.is_company_admin(uuid)     to authenticated;
grant execute on function public.can_access_cfdi(uuid)      to authenticated;
grant execute on function public.is_cfdi_admin(uuid)        to authenticated;
grant execute on function public.can_access_statement(uuid) to authenticated;
grant execute on function public.is_statement_admin(uuid)   to authenticated;

-- Helper predicates
-- Un usuario es OWNER de una compañía
-- exists(select 1 from companies c where c.id = <company_id> and c.owner_id = auth.uid())

-- Un usuario es MEMBER (cualquier rol) de una compañía
-- exists(select 1 from company_members m where m.company_id = <company_id> and m.user_id = auth.uid())

-- Un usuario es ADMIN (owner o admin) de una compañía
-- exists(select 1 from companies c where c.id = <company_id> and c.owner_id = auth.uid())
--   or exists(select 1 from company_members m where m.company_id = <company_id> and m.user_id = auth.uid() and m.role in ('owner','admin'))

-- PROFILES: cada usuario solo ve/modifica su propio perfil
drop policy if exists "profiles-select-own" on profiles;
create policy "profiles-select-own"
  on profiles for select to authenticated
  using (user_id = auth.uid());

drop policy if exists "profiles-upsert-own" on profiles;
create policy "profiles-upsert-own"
  on profiles for insert to authenticated
  with check (user_id = auth.uid());

drop policy if exists "profiles-update-own" on profiles;
create policy "profiles-update-own"
  on profiles for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists "profiles-delete-own" on profiles;
create policy "profiles-delete-own"
  on profiles for delete to authenticated
  using (user_id = auth.uid());

-- COMPANIES
drop policy if exists "companies-select-members" on companies;
create policy "companies-select-members"
  on companies for select to authenticated
  using (
    owner_id = auth.uid()
    or public.is_company_member(id)
    or public.is_company_owner(id)
  );

drop policy if exists "companies-insert-owner" on companies;
create policy "companies-insert-owner"
  on companies for insert to authenticated
  with check (owner_id = auth.uid());

drop policy if exists "companies-update-owner" on companies;
create policy "companies-update-owner"
  on companies for update to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

drop policy if exists "companies-delete-owner" on companies;
create policy "companies-delete-owner"
  on companies for delete to authenticated
  using (owner_id = auth.uid());

-- COMPANY_MEMBERS
drop policy if exists "members-select-related" on company_members;
create policy "members-select-related"
  on company_members for select to authenticated
  using (
    user_id = auth.uid()
    or public.is_company_owner(company_id)
  );

drop policy if exists "members-insert-by-owner" on company_members;
create policy "members-insert-by-owner"
  on company_members for insert to authenticated
  with check (public.is_company_owner(company_id));

drop policy if exists "members-update-by-owner" on company_members;
create policy "members-update-by-owner"
  on company_members for update to authenticated
  using (public.is_company_owner(company_id))
  with check (public.is_company_owner(company_id));

drop policy if exists "members-delete-by-owner" on company_members;
create policy "members-delete-by-owner"
  on company_members for delete to authenticated
  using (public.is_company_owner(company_id));

-- CFDI: visibilidad para miembros; escritura para admin (owner o admin)
drop policy if exists "cfdi-select-members" on cfdi;
create policy "cfdi-select-members"
  on cfdi for select to authenticated
  using (
    public.is_company_owner(company_id)
    or public.is_company_member(company_id)
  );

drop policy if exists "cfdi-insert-admin" on cfdi;
create policy "cfdi-insert-admin"
  on cfdi for insert to authenticated
  with check (
    public.is_company_admin(company_id)
  );

drop policy if exists "cfdi-update-admin" on cfdi;
create policy "cfdi-update-admin"
  on cfdi for update to authenticated
  using (public.is_company_admin(company_id))
  with check (public.is_company_admin(company_id));

drop policy if exists "cfdi-delete-admin" on cfdi;
create policy "cfdi-delete-admin"
  on cfdi for delete to authenticated
  using (public.is_company_admin(company_id));

-- GASTOS_CLASIFICADOS: hereda permisos de su CFDI
drop policy if exists "gastos-select-members" on gastos_clasificados;
create policy "gastos-select-members"
  on gastos_clasificados for select to authenticated
  using (
    public.can_access_cfdi(gastos_clasificados.cfdi_id)
  );

drop policy if exists "gastos-upsert-admin" on gastos_clasificados;
create policy "gastos-upsert-admin"
  on gastos_clasificados for insert to authenticated
  with check (
    public.is_cfdi_admin(gastos_clasificados.cfdi_id)
  );

drop policy if exists "gastos-update-admin" on gastos_clasificados;
create policy "gastos-update-admin"
  on gastos_clasificados for update to authenticated
  using (public.is_cfdi_admin(gastos_clasificados.cfdi_id))
  with check (public.is_cfdi_admin(gastos_clasificados.cfdi_id));

drop policy if exists "gastos-delete-admin" on gastos_clasificados;
create policy "gastos-delete-admin"
  on gastos_clasificados for delete to authenticated
  using (public.is_cfdi_admin(gastos_clasificados.cfdi_id));

-- TAXES_MONTHLY: por compañía
drop policy if exists "taxes-select-members" on taxes_monthly;
create policy "taxes-select-members"
  on taxes_monthly for select to authenticated
  using (
    public.is_company_owner(company_id)
    or public.is_company_member(company_id)
  );

drop policy if exists "taxes-upsert-admin" on taxes_monthly;
create policy "taxes-upsert-admin"
  on taxes_monthly for insert to authenticated
  with check (
    public.is_company_admin(company_id)
  );

drop policy if exists "taxes-update-admin" on taxes_monthly;
create policy "taxes-update-admin"
  on taxes_monthly for update to authenticated
  using (public.is_company_admin(company_id))
  with check (public.is_company_admin(company_id));

drop policy if exists "taxes-delete-admin" on taxes_monthly;
create policy "taxes-delete-admin"
  on taxes_monthly for delete to authenticated
  using (public.is_company_admin(company_id));

-- BANK_STATEMENTS
drop policy if exists "bankst-select-members" on bank_statements;
create policy "bankst-select-members"
  on bank_statements for select to authenticated
  using (
    public.is_company_owner(company_id)
    or public.is_company_member(company_id)
  );

drop policy if exists "bankst-upsert-admin" on bank_statements;
create policy "bankst-upsert-admin"
  on bank_statements for insert to authenticated
  with check (
    public.is_company_admin(company_id)
  );

drop policy if exists "bankst-update-admin" on bank_statements;
create policy "bankst-update-admin"
  on bank_statements for update to authenticated
  using (public.is_company_admin(company_id))
  with check (public.is_company_admin(company_id));

drop policy if exists "bankst-delete-admin" on bank_statements;
create policy "bankst-delete-admin"
  on bank_statements for delete to authenticated
  using (public.is_company_admin(company_id));

-- BANK_TX (hereda permisos por statement -> compañía)
drop policy if exists "banktx-select-members" on bank_tx;
create policy "banktx-select-members"
  on bank_tx for select to authenticated
  using (
    public.can_access_statement(bank_tx.statement_id)
  );

drop policy if exists "banktx-upsert-admin" on bank_tx;
create policy "banktx-upsert-admin"
  on bank_tx for insert to authenticated
  with check (
    public.is_statement_admin(bank_tx.statement_id)
  );

drop policy if exists "banktx-update-admin" on bank_tx;
create policy "banktx-update-admin"
  on bank_tx for update to authenticated
  using (public.is_statement_admin(bank_tx.statement_id))
  with check (public.is_statement_admin(bank_tx.statement_id));

drop policy if exists "banktx-delete-admin" on bank_tx;
create policy "banktx-delete-admin"
  on bank_tx for delete to authenticated
  using (public.is_statement_admin(bank_tx.statement_id));

-- Nota: Si usas endpoints de servicio (service_role), RLS no aplica.
-- Verifica con test simples desde el cliente que puedes leer/escribir solo tus datos.
