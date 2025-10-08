Este documento resume las funcionalidades identificadas en los PDFs y sugiere un plan de monetización y un roadmap inicial para llevar Fiscal-IA a producción.

1) Objetivo del producto
- Automatizar el cumplimiento fiscal y contable para pymes y personas físicas con actividad empresarial en México usando IA y conexión con SAT.

2) Público objetivo
- Personas físicas con actividad empresarial, RIF/RESICO, profesionistas independientes.
- Pymes con 1–50 empleados que usan CFDI y requieren control básico contable/fiscal.

3) Propuesta de valor
- Descarga automática de CFDI + clasificación de gastos con IA + cálculo de impuestos provisionales + DIOT + dashboard.
- Módulos avanzados: conciliación bancaria, pólizas automáticas, cuentas por cobrar/pagar, activos fijos, análisis de deducciones, simulador fiscal y asistente IA.

4) MVP (8–10 semanas)
- Autenticación (Supabase Auth)
- Perfil fiscal: RFC + carga de e.firma (.cer/.key) + passphrase
- Servicio de descarga masiva de CFDI (vía scraping/robot SAT o proveedores API: Covesa/Facturapi/SwSapien; empezar con importación de XML manual como fallback)
- Clasificación básica de gastos con reglas + IA ligera (embeddings/keywords)
- Cálculo simple de ISR/IVA mensual (basado en CFDI ingresos/egresos)
- Dashboard básico (ingresos/gastos/IVA/ISR)

5) Roadmap posterior
- DIOT generator (CSV)
- Corrección manual de clasificaciones + feedback loop
- Conciliación bancaria (import CSV/Excel)
- Pólizas automáticas
- CxC/CxP
- Activos fijos y depreciaciones
- Simulador fiscal
- Asistente IA

6) Monetización (modelo propuesto)
- Freemium:
  • Gratis: Importación manual de XML + dashboard básico + 50 CFDI/mes.
  • Pro: $199 MXN/mes: Descarga SAT automática + clasificación IA + cálculo ISR/IVA + DIOT + 1,000 CFDI/mes.
  • Business: $499 MXN/mes: Conciliación bancaria + pólizas automáticas + CxC/CxP + 10,000 CFDI/mes + multi-empresa.
- Add-ons:
  • Asistente IA fiscal + simulador: $99 MXN/mes.
  • Procesamiento extra de CFDIs (por bloque).
- Descuentos anual/semestre, prueba 14 días.

7) Arquitectura propuesta
- Frontend: Next.js (React) + Tailwind.
- Backend: Next.js API routes / Edge Functions de Supabase.
- Auth y DB: Supabase (Postgres + RLS)
- Storage: Supabase Storage (XML/CSV/firmas encriptadas)
- Jobs: Supabase Scheduled Functions / Worker externo (scraping SAT si aplica)
- Pagos: Stripe (planes + webhook para activar features)
- Observabilidad: Sentry/Logflare, PostHog (eventos de uso)

8) Datos y tablas (borrador)
- users (supabase auth)
- profiles: user_id, rfc, legal_name, regime, sat_status, firma_encrypted_ref
- companies: id, owner_id, rfc, name
- company_members: company_id, user_id, role
- cfdi: id, company_id, uuid, tipo (I/E/P), emisor_rfc, receptor_rfc, fecha, subtotal, impuestos, total, xml_ref, status
- gastos_clasificados: cfdi_id, categoria, subcategoria, score, fuente (regla/ia), corrected_by
- taxes_monthly: company_id, periodo, isr_base, isr, iva_cobrado, iva_acreditable, iva_a_pagar
- bank_statements: id, company_id, file_ref, periodo
- bank_tx: id, statement_id, fecha, concepto, monto, cuenta, match_cfdi_id?
- assets: company_id, cfdi_id, descripcion, fecha_inicio, metodo, porcentaje, vida_util, depreciacion_acumulada
- plans: plan_id, name, limits (jsonb), price_mxn
- subscriptions: user_id/company_id, plan_id, status, current_period_end
- usage_counters: company_id, metric, period, count

9) Riesgos y mitigaciones
- Interacción con SAT (capchas/cambios): empezar con importación manual + usar proveedores o headless browser solo para pruebas.
- Seguridad e.firma: cifrado AES-256 en repositorio seguro, llaves en KMS, nunca en texto plano.
- Cumplimiento legal: Términos y consentimiento explícito para uso de e.firma y descarga de CFDI.

10) Métricas clave
- Activaciones (perfil fiscal completo)
- CFDIs importados/semanales
- Tiempo de valor (primer dashboard generado)
- Retención 4/8/12 semanas
- Conversión a Pro/Business

11) Próximos pasos sugeridos
- Crear repo y proyecto Next.js + Supabase
- Esquema inicial de Postgres en Supabase
- Flujo de importación manual de XML + parser CFDI 3.3/4.0
- Clasificador simple de gastos (reglas + keywords)
- Cálculo IVA/ISR (RESICO PF de inicio)
- Stripe sandbox y paywall por plan
