-- Añade columnas de métricas y metadatos SAT para seguimiento detallado de descargas
-- Ejecutar este script en el editor SQL de Supabase (puede ajustarse si ya existen columnas)

alter table sat_jobs add column if not exists auth_ms int;
alter table sat_jobs add column if not exists request_ms int;
alter table sat_jobs add column if not exists verify_ms int;
alter table sat_jobs add column if not exists download_ms int;
alter table sat_jobs add column if not exists sat_request_id text;
alter table sat_jobs add column if not exists sat_meta jsonb;

-- Índice opcional para consultar por estado rápidamente
create index if not exists sat_jobs_status_idx on sat_jobs(status);
-- Índice sobre created_at para dashboards
create index if not exists sat_jobs_created_at_idx on sat_jobs(created_at);
