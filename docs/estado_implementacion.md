# Estado de Implementación – Núcleo (Módulo 1)

Este documento mapea, con los mismos nombres que en los PDFs, el estado real de cada funcionalidad del Núcleo (Módulo 1) y cómo se usa hoy en el proyecto. Incluye contratos mínimos, endpoints/archivos implicados, y próximos pasos.

Leyenda de estado:
- Terminada: lista para uso (MVP o mejor)
- Parcial: existe parte utilizable pero no cumple todo el alcance
- Pendiente: aún no implementada

## 1) Descarga Masiva de CFDI

- Estado: Parcial
- Alcance actual:
  - Mock end-to-end funcionando: se generan CFDI falsos, se suben a Storage y se registran en DB. Sirve para probar UI, Storage y reportes.
  - SAT real (Descarga Masiva 2.0 vía SOAP): no implementado todavía (falta WS-Security completa y flujo de paquetes). Hay un cliente borrador y endpoints listos para integrar.
- Contrato (MVP actual – Mock):
  - Entrada: user_id, company_id, kind ('recibidos'|'emitidos'), date_from, date_to (opcional), passphrase (opcional)
  - Salida: job { id, status }, y posteriormente el job se actualiza con { total_found, total_downloaded }
- Endpoints/archivos:
  - Backend: POST /sat/sync, GET /sat/jobs/{id}
  - Código: `backend/app/routers/sat.py`, `backend/app/services/sat_provider.py` (orquestación), `backend/app/services/sat_sat20.py` (cliente SAT 2.0 – borrador)
  - Storage: bucket `CFDI_BUCKET` (default: `cfdi-xml`) → `{user_id}/{company_id}/{uuid}.xml`
  - DB: tabla `cfdi` (ver `docs/schema_supabase.sql`)
- Requisitos:
  - Mock: `SAT_MODE=mock` y (opcional) `DEMO_MODE=true` para permitir flujo sin e.firma
  - Real (pendiente): `SAT_MODE=soap`, `DEMO_MODE=false`, e.firma cargada (`profiles.firma_ref`) + passphrase; binarios y lib `xmlsec` instalados
- Próximos pasos:
  1. Implementar WS-Security completo en `Sat20Client.authenticate()` (firma con .cer/.key) y validar operación `Autentica`.
  2. Confirmar operaciones/nombres/params de los WSDL vigentes: `SolicitaDescarga`, `VerificaSolicitudDescarga`, `Descargar`.
  3. Manejo de errores y reintentos; registrar notas en `sat_jobs`.

## 2) Clasificación de Gastos con IA

- Estado: Pendiente
- Alcance deseado (PDFs): etiquetar automáticamente gastos (gasolina, papelería, etc.) y permitir corrección manual.
- Diseño propuesto (MVP):
  - Reglas deterministas por proveedor/concepto + extracción simple desde CFDI.
  - Tabla `gastos_clasificados` ya definida en `docs/schema_supabase.sql`.
  - UI de revisión/corrección en Reportes.
- Próximos pasos:
  1. Backend: endpoint para clasificar por lote una compañía/periodo.
  2. Frontend: vista de clasificación y edición.
  3. Posterior: agregar embeddings/IA ligera y feedback loop.

## 3) Cálculo de Impuestos Provisionales (ISR/IVA)

- Estado: Terminada (MVP)
- Alcance actual:
  - Backend calcula, por mes (YYYY-MM), ingresos/egresos, IVA cobrado/acreditable, IVA a pagar, ISR base y estimado (tasa configurable por régimen – RESICO/default).
- Contrato:
  - Entrada: company_id (query), persist (bool opcional)
  - Salida: lista de filas mensuales: { periodo, ingresos, egresos, iva_cobrado, iva_acreditable, iva_a_pagar, isr_base, isr }
- Endpoints/archivos:
  - Backend: GET `/reports/monthly`
  - Código: `backend/app/routers/reports.py`
  - DB: lee `cfdi` y opcionalmente guarda en `taxes_monthly` si `persist=true`
- Requisitos: variables `ISR_RATE_RESICO`, `ISR_RATE_DEFAULT` (opcional) y datos en `cfdi`.
- Próximos pasos: exponer en UI con gráficos y botón “Guardar a taxes_monthly”.

## 4) Generación de DIOT

- Estado: Pendiente
- Alcance deseado: generar layout/CSV DIOT con agregación por proveedor a partir de CFDI de egresos y complementos de pago.
- Próximos pasos:
  1. Agregaciones en backend (por RFC proveedor, tasa, etc.).
  2. Exportación CSV y descarga desde la web.

## 5) Dashboard Financiero Básico

- Estado: Terminada (MVP)
- Alcance actual:
  - Muestra conteo de CFDI y accesos a Perfil, Importar y Reportes.
  - En modo demo, auto-sincroniza mock SAT cuando no hay CFDI.
- Archivos: `web/src/routes/Dashboard.jsx` y cards en `web/src/components/dashboard/*`.

---

## Resumen de estado (Núcleo)

- Descarga Masiva de CFDI → Parcial (Mock listo; SAT real no implementado)
- Clasificación de Gastos con IA → Pendiente
- Cálculo de Impuestos Provisionales (ISR/IVA) → Terminada (MVP)
- Generación de DIOT → Pendiente
- Dashboard Financiero Básico → Terminada (MVP)

Para detalles de tablas, RLS y policies de Storage, ver:
- `docs/schema_supabase.sql`
- `docs/rls_business.sql`
- `docs/supabase_storage_policies_cfdi.sql` y (ajustado al bucket real de firmas)
