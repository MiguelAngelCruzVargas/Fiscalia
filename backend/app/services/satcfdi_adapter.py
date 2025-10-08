import os
import time
from datetime import datetime, timedelta, UTC
from typing import Optional, List, Dict, Any

_token_cache: Dict[str, Dict[str, Any]] = {}

class SatCfdiAdapterError(RuntimeError):
    pass

def _cache_key(cert_sha256: str, scope: str) -> str:
    return f"{cert_sha256}:{scope}"

def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

def authenticate(cert_der: bytes, key_der: bytes, passphrase: Optional[str], cert_sha256: str, scope: str = 'comprobante') -> str:
    """Obtiene (con cache) un token de autenticación SAT usando SAT-CFDI.

    :param cert_der: Certificado DER bytes
    :param key_der: Llave privada DER bytes
    :param passphrase: Passphrase de la llave
    :param cert_sha256: Hash para clave cache (de .cer)
    :param scope: 'comprobante' o 'retencion'
    :return: token string
    """
    ttl_seconds = int(os.environ.get('SAT_TOKEN_TTL_SECONDS', '540'))  # < 600 para renovar antes de expirar
    ck = _cache_key(cert_sha256, scope)
    entry = _token_cache.get(ck)
    if entry and entry['expires_at'] > _now():
        return entry['token']

    try:
        from satcfdi.pacs.sat import _CFDIAutenticacion, _RetenAutenticacion  # type: ignore
        from satcfdi.models import Signer  # type: ignore
        from lxml import etree  # type: ignore
        import requests  # type: ignore
    except Exception:
        # Intentar vendor local
        repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        ext_path = os.path.join(repo_root, 'external', 'python-satcfdi')
        import sys
        if os.path.isdir(ext_path) and ext_path not in sys.path:
            sys.path.insert(0, ext_path)
        try:
            from satcfdi.pacs.sat import _CFDIAutenticacion, _RetenAutenticacion  # type: ignore
            from satcfdi.models import Signer  # type: ignore
            from lxml import etree  # type: ignore
            import requests  # type: ignore
        except Exception as e:  # pragma: no cover
            raise SatCfdiAdapterError(f'No se pudo importar SAT-CFDI: {e}')

    signer = Signer.load(certificate=cert_der, key=key_der, password=(passphrase or '').encode('utf-8') if passphrase else None)
    req_cls = _CFDIAutenticacion if scope == 'comprobante' else _RetenAutenticacion
    req = req_cls(signer=signer, arguments={'seconds': ttl_seconds})
    payload = req.get_payload()
    headers = {
        'Content-type': 'text/xml;charset="utf-8"',
        'Accept': 'text/xml',
        'Cache-Control': 'no-cache',
        'SOAPAction': req.soap_action,
    }
    resp = requests.post(req.soap_url, data=payload, headers=headers, timeout=30)
    if resp.status_code >= 400:
        raise SatCfdiAdapterError(f'HTTP {resp.status_code}: {(resp.text or "")[:200]}')
    doc = etree.fromstring(resp.content)
    parsed = req.process_response(doc)
    token = (parsed or {}).get('AutenticaResult')
    if not token:
        raise SatCfdiAdapterError('SAT-CFDI no devolvió token')
    expires = _now() + timedelta(seconds=ttl_seconds - 30)  # margen
    _token_cache[ck] = {'token': token, 'expires_at': expires}
    return token

# ---- Flujo completo opcional ----

def solicitar(signer_rfc: str, kind: str, rfc_objetivo: str, date_from: str, date_to: str, token_provider, tipo_solicitud: str = 'CFDI', estado_comp: Optional[str] = None, tipo_comp: Optional[str] = None) -> Dict[str, Any]:
    """Crea solicitud Emitidos/Recibidos usando SAT(SAT-CFDI). Devuelve dict con IdSolicitud y metadatos."""
    try:
        from satcfdi.pacs.sat import SAT, Signer  # type: ignore
    except Exception:
        # vendor fallback
        repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        ext_path = os.path.join(repo_root, 'external', 'python-satcfdi')
        import sys
        if os.path.isdir(ext_path) and ext_path not in sys.path:
            sys.path.insert(0, ext_path)
        from satcfdi.pacs.sat import SAT, Signer  # type: ignore

    sat: SAT = token_provider  # ya inicializado con signer y tokens internamente
    if kind.lower().startswith('emit'):
        res = sat.recover_comprobante_emitted_request(
            fecha_inicial=date_from,
            fecha_final=date_to,
            rfc_emisor=rfc_objetivo,
            tipo_solicitud=tipo_solicitud,
            estado_comprobante=estado_comp,
        )
    else:
        res = sat.recover_comprobante_received_request(
            fecha_inicial=date_from,
            fecha_final=date_to,
            rfc_receptor=rfc_objetivo,
            tipo_solicitud=tipo_solicitud,
            estado_comprobante=estado_comp,
        )
    return res


def verificar(sat_instance, request_id: str, max_wait: int = 300, interval: int = 5) -> Dict[str, Any]:
    """Hace polling hasta TERMINADA o NO_ENCONTRADO. Devuelve dict con estado y lista paquetes."""
    start = time.time()
    while time.time() - start < max_wait:
        res = sat_instance.recover_comprobante_status(request_id)
        estado = res.get('EstadoSolicitud')
        cod = res.get('CodigoEstadoSolicitud') or res.get('CodEstatus')
        if str(estado) == '3':  # Terminada
            return {'estado': estado, 'codigo': cod, 'paquetes': res.get('IdsPaquetes', []), 'raw': res}
        if cod == '5004':
            return {'estado': estado, 'codigo': cod, 'paquetes': [], 'raw': res}
        if cod in ('5003','5005','5011'):
            # Propagamos como estado final con error lógico
            return {'estado': estado, 'codigo': cod, 'paquetes': [], 'raw': res}
        time.sleep(interval)
    raise SatCfdiAdapterError(f'Timeout verificando solicitud {request_id}')


def descargar_paquete(sat_instance, paquete_id: str) -> Dict[str, Any]:
    """Descarga paquete y regresa dict con 'contenido_b64' y meta (header)."""
    header, b64data = sat_instance.recover_comprobante_download(paquete_id)
    return {'header': header, 'b64': b64data}


def parse_zip_cfdis(b64data: str) -> List[Dict[str, Any]]:
    """Decodifica ZIP base64 y parsea CFDI con satcfdi.CFDI para extraer datos clave."""
    import base64, zipfile, io, re
    from decimal import Decimal
    try:
        from satcfdi.cfdi import CFDI  # type: ignore
    except Exception as e:
        raise SatCfdiAdapterError(f'No se pudo importar CFDI: {e}')

    raw = base64.b64decode(b64data)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    items: List[Dict[str, Any]] = []
    for name in zf.namelist():
        if not name.lower().endswith('.xml'):
            continue
        xml_bytes = zf.read(name)
        try:
            cfdi = CFDI.from_string(xml_bytes)
            version = cfdi['Version']
            uuid = cfdi['Complemento']['TimbreFiscalDigital']['UUID']
            total = float(cfdi['Total'])
            fecha = cfdi['Fecha'][:10]
            tipo = cfdi['TipoDeComprobante']
            emisor_rfc = cfdi['Emisor']['Rfc']
            receptor_rfc = cfdi['Receptor']['Rfc']
            # IVA trasladado (002)
            iva = 0.0
            try:
                imps = cfdi.get('Impuestos', {})
                traslados = imps.get('Traslados') or []
                if isinstance(traslados, dict):
                    traslados = [traslados]
                for t in traslados:
                    if t.get('Impuesto') == '002' and t.get('Importe'):
                        iva += float(t['Importe'])
            except Exception:
                pass
            subtotal = float(cfdi.get('SubTotal') or 0)
            items.append({
                'uuid': uuid,
                'fecha': fecha,
                'subtotal': subtotal,
                'iva': round(iva, 2) if iva else None,
                'total': total,
                'tipo': tipo[:1],
                'emisor_rfc': emisor_rfc,
                'receptor_rfc': receptor_rfc,
                'content': xml_bytes.decode('utf-8', errors='ignore'),
            })
        except Exception:
            # fallback a heurística simple
            text = xml_bytes.decode('utf-8', errors='ignore')
            def rex(pat):
                m = re.search(pat, text, re.I)
                return m.group(1) if m else ''
            uuid = rex(r'UUID="([^"]+)"') or ''
            fecha = (rex(r'Fecha="([0-9T:\-]+)"') or '')[:10]
            subtotal = float(rex(r'SubTotal="([0-9\.]+)"') or 0)
            total = float(rex(r'Total="([0-9\.]+)"') or 0)
            tipo = (rex(r'TipoDeComprobante="([IEP])"') or 'I')
            emisor = rex(r'Emisor[^>]*Rfc="([A-Z0-9&]+)"')
            receptor = rex(r'Receptor[^>]*Rfc="([A-Z0-9&]+)"')
            items.append({
                'uuid': uuid or '', 'fecha': fecha, 'subtotal': subtotal, 'iva': None,
                'total': total, 'tipo': tipo, 'emisor_rfc': emisor, 'receptor_rfc': receptor,
                'content': text,
            })
    return items
