-- Extiende sat_jobs para soportar metadatos completos del flujo SAT (CFDI/Metadata, fallback y trazas)
-- Ejecutar después de 2025-10-02_sat_jobs_metrics.sql

alter table sat_jobs add column if not exists tipo_solicitud_final text; -- 'CFDI' o 'Metadata'
alter table sat_jobs add column if not exists fallback_from_cfdi boolean;  -- true si se intentó CFDI y se cayó a Metadata
alter table sat_jobs add column if not exists request_meta jsonb;          -- metadatos de la solicitud exitosa o último intento
alter table sat_jobs add column if not exists request_error text;          -- mensaje de error original de la solicitud CFDI (si fallback)
alter table sat_jobs add column if not exists fallback_error text;         -- error del intento Metadata si también falló
alter table sat_jobs add column if not exists request_meta_first jsonb;    -- meta del primer intento antes de fallback
alter table sat_jobs add column if not exists fallback_meta jsonb;         -- meta del segundo intento (fallback) si falla
alter table sat_jobs add column if not exists verify_trace jsonb;          -- primeras transiciones de verificación (cuando SAT_TRACE_VERIFY=1)

-- No todos los motores necesitan índices aquí; si haces filtros por tipo_solicitud_final puedes añadir:
create index if not exists sat_jobs_tipo_solicitud_idx on sat_jobs(tipo_solicitud_final);
