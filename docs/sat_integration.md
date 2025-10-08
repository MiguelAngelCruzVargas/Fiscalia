# Integración con SAT (Descarga CFDI)

Este documento resume opciones para integrar la descarga de CFDI y cómo conectarlo con esta app (Supabase + React).

## Opciones

1) Proveedor tercero (API comercial)
- Ejemplos: FacturAPI, Facturama, Finkok, etc.
- Pros: Menor complejidad técnica y mantenimiento; SLA y soporte.
- Contras: Costos por uso; límites del proveedor; manejo de datos con terceros.
- Flujo: Frontend -> Backend propio -> API proveedor -> Guardar XML en Storage -> Upsert en `cfdi`.

2) SAT directo (Descarga masiva CFDI 2.0)
- Requiere e.firma (.cer/.key) y contraseña.
- Implementación vía:
  - Web automation (Playwright) para portal SAT, o
  - Web service/SOAP de descarga masiva 2.0 (WS-Security, sellado con e.firma).
- Pros: Control total y sin costos por factura.
- Contras: Complejidad técnica (certificados, seguridad, retos, cambios de portal), mantenimiento continuo.

## Arquitectura sugerida (SAT directo)

Servicio backend (Python FastAPI o Supabase Edge Function) con credenciales de servicio para acceder a Supabase (DB + Storage).

Pasos del servicio:
1. Obtiene e.firma del usuario desde Storage (ruta `firmas/{uid}/...`) usando Service Role (nunca desde el cliente).
2. Autentica contra SAT y solicita descarga por rango de fechas y tipo (emitidos/recibidos).
3. Guarda cada XML en el bucket `cfdi-xml` bajo `uid/company_id/uuid.xml`.
4. Upsert en `cfdi` (rellena campos parseados y `xml_ref`).
5. Registra el avance en `sat_jobs` para que el frontend muestre progreso.

### Tabla de jobs

```sql
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
```

RLS: permitir leer/crear jobs al propio usuario (o miembros de la compañía); el backend usa service role para ejecutarlos.

### Backend (borrador)

Dependencias sugeridas: `fastapi`, `uvicorn`, `httpx`, `cryptography`, `lxml`, opcional `playwright` o `zeep` (SOAP).

Endpoints:
- POST /sat/sync { user_id, company_id, kind, date_from, date_to }
- GET /sat/jobs/:id – estado/progreso.

### Frontend

- En `/import`, botón “Sincronizar desde SAT” con rango de fechas y tipo; llama al backend y muestra progreso.

### Seguridad

- Nunca exponer .cer/.key o contraseña de e.firma al cliente.
- Backend accede a Storage con Service Role, descarga temporalmente, y elimina archivos temporales.

### Recomendación

- MVP rápido: integrar proveedor (FacturAPI, etc.).
- Fase 2: SAT directo si buscas control/costos a largo plazo.