# Fiscal-IA Backend

Backend mínimo (FastAPI) para orquestar la descarga de CFDI desde SAT y persistir en Supabase.

Para el estado real de implementación (qué está listo, parcial o pendiente), consulta `../docs/estado_implementacion.md`.

## Endpoints

- POST /sat/sync
  - Body JSON: { user_id, company_id, kind: 'recibidos'|'emitidos', date_from?: 'YYYY-MM-DD', date_to?: 'YYYY-MM-DD' }
  - Respuesta: { id }
- GET /sat/jobs/{id} – estado/progreso
- POST /sat/verify – valida e.firma y contraseña; devuelve info del certificado

## Desarrollo local

1. Crear y activar venv (o usar la tarea de VS Code)
2. Instalar dependencias
3. Ejecutar servidor

## Variables de entorno

- SUPABASE_URL, SUPABASE_SERVICE_ROLE (para operar con storage/db del lado servidor)
- STORAGE buckets esperados: cfdi-xml, firmas (ajustar si cambian)
- SAT_MODE: 'mock' (default) o 'soap' (real SAT 2.0)
- DEMO_MODE: 'true'|'false' (si true, permite flujo demo sin e.firma)
- Opcional: ISR_RATE_RESICO, ISR_RATE_DEFAULT

## Requisitos SAT 2.0 (soap)

- Dependencias Python: zeep, lxml, xmlsec
- En Windows debes instalar los binarios de xmlsec/libxml2 en el sistema (xmlsec1). Busca paquetes precompilados o usa vcpkg/chocolatey. La librería python `xmlsec` necesita encontrar las DLLs en PATH.
- Se usa WS-Security para firmar la solicitud de Autenticación con .cer/.key + passphrase.
- Endpoint /sat/verify ayuda a probar .cer/.key y contraseña antes de llamar al SAT.

### Variables clave para SAT real

- SAT_MODE=soap
- DEMO_MODE=false
- FIRMAS_BUCKET=bucket con .cer/.key en Supabase Storage (coloca ambos bajo profiles.firma_ref)
- CFDI_BUCKET=cfdi-xml

### Flujo

1) Carga tu .cer y .key al bucket de `FIRMAS_BUCKET` y guarda la ruta base en `profiles.firma_ref`.
2) POST /sat/verify con { user_id, passphrase } para validar contraseña y cert.
3) POST /sat/sync con { user_id, company_id, kind, date_from, date_to, passphrase }.
4) GET /sat/jobs/{id} hasta status=success. Los XML se guardan en Storage y tabla `cfdi`.

