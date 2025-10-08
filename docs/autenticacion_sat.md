# Estado y Pruebas de Autenticación SAT 2.0 (Descarga Masiva CFDI)

Este documento registra las comprobaciones realizadas para validar que el backend está listo para autenticarse contra el servicio de Descarga Masiva CFDI 2.0 del SAT y los pasos para una prueba completa con un usuario real.

> Fecha de verificación: 2025-10-01

---
## 1. Resumen Rápido

| Componente | Resultado | Detalle |
|------------|-----------|---------|
| Modo SAT | soap | `SAT_MODE=soap` |
| Demo desactivado | OK | `DEMO_MODE=false` |
| Variables Supabase | OK | `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE` presentes |
| xmlsec | Disponible | `xmlsec_available=true` |
| zeep | Instalado | Detectado en `/sat/self-check` |
| WSDL Autenticación | OK (200) | `Autenticacion.svc?wsdl` accesible |
| WSDL Solicitud | OK (200) | `SolicitaDescargaService.svc?wsdl` accesible |
| Operación Autentica | Encontrada | `Autentica` |
| Operaciones Solicitud | Encontradas | `SolicitaDescargaEmitidos`, `SolicitaDescargaRecibidos`, `SolicitaDescargaFolio` |
| Buckets (firmas / cfdi) | Existen | `fiscalia`, `cfdi-xml` |
| Tablas claves | Existen | `profiles, companies, sat_jobs, cfdi, taxes_monthly` |
| OpenSSL sistema | No detectado | `system_has_openssl=false` (no bloquea si xmlsec ya funciona) |

---
## 2. Evidencia de Endpoints de Diagnóstico

### 2.1 `/diag`
Respuesta (recortada):
```json
{
  "sat_mode": "soap",
  "demo_mode": "false",
  "supabase_env": true,
  "env_path_used": "D:\\FISCAL-IA\\backend\\.env",
  "env_path_exists": true,
  "xmlsec_available": true,
  "wsdl_auth": "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx/Autenticacion/Autenticacion.svc?wsdl",
  "wsdl_solicitud": "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx/SolicitaDescargaService.svc?wsdl",
  "supabase_ok": true
}
```

### 2.2 `/sat/self-check`
Campos relevantes:
```json
{
  "sat_mode": "soap",
  "demo_mode": false,
  "env": {
    "FIRMAS_BUCKET": "fiscalia",
    "CFDI_BUCKET": "cfdi-xml"
  },
  "soap_prereqs": {
    "zeep_installed": true,
    "xmlsec_installed": true,
    "httpx_installed": true,
    "wsdl_autenticacion_reachable": "OK(200)",
    "wsdl_solicitud_reachable": "OK(200)",
    "system_has_openssl": false,
    "clock_utc": "2025-10-01T23:16:54.972908Z"
  }
}
```
Tablas y buckets: todas existen.

### 2.3 `/sat/debug/ops`
```json
{
  "auth": ["Autentica"],
  "request": ["SolicitaDescargaEmitidos", "SolicitaDescargaFolio", "SolicitaDescargaRecibidos"],
  "request_signatures": {
    "SolicitaDescargaEmitidos": "solicitud: ns1:SolicitudDescargaMasivaTerceroEmitidos",
    "SolicitaDescargaRecibidos": "solicitud: ns1:SolicitudDescargaMasivaTerceroRecibidos",
    "SolicitaDescargaFolio": "solicitud: ns1:SolicitudDescargaMasivaTerceroFolio"
  }
}
```

---
## 3. Flujo Requerido para Prueba Completa de Autenticación
> Aún no se probó contra una e.firma real en esta sesión (faltó `user_id` con archivos reales). Estos pasos deben ejecutarse con un usuario que tenga su carpeta de e.firma cargada.

1. Verificar perfil y archivos:
   - `GET /sat/debug/profile/{user_id}`
   - Esperar: `exists=true`, `firma_ref` definido, lista con `.cer` y `.key`.
2. Verificar lectura de certificado:
   - `GET /sat/debug/firma/{user_id}`
   - Esperar: `ok=true`, `is_probably_csd=false`, vigencia futura, hash SHA256.
3. Inspección (metadatos RFC):
   - `POST /sat/inspect` body `{ "user_id":"<uuid>" }`
   - Revisar `rfc`, `is_probably_csd=false`.
4. Validar passphrase:
   - `POST /sat/verify` body `{ "user_id":"<uuid>", "passphrase":"..." }`
   - Esperar: `key_matches_cert=true`.
5. Autenticación SAT:
   - `POST /sat/auth` body `{ "user_id":"<uuid>", "passphrase":"..." }`
   - Esperar: `{ "ok": true, "token_len": > 100 }`.
6. Flujo de solicitud y verificación rápida (opcional):
   - `POST /sat/test-flow` body `{ "user_id":"<uuid>", "passphrase":"...", "kind":"recibidos" }`
   - Salida incluye: `request_id`, `packages_count` (0 si no hay CFDI recientes), `rfc_used`.

---
## 4. Notas Técnicas y Recomendaciones

| Tema | Observación | Acción sugerida |
|------|-------------|-----------------|
| system_has_openssl=false | xmlsec funciona igual, pero instalar OpenSSL mejora portabilidad | Instalar binarios si se enfrenta error de firma futuro |
| Diferencia RFC cert vs compañía | Se marca nota en job | Alinear FIEL con RFC de la compañía cuando sea posible |
| 5004 (sin información) | No es error, indica rango vacío | Mostrar mensaje claro en UI |
| Tokens no cacheados | Cada job autentica | Implementar cache in-memory (mejora rendimiento) |

---
## 5. Troubleshooting Rápido

| Síntoma | Posible causa | Paso siguiente |
|---------|---------------|----------------|
| `Fault del SAT en Autentica` con "verifying security" | CSD en lugar de FIEL, reloj desfasado, passphrase incorrecta, cert vencido | Revisar `inspect` (is_probably_csd), hora `/diag/time`, vigencia, passphrase |
| `Contraseña inválida o formato .key no soportado` | Passphrase incorrecta o `.key` corrupto / diferente del `.cer` | Confirmar archivos originales y passphrase exacta |
| `Certificado fuera de vigencia` | Certificado vencido | Renovar e.firma FIEL |
| Solicitud sin paquetes (`packages_count=0`) | No hay CFDI en rango o `5004` | Ampliar rango / confirmar actividad fiscal |
| `Error de transporte` | Conectividad, firewall, internet intermitente | Reintentar, probar curl directo a WSDL |

---
## 6. Próximos Pasos (Pendientes)
- [ ] Ejecutar prueba real con user_id y registrar token_len obtenido.
- [ ] Añadir caching de token (clave: hash cert + expiración 600s).
- [ ] Guardar en job: `auth_duration_ms`, `request_duration_ms` (para métricas).
- [ ] Parser XML robusto para cfdi descargados (actualmente regex heurística en `download_package_xmls`).
- [ ] Documentar códigos de estado SAT más frecuentes (5000, 5003, 5004, 5011) en UI.

---
## 7. Comandos de Referencia (PowerShell)
Ejemplos (sustituir `<UUID>` y `<PASS>`):
```powershell
# Inspección
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/sat/inspect -ContentType 'application/json' -Body '{"user_id":"<UUID>"}'

# Verificar passphrase
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/sat/verify -ContentType 'application/json' -Body '{"user_id":"<UUID>", "passphrase":"<PASS>"}'

# Autenticar
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/sat/auth -ContentType 'application/json' -Body '{"user_id":"<UUID>", "passphrase":"<PASS>"}'
```

---
## 8. Conclusión
Las capas previas a la autenticación (dependencias, WSDL, firma SOAP habilitada) están correctas. Falta ejecutar la prueba final con una e.firma real del usuario para cerrar la verificación end-to-end y, si procede, realizar la primera solicitud de paquetes (con probable resultado `5004` si el rango está vacío). Este documento se actualizará una vez capturado un `token_len` real.

---
_Actualizado automáticamente por asistente IA._
