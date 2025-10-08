# Fiscal-IA Web (Vite + React)

App base con autenticación de Supabase, rutas de login/registro y una ruta protegida `/dashboard`.

## Requisitos
- Node.js 18+
- Proyecto de Supabase con Auth habilitado (correo/contraseña)

## Variables de entorno
Copia `.env.local.example` a `.env.local` y completa:

- `VITE_SUPABASE_URL` (Project URL de tu proyecto Supabase)
- `VITE_SUPABASE_PUBLISHABLE_KEY` (nueva “Publishable key” de Supabase) – recomendado
- o `VITE_SUPABASE_ANON_KEY` (clave anon anterior) – compatibilidad
- `VITE_FIRMAS_BUCKET` (nombre del bucket PRIVADO de Storage para la e.firma; ej. `fiscalia`)
 - `VITE_CFDI_BUCKET` (bucket PRIVADO para XML de CFDI; ej. `cfdi-xml`)

Tras cambiar variables, reinicia el servidor de Vite.

### Storage (e.firma)
1) Crea un bucket PRIVADO en Supabase Storage (por ejemplo, `fiscalia`).
2) Aplica policies RLS en `storage.objects` para permitir a cada usuario leer/escribir solo dentro de su carpeta `${auth.uid()}/...`.
	- Consulta `../docs/supabase_storage_policies.sql` y ejecuta ese SQL en el editor de SQL de Supabase ajustando el nombre del bucket si es necesario.

### Storage (CFDI XML)
1) Crea un bucket PRIVADO en Supabase Storage (por ejemplo, `cfdi-xml`).
2) Aplica políticas RLS por prefijo `${auth.uid()}/...` similares a las de e.firma (reemplazando el bucket_id por `cfdi-xml`).

### RLS en tablas de negocio (DB)
Para asegurar que cada usuario solo vea los datos de sus compañías:

1) Abre el editor de SQL en Supabase.
2) Copia y ejecuta el archivo `../docs/rls_business.sql`.
	- Habilita RLS y crea policies para `profiles`, `companies`, `company_members`, `cfdi`, `gastos_clasificados`, etc.
3) Verifica que puedes crear/leer tu empresa y CFDI desde la app.

### Backend para SAT (opcional pero recomendado)
Para sincronizar CFDI automáticamente desde el SAT:

- Configura un backend (FastAPI o Supabase Edge Function) con endpoints `/sat/sync` y `/sat/jobs/:id`.
- Añade `VITE_BACKEND_URL` en `.env.local` con la URL del backend.
- Consulta `../docs/sat_integration.md` y `../docs/sat_jobs.sql` para la tabla de jobs y RLS.

## Scripts
- `npm run dev` – servidor de desarrollo
- `npm run build` – build de producción
- `npm run preview` – previsualización del build

## Flujo
1. Registro de usuario (`/register`)
2. Confirmación vía email (si está activada)
3. Login (`/login`)
4. Acceso a `/dashboard` (ruta protegida)

## Siguientes pasos
- Perfil fiscal y carga de e.firma
- Importación manual de XML (drag & drop) y parsing
- Clasificación básica de gastos
- Cálculo de ISR/IVA mensual