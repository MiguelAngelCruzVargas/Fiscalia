# Catálogo de Funcionalidades de Fiscal-IA

Este documento describe las funcionalidades de la plataforma, organizadas por módulos y señalando su estado actual en el proyecto.

## Módulo 1: Cumplimiento Fiscal Automatizado (Núcleo)

Nota: Este catálogo refleja el objetivo funcional. Para el estado real y cómo correr cada pieza, ver `docs/estado_implementacion.md`.

- Descarga masiva de CFDI
  - Estado: Parcial (Mock listo; SAT real pendiente)
  - Hoy: Mock funcional end-to-end (jobs + storage + DB). SAT 2.0 real no implementado aún (queda por completar WS-Security y flujo de paquetes).
  - Endpoints: POST /sat/sync, GET /sat/jobs/:id, POST /sat/verify

- Clasificación de gastos con IA
  - Estado: Pendiente
  - Hoy: Tabla `gastos_clasificados` definida; faltan reglas/IA y UI de revisión.

- Cálculo de impuestos provisionales (ISR/IVA)
  - Estado: Funcional (MVP)
  - Hoy: Backend `/reports/monthly` calcula ISR/IVA a partir de CFDI; falta UI de gráficos/persistencia.

- Generación de DIOT
  - Estado: Pendiente
  - Hoy: Planificada; requiere agregaciones por proveedor y exportación CSV/Texto.

- Dashboard financiero básico
  - Estado: Funcional (MVP)
  - Hoy: Muestra conteo de CFDI; en modo demo auto-sincroniza mock SAT cuando no hay datos.

## Módulo 2: Gestión Contable Inteligente

- Conciliación bancaria
  - Estado: Pendiente

- Generación de pólizas contables
  - Estado: Pendiente

- Cuentas por cobrar y por pagar
  - Estado: Pendiente

- Gestión de activos fijos y depreciaciones
  - Estado: Pendiente

## Módulo 3: Optimización Estratégica (Premium)

- Análisis avanzado de deducciones
  - Estado: Pendiente

- Simulador de escenarios fiscales
  - Estado: Pendiente

- Asistente fiscal con IA
  - Estado: Pendiente

## Estado general y próximos pasos

1. Finalizar SAT real:
   - Completar `Sat20Client.request_download` y descarga real de paquetes.
   - Instalar xmlsec en el sistema (Windows) si falta; validar token SAT con `/sat/verify` y autenticación.
2. Enriquecer reportes:
   - Mostrar ISR en UI y permitir persistir a `taxes_monthly`.
3. Clasificación de gastos:
   - Reglas simples + embeddings; UI de revisión/corrección.
4. DIOT:
   - Generación de layout con base en CFDI de proveedores.

