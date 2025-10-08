# Integración con SAT-CFDI: alcance, decisiones y plan

Este documento resume qué ofrece la librería SAT-CFDI (https://github.com/SAT-CFDI/python-satcfdi), qué partes aprovecharemos en nuestra app, qué no aplica, y el plan paso a paso para integrarla. La idea es mantener control y visibilidad del avance.

## Resumen
- SAT-CFDI es una "caja de herramientas fiscal" (CFDI, Retenciones, PACs, Descarga Masiva, utilidades SAT).
- Nosotros ya tenemos backend FastAPI + Supabase, endpoints, UI y flujos propios. SAT-CFDI nos ayuda en la capa fiscal (firmas, plantillas, llamadas SAT/PAC) pero no sustituye nuestra capa de producto (usuarios, RLS, jobs, reportes, UI).

## Alcance de SAT-CFDI (qué trae)
- CFDI 3.2/3.3/4.0: armado/validación, complementos (Nómina, Pagos, etc.), representación PDF/HTML/JSON.
- Retenciones 1.0/2.0 y Contabilidad Electrónica 1.3.
- Integración con PACs (Diverza, Finkok, Prodigia, SW Sapien) para timbrado/cancelación.
- Descarga Masiva (Autenticación y solicitudes base).
- Utilidades SAT: Validación de comprobantes, listado 69B, LCO, validación de RFC/razón social, DIOT, constancia de situación fiscal.

## Mapeo a nuestra app (qué usaremos vs. no)
- Sí aprovecharemos de inicio:
  - Autenticación y flujo base de Descarga Masiva 2.0 (para reducir fricción WS‑Security/XMLDSig).
  - Validación de CFDI (estructura/sellos) como servicio interno.
  - Representación (PDF/HTML/JSON) para previsualización/descarga de CFDI en el dashboard.
  - Utilidades SAT: 69B, LCO, validación de RFC, constancia.
- Evaluar después (requiere contrato/credenciales/operación):
  - Integraciones con PACs para timbrado/cancelación por tenant.
- No reemplaza (queda en nuestra plataforma):
  - Gestión de usuarios, perfiles, RLS (Supabase), almacenamiento, auditoría, jobs, colas, métricas, dashboards y reportes de negocio.

## Decisiones actuales
- Mantener nuestro cliente SAT 2.0 y habilitar una ruta opcional con SAT-CFDI.
- Variables de entorno de control:
  - SAT_USE_SATCFDI=1 para intentar SAT-CFDI primero en autenticación.
  - SAT_SAVE_SOAP=1 y SAT_DEBUG=1 para capturar artefactos y trazas.
- Entorno Windows: xmlsec/firmas son más estables en Linux/WSL; si hay fricciones, considerar correr backend en WSL o contenedor.

## Estado de implementación (checklist)
- [x] Endpoints de diagnóstico (inspección/validación de e.firma).
- [x] Autenticación SAT 2.0 propia (Zeep + manual xmlsec) con artefactos.
- [x] Ruta opcional de autenticación vía SAT-CFDI integrada en `Sat20Client`.
- [ ] Traer SAT-CFDI como dependencia estable (opción A: vendor en `external/python-satcfdi`; opción B: instalar por PyPI y ajustar import).
- [ ] Validar obtención de token real con SAT_USE_SATCFDI=1 en ambiente del cliente.
- [ ] Añadir endpoints utilitarios (69B, LCO, validar RFC, constancia) usando SAT-CFDI.
- [ ] Añadir endpoints de representación (PDF/HTML/JSON) y almacenar en Supabase Storage.
- [ ] Tests mínimos y cachés para evitar límites SAT.
- [ ] Evaluar conectores PAC por tenant (si aplica).

## Cómo habilitar SAT-CFDI en nuestro backend
Dos caminos posibles (elegir uno):

1) Vendor del repo (camino ya soportado por el código actual)
- Clonar `python-satcfdi` en `external/python-satcfdi` (ruta relativa al repo).
- Exportar variables de entorno:
  - `SAT_USE_SATCFDI=1`
  - Opcional: `SAT_SAVE_SOAP=1`, `SAT_DEBUG=1`
- Reiniciar backend y consumir `GET/POST /sat/auth`.

2) Instalar por PyPI (recomendado a futuro)
- Agregar dependencia `satcfdi` a `backend/requirements.txt` y ajustar `_satcfdi_authenticate` para importar directo sin `external/`.
- Mantener el resto igual (env vars y endpoints).

Dependencias típicas: `cryptography`, `lxml`, `requests`, `pyOpenSSL`, `beautifulsoup4`, `packaging`.

## Endpoints involucrados
- `/sat/auth` — ahora intenta SAT-CFDI primero si `SAT_USE_SATCFDI=1` y, si falla, recurre a Zeep/manual.
- Descarga: `/sat/request`, `/sat/wait`, `/sat/download` (o equivalentes ya presentes en servicios) usan el token obtenido.
- Próximos (a crear):
  - `/sat/utils/69b`, `/sat/utils/lco`, `/sat/utils/validar-rfc`, `/sat/utils/constancia`.
  - `/cfdi/validar` (recibe XML/UUID+RFC) y `/cfdi/render/{uuid}?formato=pdf|html|json`.

## Riesgos y mitigaciones
- WS‑Security sensible (Timestamp, RSA‑SHA1, c14n). Mitigación: usar SAT-CFDI para Autenticación; conservar artefactos (SAVE_SOAP) para auditoría.
- Límite o cambios del SAT: añadir cachés y manejo de errores con códigos conocidos (5003, 5004, 5011, etc.).
- Windows + xmlsec: preferir WSL/Linux si aparecen errores de firma.
- PACs: operación real requiere contratos, credenciales y monitoreo.

## Próximos pasos
1) Elegir estrategia de instalación (vendor vs PyPI) y completar setup.
2) Probar `/sat/auth` con `SAT_USE_SATCFDI=1`, guardar artefactos y confirmar token.
3) Publicar endpoints utilitarios + representación y conectarlos al dashboard.
4) Añadir pruebas mínimas y caching (Supabase) para utilidades SAT.
5) Si aplica, parametrizar y probar timbrado con un PAC piloto.

## Apéndice: variables de entorno relevantes
- SAT_USE_SATCFDI: 1/0 — usa SAT-CFDI primero para Autenticación.
- SAT_MANUAL_AUTH: 1/0 — fuerza modo manual xmlsec (fallback).
- SAT_FORCE_ALG / SAT_FORCE_DIGEST: controla algoritmos en modo manual.
- SAT_SAVE_SOAP: 1/0 — guarda `sat_auth_envelope.xml` y respuesta.
- SAT_DEBUG: 1/0 — logs detallados.
