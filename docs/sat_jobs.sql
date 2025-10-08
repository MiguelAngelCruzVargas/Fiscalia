-- SAT Jobs (descarga/sincronización)

create table if not exists sat_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  company_id uuid references companies(id) on delete cascade,
  kind text check (kind in ('emitidos','recibidos')) not null,
  date_from date not null,
  date_to date not null,
  status text check (status in ('queued','running','success','error')) default 'queued',
  total_found int,
  total_downloaded int,
  error text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table if exists sat_jobs enable row level security;

drop policy if exists "jobs-select-own" on sat_jobs;
create policy "jobs-select-own"
  on sat_jobs for select to authenticated
  using (
    user_id = auth.uid()
    or exists(select 1 from companies c where c.id = company_id and c.owner_id = auth.uid())
    or exists(select 1 from company_members m where m.company_id = company_id and m.user_id = auth.uid())
  );

drop policy if exists "jobs-insert-own" on sat_jobs;
create policy "jobs-insert-own"
  on sat_jobs for insert to authenticated
  with check (
    user_id = auth.uid()
    and (
      exists(select 1 from companies c where c.id = company_id and c.owner_id = auth.uid())
      or exists(select 1 from company_members m where m.company_id = company_id and m.user_id = auth.uid())
    )
  );

drop policy if exists "jobs-update-own" on sat_jobs;
create policy "jobs-update-own"
  on sat_jobs for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
