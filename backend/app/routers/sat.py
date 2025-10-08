from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from fastapi.responses import StreamingResponse, JSONResponse, Response
import os
import io
from ..services.sat_provider import SatProvider, SatKind
try:  # type: ignore
    from ..services.sat_job_example import SatDownloader  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    SatDownloader = None  # type: ignore
from ..services.sat_sat20 import Sat20Client

router = APIRouter()

# Debug: log when this router file is imported to verify hot-reload is using the expected path.
try:  # pragma: no cover - sólo diagnóstico
    import logging, os as _os
    logging.warning(f"[sat.router] Importing router from path={__file__} pid={_os.getpid()}")
except Exception:
    pass

class SatSyncRequest(BaseModel):
    user_id: str
    company_id: str
    kind: SatKind
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    passphrase: Optional[str] = None  # Contraseña de la e.firma (no se guarda)
    tipo_solicitud: Optional[str] = None  # 'CFDI' | 'Metadata' (solo modo SOAP real)

    @field_validator('date_from', 'date_to')
    @classmethod
    def validate_date(cls, v):
        if v is None or v == '':
            return None
        if len(v) != 10:
            raise ValueError('Formato de fecha debe ser YYYY-MM-DD')
        return v

@router.post('/sync')
def sync_cfdi(req: SatSyncRequest, background: BackgroundTasks):
    try:
        provider = SatProvider()
        job_id = provider.enqueue_sync(
            user_id=req.user_id,
            company_id=req.company_id,
            kind=req.kind,
            date_from=req.date_from,
            date_to=req.date_to,
            tipo_solicitud=req.tipo_solicitud,
        )
        # Procesamiento en background para no bloquear la respuesta
        background.add_task(
            provider.process_job,
            job_id=job_id,
            user_id=req.user_id,
            company_id=req.company_id,
            kind=req.kind,
            date_from=req.date_from,
            date_to=req.date_to,
            passphrase=req.passphrase,
            tipo_solicitud=req.tipo_solicitud,
        )
        return {"id": job_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/sync-dev')
def sync_cfdi_dev(
    background: BackgroundTasks,
    user_id: str = Query(...),
    company_id: str = Query(...),
    kind: SatKind = SatKind.recibidos,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    passphrase: Optional[str] = Query(None, description="Contraseña e.firma (solo DEV, no usar en prod por URL)"),
    tipo_solicitud: Optional[str] = Query(None, description="CFDI|Metadata (solo SOAP real)"),
):
    """Versión GET de /sat/sync para desarrollo rápido sin construir JSON.

    ADVERTENCIA: La passphrase via query string NO debe usarse en producción.
    """
    try:
        provider = SatProvider()
        job_id = provider.enqueue_sync(
            user_id=user_id,
            company_id=company_id,
            kind=kind,
            date_from=date_from,
            date_to=date_to,
            tipo_solicitud=tipo_solicitud,
        )
        background.add_task(
            provider.process_job,
            job_id=job_id,
            user_id=user_id,
            company_id=company_id,
            kind=kind,
            date_from=date_from,
            date_to=date_to,
            passphrase=passphrase,
            tipo_solicitud=tipo_solicitud,
        )
        return { 'id': job_id, 'status': 'queued', 'kind': kind, 'tipo_solicitud': tipo_solicitud }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/jobs/{job_id}')
def get_job(job_id: str):
    try:
        provider = SatProvider()
        job = provider.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado")
        return job
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/debug/job-trace/{job_id}')
def debug_job_trace(job_id: str):
    """Devuelve campos clave de un sat_job para diagnóstico rápido (no requiere passphrase)."""
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table('sat_jobs').select('*').eq('id', job_id).maybe_single().execute()
        data = getattr(resp, 'data', None)
        if not data:
            raise HTTPException(status_code=404, detail='job no encontrado')
        keep = ['id','status','error','note','tipo_solicitud_final','fallback_from_cfdi','request_meta','request_error','fallback_error','request_meta_first','fallback_meta','verify_trace','sat_request_id','auth_ms','request_ms','verify_ms','download_ms','total_found','total_downloaded','created_at','updated_at']
        slim = {k: data.get(k) for k in keep}
        return {'job': slim}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VerifyRequest(BaseModel):
    user_id: str
    passphrase: Optional[str] = None


@router.post('/verify')
def verify_firma(req: VerifyRequest):
    try:
        provider = SatProvider()
        info = provider.verify_firma(req.user_id, req.passphrase)
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/verify/{user_id}')
def verify_firma_get(user_id: str, passphrase: Optional[str] = Query(default=None)):
    """Conveniencia GET sólo para desarrollo (la passphrase iría en la URL)."""
    return verify_firma(VerifyRequest(user_id=user_id, passphrase=passphrase))


class InspectRequest(BaseModel):
    user_id: str


@router.post('/inspect')
def inspect_firma(req: InspectRequest):
    """Analiza el .cer y devuelve sugerencias para autocompletar el perfil (RFC, nombre, vigencia)."""
    try:
        provider = SatProvider()
        return provider.inspect_firma(req.user_id)
    except Exception as e:
        # Clasificar error para que el frontend pueda dar feedback claro
        msg = str(e)
        code = 'unknown'
        lowered = msg.lower()
        if 'perfil no encontrado' in lowered:
            code = 'profile_not_found'
        elif 'perfil sin referencia' in lowered or 'firma_ref' in lowered:
            code = 'missing_firma_ref'
        elif 'no se encontró archivo .cer' in lowered:
            code = 'cer_not_found'
        elif 'no se encontraron archivos .cer y .key' in lowered:
            code = 'cer_key_missing'
        elif 'no se pudo leer el certificado' in lowered or 'certificado .cer inválido' in lowered:
            code = 'cer_parse_error'
        raise HTTPException(status_code=400, detail={'message': msg, 'code': code})


@router.get('/inspect/{user_id}')
def inspect_firma_get(user_id: str):
    """Versión GET para pruebas rápidas en navegador."""
    return inspect_firma(InspectRequest(user_id=user_id))


class AuthRequest(BaseModel):
    user_id: str
    passphrase: str


@router.post('/auth')
def auth_sat(req: AuthRequest):
    """Prueba directa de autenticación SAT 2.0. Devuelve tamaño del token (no el token)."""
    try:
        provider = SatProvider()
        # Validaciones previas: tipo de certificado y vigencia
        try:
            info = provider.inspect_firma(req.user_id)
            if info.get('is_probably_csd'):
                raise HTTPException(status_code=400, detail='El certificado parece ser CSD. La autenticación del SAT requiere e.firma (FIEL). Sube tu FIEL (.cer/.key) con su contraseña.')
            # Validar vigencia
            from datetime import datetime as _dt
            vf, vt = info.get('valid_from'), info.get('valid_to')
            if isinstance(vf, str) and isinstance(vt, str):
                now = _dt.utcnow().isoformat()
                if now < vf or now > vt:
                    raise HTTPException(status_code=400, detail=f'Certificado fuera de vigencia (valid_from={vf}, valid_to={vt}).')
        except HTTPException:
            raise
        except Exception:
            # Si falla la inspección, continuamos, la autenticación reportará el problema
            pass

        cer, key = provider.load_firma(req.user_id)  # type: ignore[attr-defined]
        client = Sat20Client()
        token = client.authenticate(cer, key, req.passphrase)
        return { 'ok': True, 'token_len': len(token) }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/auth/{user_id}')
def auth_sat_get(user_id: str, passphrase: str = Query(...)):
    """Versión GET para pruebas locales (NO producción)."""
    return auth_sat(AuthRequest(user_id=user_id, passphrase=passphrase))


class ProfileUpsertRequest(BaseModel):
    user_id: str
    rfc: str
    firma_ref: str


@router.post('/profile/upsert')
def profile_upsert(req: ProfileUpsertRequest):
    """Crea o actualiza una fila en profiles (helper rápido para desarrollo).

    NOTA: En producción proteger con auth/RLS adecuada."""
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        payload = {
            'user_id': req.user_id,
            'rfc': req.rfc.upper().strip(),
            'firma_ref': req.firma_ref.strip().rstrip('/'),
        }
        # upsert: si existe user_id lo actualiza
        resp = sb.table('profiles').upsert(payload, on_conflict='user_id').execute()
        data = getattr(resp, 'data', None)
        return { 'ok': True, 'profile': data }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/cfdi/list')
def list_cfdi(
    company_id: str = Query(..., description="UUID de la compañía"),
    limit: int = Query(10, ge=1, le=200),
    offset: int = Query(0, ge=0),
    uuid: Optional[str] = Query(None, description="Filtrar por UUID exacto opcional"),
    kind: Optional[str] = Query(None, description="Filtro rápido por tipo de comprobante I/E/P/N"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD desde"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD hasta (inclusive)"),
):
    """Lista CFDIs minimal (uuid, fecha, emisor_rfc, receptor_rfc, total) para pruebas.

    NOTA: Este endpoint asume que la política RLS limita el acceso por company_id al propietario.
    En producción añadir autenticación/JWT y asociación user_id->company.
    """
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        query = sb.table('cfdi').select('uuid,fecha,emisor_rfc,receptor_rfc,total,tipo').eq('company_id', company_id)
        if uuid:
            query = query.eq('uuid', uuid)
        if kind:
            query = query.eq('tipo', kind)
        if date_from:
            query = query.gte('fecha', date_from)
        if date_to:
            query = query.lte('fecha', date_to)
        resp = query.range(offset, offset + limit - 1).execute()
        data = getattr(resp, 'data', None)
        if not isinstance(data, list):
            data = []
        return { 'items': data, 'count': len(data), 'limit': limit, 'offset': offset }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/cfdi/{uuid}/raw')
def raw_cfdi(uuid: str):
    """Devuelve el XML original del CFDI desde Storage.

    Usa la columna 'xml_ref' en la tabla 'cfdi' que apunta al path en el bucket (CFDI_BUCKET o 'cfdi-xml').
    """
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table('cfdi').select('xml_ref').eq('uuid', uuid).maybe_single().execute()
        data = getattr(resp, 'data', None)
        if not data or not data.get('xml_ref'):
            raise HTTPException(status_code=404, detail='CFDI no encontrado')
        xml_ref = data['xml_ref']
        bucket = os.environ.get('CFDI_BUCKET', 'cfdi-xml')
        xml_bytes = sb.storage.from_(bucket).download(xml_ref)
        if not xml_bytes:
            raise HTTPException(status_code=404, detail='XML no encontrado en storage')
        # Aseguramos media_type correcto
        return Response(content=xml_bytes, media_type='application/xml')
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/self-check')
def self_check():
    try:
        provider = SatProvider()
        return provider.self_check()  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RunNowRequest(BaseModel):
    user_id: str
    company_id: str
    kind: SatKind
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    passphrase: Optional[str] = None


@router.post('/run-now')
def run_now(req: RunNowRequest):
    """Ejecuta la sincronización inmediatamente (síncrono) usando el helper.

    Útil para validar el núcleo en modo mock/demos. En modo 'soap' requiere e.firma.
    """
    try:
        if SatDownloader is None:
            raise RuntimeError('SatDownloader no disponible')
        runner = SatDownloader()
        out = runner.run(
            user_id=req.user_id,
            company_id=req.company_id,
            kind=req.kind.value,
            date_from=req.date_from,
            date_to=req.date_to,
            passphrase=req.passphrase,
        )
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Endpoints de prueba rápida de flujo completo SAT (diagnóstico controlado) ---
class TestFlowRequest(BaseModel):
    user_id: str
    passphrase: str
    kind: SatKind = SatKind.recibidos
    rfc: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    # Controles opcionales para probar filtros SAT sin reiniciar
    tipo_solicitud: Optional[str] = None  # 'CFDI' o 'Metadata'
    estado_comprobante: Optional[str] = None  # '0' (vigentes) o '1' (cancelados)
    tipo_comprobante: Optional[str] = None  # 'I','E','P','N'
    # Overrides de autenticación/WS-Security (diagnóstico)
    manual_auth: Optional[bool] = None
    force_alg: Optional[str] = None  # 'rsa-sha1' | 'rsa-sha256' | 'auto'
    force_digest: Optional[str] = None  # 'sha1' | 'sha256'
    wsse_bst: Optional[bool] = None
    solicitud_manual: Optional[bool] = None  # True fuerza SAT_SOLICITUD_MANUAL=1, False=0
    full_lib: Optional[bool] = None  # True fuerza SAT_USE_SATCFDI_FULL=1 para probar librería completa


@router.post('/test-flow')
def test_flow(req: TestFlowRequest):
    """Prueba controlada: autentica, solicita, verifica y lista paquetes.

    - No expone el token; sólo longitud.
    - Si encuentra paquetes, no descarga todos los XML; devuelve conteo.
    """
    try:
        provider = SatProvider()
        cer, key = provider.load_firma(req.user_id)  # type: ignore[attr-defined]
        client = Sat20Client()

        # Permitir overrides de entorno para autenticación en esta llamada
        import os as _os
        from typing import Dict, Optional as _Optional
        _restore: Dict[str, _Optional[str]] = {}
        def _setenv(k: str, v: Optional[str]):
            _restore[k] = _os.environ.get(k)
            if v is None:
                if k in _os.environ:
                    del _os.environ[k]
            else:
                _os.environ[k] = v

        try:
            if req.manual_auth is not None:
                _setenv('SAT_MANUAL_AUTH', '1' if req.manual_auth else '0')
            if req.force_alg is not None:
                if req.force_alg.lower() == 'auto':
                    _setenv('SAT_FORCE_ALG', None)
                else:
                    _setenv('SAT_FORCE_ALG', req.force_alg)
            if req.force_digest is not None:
                _setenv('SAT_FORCE_DIGEST', req.force_digest)
            if req.wsse_bst is not None:
                _setenv('SAT_WSSE_BST', '1' if req.wsse_bst else '0')
            if req.solicitud_manual is not None:
                _setenv('SAT_SOLICITUD_MANUAL', '1' if req.solicitud_manual else '0')
            if req.full_lib is not None:
                _setenv('SAT_USE_SATCFDI_FULL', '1' if req.full_lib else '0')

            token = client.authenticate(cer, key, req.passphrase)
        finally:
            for k, v in _restore.items():
                if v is None:
                    if k in _os.environ:
                        del _os.environ[k]
                else:
                    _os.environ[k] = v
        out = { 'ok': True, 'token_len': len(token) }

        # Determinar RFC a usar: preferimos el del certificado para evitar 'Sello No Corresponde al RFC'
        cert_rfc: Optional[str] = None
        profile_rfc: Optional[str] = None
        try:
            info = provider.inspect_firma(req.user_id)
            cert_rfc = (info.get('rfc') or info.get('rfc_profile') or '').upper() or None
        except Exception:
            cert_rfc = None
        try:
            prof = provider._get_profile(req.user_id, require_rfc=False)  # type: ignore[attr-defined]
            profile_rfc = (prof.get('rfc') or '').upper() or None
        except Exception:
            profile_rfc = None
        # Elegir RFC final
        rfc = (req.rfc or cert_rfc or profile_rfc)
        if not rfc:
            raise HTTPException(status_code=400, detail='No se pudo determinar el RFC objetivo (ni certificado ni perfil tienen RFC).')
        # Si el RFC solicitado o de perfil difiere del certificado, forzamos usar el del certificado
        if cert_rfc and rfc != cert_rfc:
            rfc = cert_rfc
            # anotamos en salida para visibilidad
            out['rfc_overridden_to_cert'] = True  # type: ignore[index]
            out['cert_rfc'] = cert_rfc  # type: ignore[index]

        # Rangos por defecto: últimos 3 días
        from datetime import datetime as _dt, timedelta as _td
        df = req.date_from or (_dt.utcnow() - _td(days=3)).strftime('%Y-%m-%d')
        dt = req.date_to or _dt.utcnow().strftime('%Y-%m-%d')

        # 1) Solicitar descarga (capturando metadatos de rechazo para diagnóstico)
        try:
            req_id = client.request_download(
                token,
                rfc,
                df,
                dt,
                req.kind.value,
                solicitante_rfc=rfc,
                tipo_solicitud_override=(req.tipo_solicitud or None),
                estado_comprobante_override=(req.estado_comprobante or None),
                tipo_comprobante_override=(req.tipo_comprobante or None),
                cer_bytes=cer,
                key_bytes=key,
                key_passphrase=req.passphrase,
            )
            out['rfc_used'] = rfc  # type: ignore[index]
            out['request_id'] = req_id  # type: ignore[index]
            out['tipo_solicitud_final'] = req.tipo_solicitud or 'CFDI'  # type: ignore[index]
        except Exception as e:
            # Fallback automático: si es un 301 con mensaje de cancelados, reintentar como Metadata
            err_txt = str(e)
            meta_first = getattr(client, '_last_request_meta', None) or {}
            fallback_attempted = False
            if 'CodEstatus=301' in err_txt and 'cancelad' in err_txt.lower() and (req.tipo_solicitud or 'CFDI').upper() == 'CFDI':
                try:
                    fallback_attempted = True
                    req_id = client.request_download(
                        token,
                        rfc,
                        df,
                        dt,
                        req.kind.value,
                        solicitante_rfc=rfc,
                        tipo_solicitud_override='Metadata',
                        estado_comprobante_override=None,
                        tipo_comprobante_override=None,
                        cer_bytes=cer,
                        key_bytes=key,
                        key_passphrase=req.passphrase,
                    )
                    out['rfc_used'] = rfc  # type: ignore[index]
                    out['request_id'] = req_id  # type: ignore[index]
                    out['tipo_solicitud_final'] = 'Metadata'  # type: ignore[index]
                    out['fallback_from_cfdi'] = True  # type: ignore[index]
                    out['request_meta_first'] = meta_first  # type: ignore[index]
                except Exception as e2:
                    # Fallback también falló: reportar ambos
                    meta_second = getattr(client, '_last_request_meta', None) or {}
                    out['request_error'] = err_txt  # type: ignore[index]
                    out['request_meta'] = meta_first  # type: ignore[index]
                    out['fallback_error'] = str(e2)  # type: ignore[index]
                    if meta_second:
                        out['fallback_meta'] = meta_second  # type: ignore[index]
            if not out.get('request_id'):
                # No se logró solicitud (sin fallback exitoso)
                # Adjuntar envelope snippet si existe
                try:
                    if os.path.exists('sat_request_envelope.xml'):
                        with open('sat_request_envelope.xml','rb') as fh:
                            env_bytes = fh.read(1500)
                        import base64 as _b64
                        out['request_envelope_b64'] = _b64.b64encode(env_bytes).decode('ascii')  # type: ignore[index]
                except Exception:
                    pass
                if not fallback_attempted:
                    out['request_error'] = err_txt  # type: ignore[index]
                    if meta_first:
                        out['request_meta'] = meta_first  # type: ignore[index]
                raise HTTPException(status_code=400, detail=out)

        # 2) Verificar (polling corto de diagnóstico)
        # Si no se obtuvo request_id (falló y no hubo fallback), devolvemos early (aunque ya se lanzó HTTPException antes)
        if 'request_id' not in out:
            return out
        try:
            pkgs = client.wait_and_list_packages(token, out['request_id'])
            out['packages_count'] = len(pkgs)  # type: ignore[index]
            out['packages'] = pkgs[:5]  # muestra primeros
            # Extraer traza si se activó SAT_TRACE_VERIFY=1
            trace = getattr(client, '_last_verify_trace', None)
            if trace:
                out['verify_trace'] = trace  # type: ignore[index]
        except Exception as e:
            out['verify_error'] = str(e)  # type: ignore[index]
            trace = getattr(client, '_last_verify_trace', None)
            if trace:
                out['verify_trace'] = trace  # type: ignore[index]

        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/test')
def test_flow_get(
    user_id: str,
    passphrase: str,
    kind: SatKind = SatKind.recibidos,
    rfc: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    tipo_solicitud: Optional[str] = None,
    estado_comprobante: Optional[str] = None,
    tipo_comprobante: Optional[str] = None,
):
    """Versión GET del flujo de prueba (para rapidez en dev)."""
    return test_flow(TestFlowRequest(
        user_id=user_id,
        passphrase=passphrase,
        kind=kind,
        rfc=rfc,
        date_from=date_from,
        date_to=date_to,
        tipo_solicitud=tipo_solicitud,
        estado_comprobante=estado_comprobante,
        tipo_comprobante=tipo_comprobante,
    ))


@router.get('/debug/profile/{user_id}')
def debug_profile(user_id: str):
    """Endpoint de diagnóstico: devuelve perfil completo y archivos de e.firma.

    Uso: GET /sat/debug/profile/<user_uuid>
    No expone contenido de archivos, sólo nombres; no requiere passphrase.
    """
    try:
        provider = SatProvider()
        return provider.debug_profile(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/debug/firma/{user_id}')
def debug_firma(user_id: str):
    """Diagnóstico rápido: confirma lectura de .cer/.key y metadatos mínimos sin passphrase.

    Uso: GET /sat/debug/firma/<user_uuid>
    Devuelve tamaños, hash SHA256 del .cer y fechas de vigencia.
    """
    try:
        provider = SatProvider()
        return provider.debug_firma(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/debug/last-request')
def debug_last_request():  # pragma: no cover - diagnóstico
    """Devuelve snippets base64 de los últimos envelopes/request/response guardados si SAT_SAVE_SOAP=1.

    Archivos considerados: sat_auth_envelope.xml, sat_request_envelope.xml, sat_request_response.xml.
    Solo devuelve primeros ~4000 bytes de cada uno codificados en base64 para no saturar la respuesta.
    """
    import base64, os
    files = ['sat_auth_envelope.xml','sat_request_envelope.xml','sat_request_response.xml','sat_auth_fault_response.xml']
    out = {}
    for fname in files:
        if os.path.exists(fname):
            try:
                with open(fname,'rb') as fh:
                    data = fh.read(4000)
                out[fname] = base64.b64encode(data).decode('ascii')
            except Exception as e:
                out[fname] = f'error:{e}'
    return out


@router.get('/debug/build-info')
def debug_build_info():  # pragma: no cover
    """Devuelve información de versión del código cargado para diagnosticar si el servidor corriendo
    corresponde a la versión más reciente del archivo sat.py.

    Incluye:
      - mtime (fecha de modificación) del archivo sat.py en disco según el proceso actual
      - un hash sha1 corto de su contenido
      - process_id para confirmar qué proceso atiende
    """
    import os, hashlib
    path = __file__
    try:
        with open(path,'rb') as fh:
            data = fh.read()
        sha = hashlib.sha1(data).hexdigest()[:12]
    except Exception as e:
        sha = f'error:{e}'
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        mtime = None
    return {
        'file': path,
        'mtime': mtime,
        'sha1_12': sha,
        'pid': os.getpid(),
        'has_fallback_logic': True,  # bandera manual para confirmar que es la versión parcheada
    }


@router.get('/debug/routes')
def debug_routes():  # pragma: no cover - endpoint de diagnóstico
    """Lista todas las rutas registradas actualmente en la app.

    Útil cuando parece que cambios al archivo no se reflejan (hot-reload).
    NOTA: Debe ser accesible como /sat/debug/routes. Si no aparece en /openapi.json,
    entonces estás ejecutando un proceso que no cargó esta versión de sat.py.
    """
    try:
        # La app quedará disponible cuando el router se monte; introspeccionamos via router.routes
        out = []
        for r in router.routes:  # type: ignore[attr-defined]
            methods = list(getattr(r, 'methods', []) or [])
            path = getattr(r, 'path', None)
            name = getattr(r, 'name', None)
            out.append({'path': path, 'methods': methods, 'name': name})
        # Ordenar para consistencia
        out.sort(key=lambda x: (x['path'] or '', ','.join(x['methods'])))
        return {'count': len(out), 'routes': out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/debug/firma-files/{user_id}')
def debug_firma_files(user_id: str):
    """Lista sólo los nombres de archivos bajo la firma_ref del perfil."""
    try:
        provider = SatProvider()
        raw = provider.debug_profile(user_id)
        return {
            'exists': raw.get('exists'),
            'firma_ref': raw.get('firma_ref'),
            'files': raw.get('files'),
            'missing_cer': raw.get('missing_cer'),
            'missing_key': raw.get('missing_key'),
            'bucket': raw.get('bucket'),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/debug/auth-artifacts')
def debug_auth_artifacts():
    """Devuelve si  existen los archivos sat_auth_envelope.xml y sat_auth_fault_response.xml.

    Útil cuando SAT_SAVE_SOAP=1 y SAT_DEBUG=1 para inspeccionar la última petición/respuesta.
    Incluye un snippet (primeros 400 caracteres) para revisión rápida.
    """
    files = ['sat_auth_envelope.xml', 'sat_auth_fault_response.xml']
    out = {}
    import os
    for fname in files:
        if os.path.exists(fname):
            try:
                with open(fname, 'r', encoding='utf-8', errors='ignore') as fh:
                    txt = fh.read()
                out[fname] = {
                    'exists': True,
                    'size': len(txt),
                    'snippet': txt[:400]
                }
            except Exception as e:
                out[fname] = {'exists': True, 'error': str(e)}
        else:
            out[fname] = {'exists': False}
    return out


@router.get('/debug/ops')
def debug_wsdl_operations():
    """Lista las operaciones disponibles en los WSDL de Autenticación y Solicitud.

    Útil para confirmar los nombres exactos que expone el SAT y evitar errores de 'No such operation'.
    """
    try:
        ops = {'auth': [], 'request': [], 'request_signatures': {}}  # type: ignore[typeddict-item]
        try:
            from zeep import Client as _ZeepClient  # type: ignore
            from ..services.sat_sat20 import WSDL_AUTENTICACION, WSDL_SOLICITUD
        except Exception as e:
            return {'error': f'ImportError zeep o constantes WSDL: {e}'}

        # Intentar construir clientes (capturamos errores individuales)
        c1 = None
        c2 = None
        try:
            c1 = _ZeepClient(WSDL_AUTENTICACION)
        except Exception as e:
            ops['auth_error'] = str(e)  # type: ignore[index]
        try:
            c2 = _ZeepClient(WSDL_SOLICITUD)
        except Exception as e:
            ops['request_error'] = str(e)  # type: ignore[index]

        def _ops(client):
            if client is None:
                return []
            try:
                for svc in client.wsdl.services.values():  # type: ignore[attr-defined]
                    for port in svc.ports.values():  # type: ignore[attr-defined]
                        return sorted(list(port.binding._operations.keys()))  # type: ignore[attr-defined]
            except Exception:
                return []

        if c1:
            ops['auth'] = _ops(c1)  # type: ignore[index]
        if c2:
            ops['request'] = _ops(c2)  # type: ignore[index]

        # Firmas de operaciones de solicitud
        if c2:
            try:
                for svc in c2.wsdl.services.values():  # type: ignore[attr-defined]
                    for port in svc.ports.values():  # type: ignore[attr-defined]
                        for name, op in port.binding._operations.items():  # type: ignore[attr-defined]
                            try:
                                sig = op.input.signature(c2.wsdl.types)  # type: ignore[attr-defined]
                            except Exception:
                                try:
                                    sig = str(op)
                                except Exception:
                                    sig = 'unknown'
                            ops['request_signatures'][name] = sig  # type: ignore[index]
                        break
                    break
            except Exception as e:
                ops['signatures_error'] = str(e)  # type: ignore[index]
        return ops
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- CFDI UTILITIES (separadas de debug_wsdl_operations para registrar en OpenAPI) ---
@router.get('/cfdi/{uuid}/render')
def render_cfdi(uuid: str, format: str = Query('pdf', pattern='^(pdf|html|json)$')):
    """Renderiza un CFDI almacenado (tabla cfdi -> xml_ref -> Storage) usando satcfdi.render.
    Devuelve PDF (application/pdf), HTML (text/html) o JSON estructurado.
    Requiere que la librería satcfdi esté instalada. Si no, responde 501.
    """
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table('cfdi').select('xml_ref').eq('uuid', uuid).maybe_single().execute()
        data = getattr(resp, 'data', None)
        if not data or not data.get('xml_ref'):
            raise HTTPException(status_code=404, detail='CFDI no encontrado')
        xml_ref = data['xml_ref']
        bucket = os.environ.get('CFDI_BUCKET', 'cfdi-xml')
        xml_bytes = sb.storage.from_(bucket).download(xml_ref)
        try:
            from satcfdi.cfdi import CFDI  # type: ignore
            from satcfdi import render as sat_render  # type: ignore
        except Exception:
            raise HTTPException(status_code=501, detail='satcfdi no disponible para render')
        cfdi_obj = CFDI.from_string(bytes(xml_bytes))
        if format == 'json':
            js = cfdi_obj.to_dict() if hasattr(cfdi_obj, 'to_dict') else {}  # type: ignore
            return JSONResponse(content=js)
        elif format == 'html':
            html_str = sat_render.html_str(cfdi_obj)
            return StreamingResponse(io.BytesIO(html_str.encode('utf-8')), media_type='text/html')
        else:  # pdf
            pdf_bytes = sat_render.pdf_bytes(cfdi_obj) if hasattr(sat_render, 'pdf_bytes') else None
            if pdf_bytes is None:
                sat_render.pdf_write(cfdi_obj, 'tmp_cfdi.pdf')  # type: ignore
                with open('tmp_cfdi.pdf', 'rb') as fh:
                    pdf_bytes = fh.read()
                try:
                    os.remove('tmp_cfdi.pdf')
                except Exception:
                    pass
            return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf')
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/cfdi/{uuid}/validate')
def validate_cfdi(uuid: str):
    """Valida firmas y certificados del CFDI usando satcfdi SAT.validate().
    Devuelve { uuid, valid }.
    """
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table('cfdi').select('xml_ref').eq('uuid', uuid).maybe_single().execute()
        data = getattr(resp, 'data', None)
        if not data or not data.get('xml_ref'):
            raise HTTPException(status_code=404, detail='CFDI no encontrado')
        xml_ref = data['xml_ref']
        bucket = os.environ.get('CFDI_BUCKET', 'cfdi-xml')
        xml_bytes = sb.storage.from_(bucket).download(xml_ref)
        try:
            from satcfdi.cfdi import CFDI  # type: ignore
            from satcfdi.pacs.sat import SAT  # type: ignore
        except Exception:
            raise HTTPException(status_code=501, detail='satcfdi no disponible para validación')
        cfdi_obj = CFDI.from_string(bytes(xml_bytes))
        sat = SAT()  # No requiere signer para validate
        valid = sat.validate(cfdi_obj)
        return { 'uuid': uuid, 'valid': bool(valid) }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
